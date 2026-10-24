"""Use HA's flow manager and entity platforms in an isolated config directory."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.bark_alerts.const import (
    CONF_BEEP_ONLY,
    CONF_BROADLINK,
    CONF_CAMERA,
    CONF_COMMAND,
    CONF_COMMAND_MODE,
    CONF_DELAY,
    CONF_DEVICE,
    CONF_FALLBACK,
    CONF_REPEATS,
    CONF_RF_CODE,
    DEFAULTS,
    DOMAIN,
)

from .test_validation import packet


async def configure_named(hass, result, device):
    for data in (
        {CONF_COMMAND_MODE: "learned"},
        {CONF_DEVICE: device},
        {CONF_COMMAND: "beep", CONF_BEEP_ONLY: True},
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["step_id"] == "behavior"
    return result


async def test_real_flow_setup_platforms_options_and_unload(hass, rig, learned_storage):
    learned_storage({"example": {"beep": "synthetic saved packet"}})
    # Source integrations are represented by isolated registries, never hardware.
    hass.config.components.add("broadlink")
    assert await async_setup_component(hass, "remote", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CAMERA: rig.selected["camera"].entity_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BROADLINK: rig.device.id}
    )
    result = await configure_named(hass, result, "example")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULTS)
    )
    assert result["type"] == "create_entry"
    entry = result["result"]
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    controller = entry.runtime_data
    assert not controller.armed and controller.dry_run
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 8
    assert all(hass.states.get(entity.entity_id) is not None for entity in entities)
    assert not rig.sends and not rig.learns
    # Arming controls are configuration entities, which voice assistants do not
    # receive by default.
    switches = [entity for entity in entities if entity.domain == "switch"]
    assert len(switches) == 2
    assert all(entity.entity_category is EntityCategory.CONFIG for entity in switches)

    controller.armed, controller.dry_run = True, False
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**DEFAULTS, CONF_FALLBACK: True, CONF_REPEATS: 2, CONF_DELAY: 2},
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is not controller
    assert not entry.runtime_data.armed and entry.runtime_data.dry_run
    assert entry.options[CONF_REPEATS] == entry.runtime_data.option(CONF_REPEATS) == 2
    assert entry.options[CONF_DELAY] == entry.runtime_data.option(CONF_DELAY) == 2

    # A new controller preserves saved options, never the live enable switches.
    reloaded = entry.runtime_data
    reloaded.armed, reloaded.dry_run = True, False
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data is not reloaded
    assert not entry.runtime_data.armed and entry.runtime_data.dry_run
    assert entry.runtime_data.option(CONF_REPEATS) == 2
    assert entry.runtime_data.option(CONF_DELAY) == 2
    assert not rig.sends and not rig.learns

    # Reconfigure the same pairing without falsely treating itself as a duplicate.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CAMERA: rig.selected["camera"].entity_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BROADLINK: rig.device.id}
    )
    assert result["step_id"] == "command"
    result = await configure_named(hass, result, "replacement")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULTS)
    )
    assert result["type"] == "abort" and result["reason"] == "reconfigured"
    await hass.async_block_till_done()
    assert entry.data[CONF_DEVICE] == "replacement"
    assert not entry.runtime_data.armed and entry.runtime_data.dry_run

    # A second entry for exactly this camera and transmitter is rejected.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CAMERA: rig.selected["camera"].entity_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BROADLINK: rig.device.id}
    )
    assert result["type"] == "abort" and result["reason"] == "already_configured"
    await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not rig.sends and not rig.learns


async def test_real_raw_flow_setup_and_reconfigure_to_named(hass, rig):
    hass.config.components.add("broadlink")
    assert await async_setup_component(hass, "remote", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    for data in (
        {CONF_CAMERA: rig.selected["camera"].entity_id},
        {CONF_BROADLINK: rig.device.id},
        {CONF_COMMAND_MODE: "raw"},
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["step_id"] == "raw_command"
    assert set(result["data_schema"].schema) == {CONF_RF_CODE, CONF_BEEP_ONLY}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_RF_CODE: packet(0xB1), CONF_BEEP_ONLY: True}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULTS)
    )
    entry = result["result"]
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_RF_CODE] == "b64:" + packet(0xB1)
    assert CONF_DEVICE not in entry.data and CONF_COMMAND not in entry.data
    assert not entry.runtime_data.armed and entry.runtime_data.dry_run
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    for data in (
        {CONF_CAMERA: rig.selected["camera"].entity_id},
        {CONF_BROADLINK: rig.device.id},
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    result = await configure_named(hass, result, "New group")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULTS)
    )
    assert result["reason"] == "reconfigured"
    await hass.async_block_till_done()
    assert entry.data[CONF_DEVICE] == "New group"
    assert CONF_RF_CODE not in entry.data
    assert not entry.runtime_data.armed and entry.runtime_data.dry_run
    assert not rig.sends and not rig.learns
    await hass.config_entries.async_unload(entry.entry_id)
