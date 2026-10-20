"""Use HA's flow manager and entity platforms in an isolated config directory."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.bark_alerts.const import (
    CONF_BEEP_ONLY,
    CONF_BROADLINK,
    CONF_CAMERA,
    CONF_COMMAND,
    CONF_COMMAND_MODE,
    CONF_DEVICE,
    CONF_FALLBACK,
    DEFAULTS,
    DOMAIN,
)


async def test_real_flow_setup_platforms_options_and_unload(hass, rig):
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
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COMMAND_MODE: "learned",
            CONF_DEVICE: "example",
            CONF_COMMAND: "beep",
            CONF_BEEP_ONLY: True,
        },
    )
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

    controller.armed, controller.dry_run = True, False
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    await hass.config_entries.options.async_configure(
        result["flow_id"], {**DEFAULTS, CONF_FALLBACK: True}
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is not controller
    assert not entry.runtime_data.armed and entry.runtime_data.dry_run

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
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COMMAND_MODE: "learned",
            CONF_DEVICE: "replacement",
            CONF_COMMAND: "beep",
            CONF_BEEP_ONLY: True,
        },
    )
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
