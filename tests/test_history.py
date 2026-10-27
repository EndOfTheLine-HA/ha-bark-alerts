"""Archive retention, lifecycle, authenticated playback and RF separation."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homeassistant.components.media_source import Unresolvable
from homeassistant.setup import async_setup_component

from custom_components.bark_alerts import history as history_module
from custom_components.bark_alerts.const import CONF_HISTORY, DOMAIN
from custom_components.bark_alerts.history import BarkHistory, HistoryError
from custom_components.bark_alerts.media_source import (
    BarkHistorySource,
    register_history_view,
)

from .conftest import add_entry
from .test_controller import controller as controller_fixture
from .test_controller import edge

controller = controller_fixture


async def fake_extract(source, target, binary):
    # Bytes are deliberately synthetic; real decoding has a separate smoke test.
    target.write_bytes(b"RIFF" + bytes(200))


@pytest.fixture
async def archive(hass):
    entry = add_entry(hass, DOMAIN)
    history = BarkHistory(
        hass,
        entry,
        lambda: None,
        fetch=AsyncMock(return_value=b"video"),
        extract=fake_extract,
    )
    entry.runtime_data = SimpleNamespace(history=history)
    await history.initialize()
    yield history
    await history.close()


async def test_retains_latest_25_and_survives_restart(archive):
    ids = []
    for index in range(30):
        ids.append(archive.add(time.time() - 60 + index / 100))
        archive.outcome(ids[-1], "disarmed")
        await archive.task
    assert len(archive.items) == 25
    assert len(list(archive.folder.glob("*.wav"))) == 25
    assert archive.clip_path(ids[0]) is None
    assert archive.clip_path(ids[-1]).is_file()
    await archive.close()
    other = BarkHistory(archive.hass, archive.entry, lambda: None)
    await other.initialize()
    assert len(other.items) == 25
    assert other.items[0]["outcome"] == "disarmed"
    assert all(row["status"] == "ready" for row in other.items)
    await other.clear()
    assert not list(other.folder.glob("*.wav"))
    assert json.loads((other.folder / "index.json").read_text()) == []


async def test_capture_failure_does_not_claim_audio(archive):
    archive.fetch.side_effect = HistoryError("recording_unavailable")
    clip = archive.add(time.time() - 60)
    await archive.task
    assert archive.items[0]["status"] == "recording_unavailable"
    assert archive.clip_path(clip) is None
    assert not list(archive.folder.glob("*.mp4"))


async def test_clear_cancels_capture_without_late_files(archive):
    started = asyncio.Event()

    async def fetch(*args):
        started.set()
        await asyncio.Event().wait()

    archive.fetch = fetch
    archive.add(time.time() - 60)
    await started.wait()
    await archive.clear()
    assert not archive.items and not archive.pending
    assert not list(archive.folder.glob("*.wav"))
    assert not list(archive.folder.glob("*.mp4"))


async def test_pending_queue_bounded_and_unload_cancels(archive):
    for _ in range(100):
        archive.add(time.time())
    assert len(archive.items) == len(archive.pending) == 25
    await archive.close()
    assert not archive.pending
    assert all(row["status"] == "interrupted" for row in archive.items)
    archive.fetch.assert_not_awaited()


async def test_only_bark_edges_archive_while_disarmed_or_dry_run(hass, rig, controller):
    history = BarkHistory(
        hass,
        controller.entry,
        lambda: None,
        fetch=AsyncMock(return_value=b"video"),
        extract=fake_extract,
    )
    await history.initialize()
    controller.history = history
    hass.config_entries.async_update_entry(
        controller.entry, options={**controller.entry.options, CONF_HISTORY: True}
    )
    await edge(hass, rig.selected["bark"])
    assert history.items[0]["outcome"] == "disarmed"
    controller.armed, controller.dry_run = True, True
    await edge(hass, rig.selected["bark"])
    assert history.items[0]["outcome"] == "dry_run"
    await edge(hass, rig.selected["bark"])
    assert history.items[0]["outcome"] == "cooldown"
    assert len(history.items) == 3
    await edge(hass, rig.other["bark"])
    await edge(hass, rig.selected["animal"])
    assert len(history.items) == 3
    assert not rig.sends and not rig.learns
    await history.close()


async def test_disabled_history_does_not_fetch(hass, rig, controller):
    controller.history = SimpleNamespace(add=AsyncMock(), stop=lambda: None)
    await edge(hass, rig.selected["bark"])
    controller.history.add.assert_not_called()
    assert not rig.sends


async def test_late_outcome_persists_after_capture(archive):
    clip = archive.add(time.time() - 60)
    await archive.task
    archive.outcome(clip, "command_requested")
    await archive.task
    rows = json.loads((archive.folder / "index.json").read_text())
    assert rows[0]["outcome"] == "command_requested"
    assert archive.clip_path(clip).is_file()


async def test_corrupt_index_and_path_injection_are_ignored(archive):
    (archive.folder / "index.json").write_text(
        json.dumps(
            [
                {"id": "../secrets", "timestamp": 123, "status": "ready"},
                {
                    "id": "a" * 32,
                    "timestamp": float("nan"),
                    "status": "ready",
                    "outcome": "dry_run",
                },
                {"id": "b" * 32, "timestamp": 123},
            ]
        )
    )
    await archive.initialize()
    assert archive.items == []
    assert archive.clip_path("../secrets") is None


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "authentication_failed"),
        (403, "authentication_failed"),
        (404, "recording_unavailable"),
        (302, "recording_unavailable"),
        (200, "recording_too_large"),
    ],
)
async def test_download_errors_are_bounded_and_private(
    hass, rig, controller, monkeypatch, status, expected
):
    from aiohttp import web

    async def respond(request):
        if status == 200:
            return web.Response(body=b"x" * 101)
        return web.Response(status=status, text="private upstream response")

    app = web.Application()
    app.router.add_get("/{tail:.*}", respond)
    async with TestClient(TestServer(app)) as client:
        hass.config_entries.async_update_entry(
            rig.frigate, data={"url": str(client.server.make_url("/"))}
        )
        hass.data["frigate"] = {
            rig.frigate.entry_id: {
                "client": SimpleNamespace(
                    get_auth_headers=AsyncMock(return_value={}), validate_ssl=True
                )
            }
        }
        monkeypatch.setattr(
            history_module, "async_get_clientsession", lambda _: client.session
        )
        monkeypatch.setattr(history_module, "MAX_DOWNLOAD", 100)
        with pytest.raises(HistoryError) as error:
            await history_module.download_recording(
                hass, controller.entry, time.time() - 60
            )
        assert str(error.value) == expected


async def test_streamed_download_limit(hass, rig, controller, monkeypatch):
    from aiohttp import web

    async def respond(request):
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(b"x" * 101)
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_get("/{tail:.*}", respond)
    async with TestClient(TestServer(app)) as client:
        hass.config_entries.async_update_entry(
            rig.frigate, data={"url": str(client.server.make_url("/"))}
        )
        hass.data["frigate"] = {
            rig.frigate.entry_id: {
                "client": SimpleNamespace(get_auth_headers=AsyncMock(return_value={}))
            }
        }
        monkeypatch.setattr(
            history_module, "async_get_clientsession", lambda _: client.session
        )
        monkeypatch.setattr(history_module, "MAX_DOWNLOAD", 100)
        with pytest.raises(HistoryError, match="recording_too_large"):
            await history_module.download_recording(
                hass, controller.entry, time.time() - 60
            )


async def test_media_browse_and_http_require_auth(hass, archive):
    assert await async_setup_component(hass, "http", {})
    register_history_view(hass)
    clip = archive.add(time.time() - 60)
    archive.outcome(clip, "dry_run")
    await archive.task
    source = BarkHistorySource(hass)
    browser = await source.async_browse_media(
        SimpleNamespace(identifier=archive.entry.entry_id)
    )
    assert len(browser.children) == 1
    assert browser.children[0].can_play
    assert "dry_run" in browser.children[0].title
    media = await source.async_resolve_media(
        SimpleNamespace(identifier=f"{archive.entry.entry_id}/{clip}")
    )
    assert media.mime_type == "audio/wav"
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(
            SimpleNamespace(identifier=f"{archive.entry.entry_id}/../secrets.yaml")
        )
    user = await hass.auth.async_create_user("Archive test")
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="http://localhost/"
    )
    token = hass.auth.async_create_access_token(refresh)
    async with TestClient(TestServer(hass.http.app)) as client:
        response = await client.get(media.url)
        assert response.status == 401
        response = await client.get(
            media.url, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status == 200
        assert (await response.read()).startswith(b"RIFF")
        assert response.headers["Cache-Control"] == "no-store"
        await archive.clear()
        response = await client.get(
            media.url, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status == 404


async def test_archive_fetches_and_preserves_trigger_camera(archive):
    clip = archive.add(time.time() - 60, "selected-camera-registry-id")
    await archive.task
    assert archive.fetch.call_args.args[3] == "selected-camera-registry-id"
    rows = json.loads((archive.folder / "index.json").read_text())
    assert rows[0]["camera_id"] == "selected-camera-registry-id"
    assert archive.clip_path(clip).is_file()


@pytest.mark.parametrize("which", ["selected", "other"])
async def test_download_uses_camera_that_triggered_event(
    hass, rig, controller, monkeypatch, which
):
    from aiohttp import web

    from custom_components.bark_alerts.const import CONF_CAMERA_IDS

    paths = []

    async def respond(request):
        paths.append(request.path)
        return web.Response(body=b"synthetic video")

    app = web.Application()
    app.router.add_get("/{tail:.*}", respond)
    selected = getattr(rig, which)["camera"]
    hass.config_entries.async_update_entry(
        controller.entry,
        data={
            **controller.entry.data,
            CONF_CAMERA_IDS: [rig.selected["camera"].id, rig.other["camera"].id],
        },
    )
    async with TestClient(TestServer(app)) as client:
        hass.config_entries.async_update_entry(
            rig.frigate, data={"url": str(client.server.make_url("/"))}
        )
        hass.data["frigate"] = {
            rig.frigate.entry_id: {
                "client": SimpleNamespace(get_auth_headers=AsyncMock(return_value={}))
            }
        }
        monkeypatch.setattr(
            history_module, "async_get_clientsession", lambda _: client.session
        )
        assert (
            await history_module.download_recording(
                hass, controller.entry, time.time() - 60, selected.id
            )
            == b"synthetic video"
        )
    camera_key = selected.unique_id.split(":camera:", 1)[1]
    assert paths[0].startswith(f"/api/{camera_key}/start/")
