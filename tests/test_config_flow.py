"""Exercise the real wizard with registries and no hardware actions."""

from __future__ import annotations

import probatio
import pytest
import voluptuous as vol
from homeassistant.config_entries import SOURCE_USER
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from custom_components.bark_alerts.config_flow import BarkAlertsFlow, behavior_schema
from custom_components.bark_alerts.const import (
    CONF_BEEP_ONLY,
    CONF_BROADLINK,
    CONF_CAMERA,
    CONF_COMMAND,
    CONF_COMMAND_MODE,
    CONF_COOLDOWN,
    CONF_DEVICE,
    CONF_FALLBACK,
    CONF_REPEATS,
    CONF_RF_CODE,
    DEFAULTS,
    DOMAIN,
)

from .test_validation import packet


def flow(hass):
    instance = BarkAlertsFlow()
    instance.hass = hass
    instance.handler = DOMAIN
    instance.context = {"source": SOURCE_USER}
    return instance


async def command_step(hass, rig, mode="learned"):
    wizard = flow(hass)
    await wizard.async_step_user({CONF_CAMERA: rig.selected["camera"].entity_id})
    await wizard.async_step_broadlink({CONF_BROADLINK: rig.device.id})
    result = await wizard.async_step_command({CONF_COMMAND_MODE: mode})
    return wizard, result


def field(result, name):
    return result["data_schema"].schema[name]


async def test_camera_device_command_wizard_sends_nothing(hass, rig):
    wizard = flow(hass)
    assert (await wizard.async_step_user())["step_id"] == "user"
    result = await wizard.async_step_user(
        {CONF_CAMERA: rig.selected["camera"].entity_id}
    )
    assert result["step_id"] == "broadlink"
    result = await wizard.async_step_broadlink({CONF_BROADLINK: rig.device.id})
    assert result["step_id"] == "command"
    result = await wizard.async_step_command({CONF_COMMAND_MODE: "learned"})
    assert result["step_id"] == "learned_device"
    result = await wizard.async_step_learned_device({CONF_DEVICE: "Example collar"})
    assert result["step_id"] == "learned_command"
    result = await wizard.async_step_learned_command(
        {
            CONF_COMMAND: "beep",
            CONF_BEEP_ONLY: True,
        }
    )
    assert result["step_id"] == "behavior"
    result = await wizard.async_step_behavior(dict(DEFAULTS))
    assert result["type"] == "create_entry"
    assert result["options"][CONF_REPEATS] == 1
    assert result["data"][CONF_DEVICE] == "Example collar"
    assert CONF_RF_CODE not in result["data"]
    assert not rig.sends and not rig.learns


async def test_no_cameras_is_actionable(hass):
    assert (await flow(hass).async_step_user())["reason"] == "no_cameras"


@pytest.mark.parametrize("prefix", ["", "b64:"])
async def test_b1_raw_command_setup_sends_nothing(hass, rig, prefix):
    wizard, result = await command_step(hass, rig, "raw")
    assert result["step_id"] == "raw_command"
    assert set(result["data_schema"].schema) == {CONF_RF_CODE, CONF_BEEP_ONLY}
    result = await wizard.async_step_raw_command(
        {
            CONF_BEEP_ONLY: True,
            CONF_RF_CODE: prefix + packet(0xB1),
        }
    )
    assert result["step_id"] == "behavior"
    result = await wizard.async_step_behavior(dict(DEFAULTS))
    assert result["type"] == "create_entry"
    assert result["data"][CONF_RF_CODE] == "b64:" + packet(0xB1)
    assert not rig.sends and not rig.learns


async def test_missing_bark_does_not_borrow_another_camera(hass, rig):
    rig.registry.async_remove(rig.selected["bark"].entity_id)
    result = await flow(hass).async_step_user(
        {CONF_CAMERA: rig.selected["camera"].entity_id}
    )
    assert result["errors"] == {"base": "missing_bark"}


async def test_ir_only_broadlink_is_rejected(hass, rig):
    rig.registry.async_remove(rig.rf.entity_id)
    result = await flow(hass).async_step_broadlink({CONF_BROADLINK: rig.device.id})
    assert result["errors"] == {"base": "rf_not_supported"}


