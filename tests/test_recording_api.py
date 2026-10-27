"""Public API authentication, secret boundaries and configuration behavior."""

from unittest.mock import AsyncMock

import pytest
from aiohttp import DummyCookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from homeassistant.helpers import entity_registry as er

from custom_components.bark_alerts import recording_api as api
from custom_components.bark_alerts.config_flow import history_schema
from custom_components.bark_alerts.const import CONF_HISTORY_CONNECTION
from custom_components.bark_alerts.diagnostics import async_get_config_entry_diagnostics
from custom_components.bark_alerts.discovery import DiscoveryError

from .conftest import add_entry
from .test_controller import controller as controller_fixture

controller = controller_fixture


async def test_connection_secrets_are_excluded_from_diagnostics(hass, controller):
    hass.config_entries.async_update_entry(
        controller.entry,
        options={
            **controller.entry.options,
            CONF_HISTORY_CONNECTION: {
                "url": "https://example.test",
                "username": "private viewer",
                "password": "synthetic secret",
            },
        },
    )
    result = repr(await async_get_config_entry_diagnostics(hass, controller.entry))
    assert all(
        value not in result
        for value in (
            "example.test",
            "private viewer",
            "synthetic secret",
            CONF_HISTORY_CONNECTION,
        )
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.test",
        "http://user:secret@example.test",
        "http://example.test/?key=secret",
        "http://example.test/#secret",
    ],
)
def test_invalid_connection_does_not_expose_input(url):
    with pytest.raises(DiscoveryError, match="^invalid_history_connection$"):
        api.normalize_connection({"url": url})


def test_saved_password_is_not_prefilled_or_forwarded_to_a_changed_destination():
    previous = api.normalize_connection(
        {
            "url": "https://example.test/",
            "username": "viewer",
            "password": "synthetic secret",
        }
    )
    schema = history_schema(previous)
    assert "synthetic secret" not in repr(schema)
    unchanged = schema({})
    assert unchanged["password"] == ""
    assert api.normalize_connection(unchanged, previous) == previous
    for change in ({"url": "https://elsewhere.test"}, {"username": "someone_else"}):
        with pytest.raises(DiscoveryError):
            api.normalize_connection({**unchanged, **change}, previous)


async def test_history_requires_one_frigate_instance(hass, rig):
    api.validate_history_cameras(
        hass, {"camera_registry_id": rig.selected["camera"].id}
    )
    other = add_entry(hass, "frigate")
    camera = er.async_get(hass).async_get_or_create(
        "camera", "frigate", f"{other.entry_id}:camera:another", config_entry=other
    )
    with pytest.raises(DiscoveryError, match="history_multiple_instances"):
        api.validate_history_cameras(
            hass, {"camera_registry_ids": [rig.selected["camera"].id, camera.id]}
        )


async def test_legacy_enabled_history_never_uses_private_client(
    hass, rig, controller, monkeypatch
):
    private = AsyncMock()
    hass.data["frigate"] = {rig.frigate.entry_id: {"client": private}}
    with pytest.raises(api.HistoryError, match="connection_required"):
        await api.FrigateRecordingClient().download(hass, controller.entry, 100)
    private.assert_not_called()
    private.get_auth_headers.assert_not_called()


async def test_login_token_cache_expiry_and_direct_recording(
    hass, rig, controller, monkeypatch
):
    calls = {"login": 0, "get": 0, "current": "token-1"}

    async def login(request):
        assert await request.json() == {
            "user": "viewer",
            "password": "synthetic secret",
        }
        calls["login"] += 1
        result = web.Response()
        result.set_cookie("frigate_token", calls["current"], secure=True, httponly=True)
        return result

    async def recording(request):
        calls["get"] += 1
        assert request.path.startswith(
            "/prefix/api/example_yard/start/95/end/105/clip.mp4"
        )
        if request.headers.get("Authorization") != f"Bearer {calls['current']}":
            return web.Response(status=401)
        return web.Response(body=b"synthetic video")

    app = web.Application()
    app.router.add_post("/prefix/api/login", login)
    app.router.add_get("/{tail:.*}", recording)
    async with TestClient(TestServer(app), cookie_jar=DummyCookieJar()) as client:
        settings = {
            "url": str(client.server.make_url("/prefix")),
            "username": "viewer",
            "password": "synthetic secret",
        }
        hass.config_entries.async_update_entry(
            controller.entry, options={CONF_HISTORY_CONNECTION: settings}
        )
        monkeypatch.setattr(api, "async_get_clientsession", lambda _: client.session)
        adapter = api.FrigateRecordingClient()
        for _ in range(2):
            assert (
                await adapter.download(hass, controller.entry, 100)
                == b"synthetic video"
            )
        assert calls["login"] == 1
        calls["current"] = "token-2"
        assert await adapter.download(hass, controller.entry, 100) == b"synthetic video"
        assert calls["login"] == 2
        assert calls["get"] == 4
    assert not rig.sends and not rig.learns


@pytest.mark.parametrize("status", [401, 403, 302, 429])
async def test_failed_login_is_bounded_and_never_downloads(
    hass, rig, controller, monkeypatch, status
):
    calls = []

    async def login(request):
        calls.append(request.path)
        return web.Response(
            status=status,
            headers={"Location": "/elsewhere"},
            text="private upstream text",
        )

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", login)
    async with TestClient(TestServer(app)) as client:
        hass.config_entries.async_update_entry(
            controller.entry,
            options={
                CONF_HISTORY_CONNECTION: {
                    "url": str(client.server.make_url("/")),
                    "username": "viewer",
                    "password": "synthetic secret",
                }
            },
        )
        monkeypatch.setattr(api, "async_get_clientsession", lambda _: client.session)
        adapter = api.FrigateRecordingClient()
        for _ in range(2):
            with pytest.raises(api.HistoryError, match="^authentication_failed$"):
                await adapter.download(hass, controller.entry, 100)
    assert calls == ["/api/login"]
