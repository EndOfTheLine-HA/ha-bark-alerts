"""Exercise the real wizard with registries and no hardware actions."""

from __future__ import annotations

import probatio
import pytest
import voluptuous as vol
from homeassistant.config_entries import SOURCE_USER
from homeassistant.helpers import entity_registry as er

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
    DEFAULTS,
    DOMAIN,
)


def flow(hass):
    instance = BarkAlertsFlow()
    instance.hass = hass
    instance.handler = DOMAIN
    instance.context = {"source": SOURCE_USER}
    return instance


async def test_camera_device_command_wizard_sends_nothing(hass, rig):
    wizard = flow(hass)
    assert (await wizard.async_step_user())["step_id"] == "user"
    result = await wizard.async_step_user(
        {CONF_CAMERA: rig.selected["camera"].entity_id}
    )
    assert result["step_id"] == "broadlink"
    result = await wizard.async_step_broadlink({CONF_BROADLINK: rig.device.id})
    assert result["step_id"] == "command"
    result = await wizard.async_step_command(
        {
            CONF_COMMAND_MODE: "learned",
            CONF_DEVICE: "Example collar",
            CONF_COMMAND: "beep",
            CONF_BEEP_ONLY: True,
        }
    )
    assert result["step_id"] == "behavior"
    result = await wizard.async_step_behavior(dict(DEFAULTS))
    assert result["type"] == "create_entry"
    assert result["options"][CONF_REPEATS] == 1
    assert not rig.sends and not rig.learns


async def test_no_cameras_is_actionable(hass):
    assert (await flow(hass).async_step_user())["reason"] == "no_cameras"


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
    wizard = flow(hass)
    await wizard.async_step_user({CONF_CAMERA: rig.selected["camera"].entity_id})
    await wizard.async_step_broadlink({CONF_BROADLINK: rig.device.id})
    await wizard.async_step_command(
        {
            CONF_COMMAND_MODE: "learned",
            CONF_DEVICE: "example",
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
