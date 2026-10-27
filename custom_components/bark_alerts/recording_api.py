"""Frigate's documented HTTP recording and login API; no integration internals.

https://docs.frigate.video/integrations/api/frigate-http-api/
https://docs.frigate.video/configuration/authentication/#api-authentication-guide
"""

from __future__ import annotations

import asyncio
import time

from aiohttp import ClientError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from .const import CONF_CAMERA_ID, CONF_HISTORY_CONNECTION
from .discovery import DiscoveryError, selected_camera_ids

MAX_DOWNLOAD = 20 * 1024 * 1024
PRE_SECONDS = 5
POST_SECONDS = 5


class HistoryError(Exception):
    """Only a non-sensitive status code may leave the recording adapter."""


def normalize_connection(data: dict, previous: dict | None = None) -> dict:
    """Validate explicitly supplied settings; never borrow another entry's data."""
    previous = previous or {}
    try:
        url = URL(data.get("url", "").strip())
        if (
            url.scheme not in ("http", "https")
            or not url.host
            or url.user is not None
            or url.password is not None
            or url.query_string
            or url.fragment
        ):
            raise ValueError
        normalized = str(url).rstrip("/")
        username = data.get("username", "").strip()
        password = data.get("password", "")
        # A blank password retains the saved value only for the exact same
        # destination and account. Changing destination never forwards a secret.
        if not password and (normalized, username) == (
            previous.get("url"),
            previous.get("username", ""),
        ):
            password = previous.get("password", "")
        if bool(username) != bool(password):
            raise ValueError
        return {
            "url": normalized,
            "username": username,
            "password": password,
            "verify_ssl": data.get("verify_ssl", True) is not False,
        }
    except ValueError, TypeError, AttributeError:
        raise DiscoveryError("invalid_history_connection") from None


def validate_history_cameras(hass, data: dict) -> None:
    """One explicitly configured API connection can serve one Frigate instance."""
    registry = er.async_get(hass)
    cameras = [registry.async_get(key) for key in selected_camera_ids(data)]
    if not cameras or any(camera is None for camera in cameras):
        raise DiscoveryError("invalid_camera")
    if len({camera.config_entry_id for camera in cameras}) != 1:
        raise DiscoveryError("history_multiple_instances")


class FrigateRecordingClient:
    """Use user-configured API settings and a token held only in memory."""

    def __init__(self):
        self._token = None
        self._destination = None
        self._retry_after = 0

    async def _login(self, session, base, settings):
        if time.monotonic() < self._retry_after:
            raise HistoryError("authentication_failed")
        self._retry_after = time.monotonic() + 60
        async with session.post(
            base / "api" / "login",
            json={"user": settings["username"], "password": settings["password"]},
            ssl=settings["verify_ssl"],
            allow_redirects=False,
        ) as response:
            # The documented login response sets the frigate_token JWT cookie.
            cookie = response.cookies.get("frigate_token")
            if response.status != 200 or cookie is None or not cookie.value:
                raise HistoryError("authentication_failed")
            self._token = cookie.value
            self._retry_after = 0

    async def download(self, hass, entry, timestamp, camera_id=None) -> bytes:
        camera_id = camera_id or entry.data[CONF_CAMERA_ID]
        if camera_id not in selected_camera_ids(entry.data):
            raise HistoryError("source_unavailable")
        camera = er.async_get(hass).async_get(camera_id)
        if camera is None or not camera.config_entry_id:
            raise HistoryError("source_unavailable")
        prefix = f"{camera.config_entry_id}:camera:"
        if not camera.unique_id.startswith(prefix):
            raise HistoryError("source_unavailable")
        try:
            validate_history_cameras(hass, entry.data)
            settings = normalize_connection(
                entry.options.get(CONF_HISTORY_CONNECTION, {})
            )
        except DiscoveryError:
            raise HistoryError("connection_required") from None
        destination = tuple(settings.items())
        if destination != self._destination:
            self._token, self._retry_after = None, 0
            self._destination = destination
        base = URL(settings["url"])
        url = (
            base
            / "api"
            / camera.unique_id[len(prefix) :]
            / "start"
            / str(timestamp - PRE_SECONDS)
            / "end"
            / str(timestamp + POST_SECONDS)
            / "clip.mp4"
        )
        session = async_get_clientsession(hass)
        try:
            async with asyncio.timeout(45):
                for attempt in range(2):
                    if settings["username"] and self._token is None:
                        await self._login(session, base, settings)
                    headers = (
                        {"Authorization": f"Bearer {self._token}"}
                        if self._token
                        else {}
                    )
                    async with session.get(
                        url,
                        headers=headers,
                        ssl=settings["verify_ssl"],
                        allow_redirects=False,
                    ) as response:
                        if (
                            response.status == 401
                            and settings["username"]
                            and attempt == 0
                        ):
                            self._token = None
                            continue
                        if response.status in (401, 403):
                            raise HistoryError("authentication_failed")
                        if response.status != 200:
                            raise HistoryError("recording_unavailable")
                        if (
                            response.content_length
                            and response.content_length > MAX_DOWNLOAD
                        ):
                            raise HistoryError("recording_too_large")
                        content = bytearray()
                        async for chunk in response.content.iter_chunked(65536):
                            content.extend(chunk)
                            if len(content) > MAX_DOWNLOAD:
                                raise HistoryError("recording_too_large")
                        if not content:
                            raise HistoryError("recording_unavailable")
                        return bytes(content)
        except ClientError, TimeoutError, ValueError:
            raise HistoryError("recording_unavailable") from None
