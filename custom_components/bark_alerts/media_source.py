"""Authenticated audio playback through Home Assistant's Media browser."""

from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source import (
    MediaSource,
    PlayMedia,
    Unresolvable,
)
from homeassistant.components.media_source.models import BrowseMediaSource
from homeassistant.util import dt as dt_util

from .const import DOMAIN


def get_history(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry and entry.domain == DOMAIN:
        return getattr(getattr(entry, "runtime_data", None), "history", None)
    return None


def register_history_view(hass):
    if not hass.data.get(f"{DOMAIN}_history_view"):
        hass.http.register_view(BarkHistoryView())
        hass.data[f"{DOMAIN}_history_view"] = True


class BarkHistoryView(HomeAssistantView):
    url = "/api/bark_alerts/history/{entry_id}/{clip_id}"
    name = "api:bark_alerts:history"
    requires_auth = True

    async def get(self, request, entry_id, clip_id):
        hass = request.app["hass"]
        history = get_history(hass, entry_id)
        path = history.clip_path(clip_id) if history else None
        if path is None or not await hass.async_add_executor_job(
            lambda: path.is_file() and not path.is_symlink()
        ):
            raise web.HTTPNotFound()
        return web.FileResponse(
            path, headers={"Content-Type": "audio/wav", "Cache-Control": "no-store"}
        )


async def async_get_media_source(hass):
    return BarkHistorySource(hass)


class BarkHistorySource(MediaSource):
    name = "Bark Alerts history"

    def __init__(self, hass):
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_browse_media(self, item):
        if not item.identifier:
            children = []
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if get_history(self.hass, entry.entry_id):
                    children.append(
                        BrowseMediaSource(
                            domain=DOMAIN,
                            identifier=entry.entry_id,
                            title=entry.title,
                            media_class=MediaClass.DIRECTORY,
                            media_content_type=MediaType.MUSIC,
                            can_play=False,
                            can_expand=True,
                        )
                    )
            title = self.name
        else:
            history = get_history(self.hass, item.identifier)
            if history is None:
                raise BrowseError("History unavailable")
            title = "Latest 25 bark episodes"
            children = []
            for row in history.items:
                date = dt_util.as_local(datetime.fromtimestamp(row["timestamp"], UTC))
                label = f"{date:%Y-%m-%d %H:%M:%S}: {row['outcome']}: {row['status']}"
                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=f"{item.identifier}/{row['id']}",
                        title=label,
                        media_class=MediaClass.MUSIC,
                        media_content_type="audio/wav",
                        can_play=row["status"] == "ready",
                        can_expand=False,
                    )
                )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=item.identifier,
            title=title,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def async_resolve_media(self, item):
        parts = item.identifier.split("/")
        if len(parts) != 2:
            raise Unresolvable("Unknown clip")
        history = get_history(self.hass, parts[0])
        if history is None or history.clip_path(parts[1]) is None:
            raise Unresolvable("Clip unavailable or expired")
        return PlayMedia(f"/api/bark_alerts/history/{parts[0]}/{parts[1]}", "audio/wav")
