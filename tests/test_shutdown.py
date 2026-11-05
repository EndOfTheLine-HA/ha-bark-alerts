"""HA's stop event and removal timing, through HA's real bus and thread checks."""

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame

from custom_components.bark_alerts.const import DOMAIN

from .test_history import fake_extract
from .test_lifecycle import create_monitor, saved_clip


@pytest.fixture
def thread_checks(hass, monkeypatch):
    """Turn on the frame helper HA needs to report calls from the wrong thread."""
    monkeypatch.setattr(frame._hass, "hass", hass)
    hass.config.debug = True


def watch_stop(controller):
    """Record the thread and outcome of each stop without changing what it does."""
    original = controller.async_stop
    calls = []
    finished = threading.Event()

    def recording():
        try:
            original()
        except Exception as err:
            calls.append((threading.get_ident(), err))
            raise
        else:
            calls.append((threading.get_ident(), None))
        finally:
            finished.set()

    controller.async_stop = recording
    return calls, finished


async def press_switch(hass, entry, key):
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_{key}"
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id}, blocking=True
    )


def problems(caplog):
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.ERROR
    ]


async def hold_capture(history):
    started = asyncio.Event()

    async def fetch(*args):
        started.set()
        await asyncio.Event().wait()

    history.fetch = fetch
    history.add(time.time() - 60)
    async with asyncio.timeout(5):
        await started.wait()
    return history.task


async def hold_send(hass, rig, controller):
    started = asyncio.Event()

    async def slow_send(call):
        started.set()
        await asyncio.Event().wait()

    hass.services.async_register("remote", "send_command", slow_send)
    hass.states.async_set(rig.selected["bark"].entity_id, "on")
    async with asyncio.timeout(5):
        await started.wait()
    return next(iter(controller._tasks))


@pytest.mark.parametrize("dry_run_warning", [True, False])
async def test_ha_stop_event_stops_monitor_on_event_loop(
    hass, rig, thread_checks, caplog, dry_run_warning
):
    entry = await create_monitor(hass, rig, rig.selected)
    controller = entry.runtime_data
    notification_id = f"{DOMAIN}_{entry.entry_id}_dry_run"
    notifications = persistent_notification._async_get_or_create_notifications(hass)

    await press_switch(hass, entry, "armed")
    pending = [await hold_capture(controller.history)]
    if dry_run_warning:
        await press_switch(hass, entry, "dry_run")
        assert notification_id in notifications
    else:
        pending.append(await hold_send(hass, rig, controller))
    calls, finished = watch_stop(controller)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    assert await hass.async_add_executor_job(finished.wait, 5)
    thread_id, error = calls[0]
    assert error is None
    assert thread_id == hass.loop_thread_id

    async with asyncio.timeout(5):
        await asyncio.gather(*pending, return_exceptions=True)
    assert all(task.cancelled() for task in pending)
    assert controller._stopped and not controller.armed and controller.history.closed
    assert notification_id not in notifications
    assert not problems(caplog)

    # A second stop and the later unload are safe, and remove nothing twice.
    controller.async_stop()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not problems(caplog)


async def test_unload_removes_stop_listener_exactly_once(
    hass, rig, thread_checks, caplog
):
    # The first monitor loads the platforms, which add stop listeners of their own.
    await create_monitor(hass, rig, rig.other)
    before = hass.bus.async_listeners()[EVENT_HOMEASSISTANT_STOP]
    entry = await create_monitor(hass, rig, rig.selected)
    assert hass.bus.async_listeners()[EVENT_HOMEASSISTANT_STOP] == before + 1
    calls, _ = watch_stop(entry.runtime_data)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.bus.async_listeners()[EVENT_HOMEASSISTANT_STOP] == before
    stops_from_unload = len(calls)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert len(calls) == stops_from_unload
    assert not problems(caplog)


async def test_removal_waits_for_in_progress_executor_write(hass, rig, monkeypatch):
    entry = await create_monitor(hass, rig, rig.selected)
    history = entry.runtime_data.history
    entered, release = threading.Event(), threading.Event()
    real_write = Path.write_bytes

    def held_write(path, data):
        if path.name == "capture.mp4":
            entered.set()
            release.wait(10)
        return real_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", held_write)
    history.fetch, history.extract = AsyncMock(return_value=b"video"), fake_extract
    history.add(time.time() - 60)
    assert await hass.async_add_executor_job(entered.wait, 5)

    removal = asyncio.create_task(hass.config_entries.async_remove(entry.entry_id))
    await asyncio.sleep(0.2)
    assert not removal.done()
    assert history.folder.exists()

    release.set()
    async with asyncio.timeout(5):
        await removal
    assert not history.folder.exists()


async def test_clear_finishing_after_removal_leaves_only_an_empty_index(hass, rig):
    entry = await create_monitor(hass, rig, rig.selected)
    history = entry.runtime_data.history
    await saved_clip(entry)

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not history.folder.exists()

    await history.clear()
    assert [path.name for path in history.folder.iterdir()] == ["index.json"]
    assert json.loads((history.folder / "index.json").read_text()) == []
