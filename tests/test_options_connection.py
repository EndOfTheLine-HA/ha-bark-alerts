"""Turning capture off must not forget the saved Frigate connection."""

from unittest.mock import AsyncMock

from custom_components.bark_alerts.const import (
    CONF_BROADLINK,
    CONF_CAMERA,
    CONF_COMMAND_MODE,
    CONF_HISTORY,
    CONF_HISTORY_CONNECTION,
    DOMAIN,
    MODE_KEEP,
)

from .test_controller import edge
from .test_lifecycle import create_monitor

SECRET = "synthetic secret"
CONNECTION = {
    "url": "https://example.test",
    "username": "viewer",
    "password": SECRET,
    "verify_ssl": True,
}


async def set_history(hass, entry, enabled, connection=None):
    """Submit the real options flow and return its final result."""
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {CONF_HISTORY: enabled}
    )
    if enabled:
        assert result["step_id"] == "history"
        assert SECRET not in repr(result)
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"], connection
        )
    await hass.async_block_till_done()
    return result


async def history_monitor(hass, rig):
    entry = await create_monitor(hass, rig, rig.selected)
    assert (await set_history(hass, entry, True, CONNECTION))["type"] == "create_entry"
    assert entry.options[CONF_HISTORY_CONNECTION] == CONNECTION
    return entry


async def test_options_keep_connection_when_history_is_turned_off(hass, rig):
    entry = await history_monitor(hass, rig)

    result = await set_history(hass, entry, False)

    assert result["type"] == "create_entry"
    assert entry.options[CONF_HISTORY] is False
    assert entry.options[CONF_HISTORY_CONNECTION] == CONNECTION
    await hass.config_entries.async_unload(entry.entry_id)


async def test_capture_stays_off_while_the_connection_is_kept(hass, rig):
    entry = await history_monitor(hass, rig)
    await set_history(hass, entry, False)
    history = entry.runtime_data.history
    history.fetch = AsyncMock()

    await edge(hass, rig.selected["bark"])

    assert not history.items and not history.pending
    history.fetch.assert_not_called()
    assert entry.runtime_data.outcome == "disarmed"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_turning_history_back_on_needs_no_password(hass, rig):
    entry = await history_monitor(hass, rig)
    await set_history(hass, entry, False)

    result = await set_history(
        hass, entry, True, {"url": CONNECTION["url"], "username": "viewer"}
    )

    assert result["type"] == "create_entry"
    assert entry.options[CONF_HISTORY] is True
    assert entry.options[CONF_HISTORY_CONNECTION] == CONNECTION
    await hass.config_entries.async_unload(entry.entry_id)


async def test_kept_password_is_not_sent_to_a_new_destination(hass, rig):
    entry = await history_monitor(hass, rig)
    await set_history(hass, entry, False)

    result = await set_history(
        hass, entry, True, {"url": "https://other.test", "username": "viewer"}
    )

    assert result["errors"]["base"] == "invalid_history_connection"
    assert entry.options[CONF_HISTORY] is False
    assert entry.options[CONF_HISTORY_CONNECTION] == CONNECTION
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure_keeps_connection_when_history_is_turned_off(hass, rig):
    entry = await history_monitor(hass, rig)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    for data in (
        {CONF_CAMERA: [rig.selected["camera"].entity_id]},
        {CONF_BROADLINK: rig.device.id},
        {CONF_COMMAND_MODE: MODE_KEEP},
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["step_id"] == "behavior"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HISTORY: False}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigured"
    assert entry.options[CONF_HISTORY] is False
    assert entry.options[CONF_HISTORY_CONNECTION] == CONNECTION
    await hass.config_entries.async_unload(entry.entry_id)


async def test_new_monitor_without_history_stores_no_connection(hass, rig):
    entry = await create_monitor(hass, rig, rig.selected)

    assert CONF_HISTORY_CONNECTION not in entry.options
    assert (await set_history(hass, entry, False))["type"] == "create_entry"
    assert CONF_HISTORY_CONNECTION not in entry.options
    await hass.config_entries.async_unload(entry.entry_id)