async def test_disabled_bark_is_rejected(hass, rig):
    rig.registry.async_update_entity(
        rig.selected["bark"].entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    result = await flow(hass).async_step_user(
        {CONF_CAMERA: rig.selected["camera"].entity_id}
    )
    assert result["errors"] == {"base": "missing_bark"}


async def test_fallback_requires_both_same_camera_sources(hass, rig):
    wizard, _ = await command_step(hass, rig)
    await wizard.async_step_learned_device({CONF_DEVICE: "example"})
    await wizard.async_step_learned_command(
        {
            CONF_COMMAND: "beep",
            CONF_BEEP_ONLY: True,
        }
    )
    rig.registry.async_remove(rig.selected["dog"].entity_id)
    result = await wizard.async_step_behavior({**DEFAULTS, CONF_FALLBACK: True})
    assert result["errors"] == {"base": "missing_fallback"}


@pytest.mark.parametrize("key,value", [(CONF_COOLDOWN, 0), (CONF_REPEATS, 100)])
def test_behavior_bounds(key, value):
    with pytest.raises((vol.Invalid, probatio.Invalid)):
        behavior_schema({})({**DEFAULTS, key: value})


async def test_named_command_uses_typed_names_only(hass, rig):
    wizard, result = await command_step(hass, rig)
    device = field(result, CONF_DEVICE)
    assert isinstance(device, selector.TextSelector)
    result = await wizard.async_step_learned_device({CONF_DEVICE: "Example collar"})
    command = field(result, CONF_COMMAND)
    assert isinstance(command, selector.TextSelector)
    assert not field(result, CONF_BEEP_ONLY)(False)
    result = await wizard.async_step_learned_command(
        {CONF_COMMAND: "beep", CONF_BEEP_ONLY: True}
    )
    result = await wizard.async_step_behavior(dict(DEFAULTS))
    assert result["data"][CONF_DEVICE] == "Example collar"
    assert result["data"][CONF_COMMAND] == "beep"
    assert not rig.sends and not rig.learns


async def test_typed_fields_allow_new_names(hass, rig):
    wizard, result = await command_step(hass, rig)
    result["data_schema"]({CONF_DEVICE: "New collar"})
    result = await wizard.async_step_learned_device({CONF_DEVICE: "New collar"})
    result["data_schema"]({CONF_COMMAND: "beep", CONF_BEEP_ONLY: True})
    result = await wizard.async_step_learned_command(
        {CONF_COMMAND: "beep", CONF_BEEP_ONLY: True}
    )
    assert result["step_id"] == "behavior"
    assert not rig.sends and not rig.learns


async def test_confirmation_error_keeps_typed_command_form(hass, rig):
    wizard, _ = await command_step(hass, rig)
    await wizard.async_step_learned_device({CONF_DEVICE: "Example"})
    result = await wizard.async_step_learned_command(
        {CONF_COMMAND: "beep", CONF_BEEP_ONLY: False}
    )
    assert result["errors"] == {"base": "beep_confirmation_required"}
    assert isinstance(field(result, CONF_COMMAND), selector.TextSelector)
    assert not rig.sends and not rig.learns


@pytest.mark.parametrize("value", ["", " ", "b64:invalid", "x" * 101, None])
async def test_invalid_device_name_does_not_advance(hass, rig, value):
    wizard, _ = await command_step(hass, rig)
    result = await wizard.async_step_learned_device({CONF_DEVICE: value})
    assert result["step_id"] == "learned_device"
    assert result["errors"] == {"base": "invalid_command"}
    assert not rig.sends and not rig.learns


async def test_raw_mode_never_prefills_private_code(hass, rig):
    wizard, result = await command_step(hass, rig, "raw")
    result = await wizard.async_step_raw_command(
        {CONF_RF_CODE: packet(), CONF_BEEP_ONLY: False}
    )
    assert result["errors"] == {"base": "beep_confirmation_required"}
    assert set(result["data_schema"].schema) == {CONF_RF_CODE, CONF_BEEP_ONLY}
    assert field(result, CONF_RF_CODE).config["type"] == "password"
    assert packet() not in repr(result)
    assert CONF_RF_CODE not in wizard._data
    assert not rig.sends and not rig.learns


async def test_switching_command_mode_discards_stale_private_code(hass, rig):
    wizard, _ = await command_step(hass, rig, "raw")
    await wizard.async_step_raw_command({CONF_RF_CODE: packet(), CONF_BEEP_ONLY: True})
    assert CONF_RF_CODE in wizard._data
    await wizard.async_step_command({CONF_COMMAND_MODE: "learned"})
    assert CONF_RF_CODE not in wizard._data and CONF_BEEP_ONLY not in wizard._data


async def test_invalid_mode_is_actionable(hass, rig):
    wizard, _ = await command_step(hass, rig)
    result = await wizard.async_step_command({CONF_COMMAND_MODE: "not-a-mode"})
    assert result["errors"] == {"base": "invalid_command_mode"}


async def test_new_entry_cannot_keep_a_command(hass, rig):
    wizard, _ = await command_step(hass, rig)
    result = await wizard.async_step_command({CONF_COMMAND_MODE: "keep"})
    assert result["errors"] == {"base": "invalid_command_mode"}
    assert "keep" not in field(result, CONF_COMMAND_MODE).config["options"]


async def test_changed_transmitter_cannot_reuse_saved_command(hass, rig):
    from .conftest import add_entry

    wizard = flow(hass)
    wizard._reconfigure = add_entry(
        hass,
        DOMAIN,
        data={
            CONF_BROADLINK: rig.device.id,
            CONF_COMMAND_MODE: "raw",
            CONF_RF_CODE: "b64:" + packet(),
            CONF_BEEP_ONLY: True,
        },
    )
    wizard._data[CONF_BROADLINK] = "another-transmitter"
    result = await wizard.async_step_command({CONF_COMMAND_MODE: "keep"})
    assert result["errors"] == {"base": "invalid_command_mode"}
    assert "keep" not in field(result, CONF_COMMAND_MODE).config["options"]
    assert CONF_RF_CODE not in wizard._data
