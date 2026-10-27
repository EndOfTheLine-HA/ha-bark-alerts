"""Multi-camera behavior, opt-in testing and explicit dry-run warnings."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.bark_alerts.config_flow import BarkAlertsFlow
from custom_components.bark_alerts.const import (
    CONF_CAMERA,
    CONF_CAMERA_IDS,
    CONF_FALLBACK,
    CONF_HISTORY,
    DOMAIN,
)
from custom_components.bark_alerts.discovery import monitor_sources
from custom_components.bark_alerts.switch import BarkAlertsSwitch

from .test_controller import controller as controller_fixture
from .test_controller import edge

controller = controller_fixture


def include_both(hass, rig, controller):
    hass.config_entries.async_update_entry(
        controller.entry,
        data={
            **controller.entry.data,
            CONF_CAMERA_IDS: [rig.selected["camera"].id, rig.other["camera"].id],
        },
    )
    controller._bind_sources()


async def test_all_selected_cameras_share_one_cooldown(hass, rig, controller):
    include_both(hass, rig, controller)
    controller.armed = True
    await edge(hass, rig.selected["bark"])
    await edge(hass, rig.other["bark"])
    assert len(rig.sends) == 1 and controller.outcome == "cooldown"
    controller.test_clock[0] += 31
    await edge(hass, rig.other["bark"])
    assert len(rig.sends) == 2


async def test_simultaneous_camera_events_never_queue_second_send(
    hass, rig, controller
):
    include_both(hass, rig, controller)
    controller.armed = True
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_send(call):
        rig.sends.append(call)
        started.set()
        await release.wait()

    hass.services.async_register("remote", "send_command", slow_send)
    first = asyncio.create_task(
        controller.async_alert("bark", camera_id=rig.selected["camera"].id)
    )
    await started.wait()
    await controller.async_alert("bark", camera_id=rig.other["camera"].id)
    assert controller.outcome == "busy"
    release.set()
    await first
    assert len(rig.sends) == 1


async def test_fallback_never_borrows_dog_from_other_selected_camera(
    hass, rig, controller
):
    include_both(hass, rig, controller)
    hass.config_entries.async_update_entry(
        controller.entry, options={**controller.entry.options, CONF_FALLBACK: True}
    )
    controller._bind_sources()
    controller.armed = True
    await edge(hass, rig.selected["dog"])
    await edge(hass, rig.other["animal"])
    assert not rig.sends and controller.outcome == "dog_not_recent"
    await edge(hass, rig.other["dog"])
    await edge(hass, rig.other["animal"])
    assert len(rig.sends) == 1


async def test_disabled_camera_does_not_block_healthy_selected_camera(
    hass, rig, controller
):
    include_both(hass, rig, controller)
    controller.armed = True
    rig.registry.async_update_entity(
        rig.selected["camera"].entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    await edge(hass, rig.selected["bark"])
    assert not rig.sends
    assert controller.ready
    await edge(hass, rig.other["bark"])
    assert len(rig.sends) == 1


async def test_history_receives_triggering_camera_and_records_cooldown(
    hass, rig, controller
):
    include_both(hass, rig, controller)
    hass.config_entries.async_update_entry(
        controller.entry, options={**controller.entry.options, CONF_HISTORY: True}
    )
    from unittest.mock import Mock

    controller.history = SimpleNamespace(
        add=Mock(side_effect=["one", "two"]), outcome=Mock(), stop=lambda: None
    )
    controller.armed = True
    await edge(hass, rig.selected["bark"])
    await edge(hass, rig.other["bark"])
    assert [call.args[1] for call in controller.history.add.call_args_list] == [
        rig.selected["camera"].id,
        rig.other["camera"].id,
    ]
    assert controller.history.outcome.call_args.args == ("two", "cooldown")
    assert len(rig.sends) == 1


@pytest.mark.parametrize("first", ["armed", "dry_run"])
async def test_both_orders_warn_without_ending_dry_run(hass, rig, controller, first):
    second = "dry_run" if first == "armed" else "armed"
    with (
        patch(
            "custom_components.bark_alerts.controller.persistent_notification.async_create"
        ) as create,
        patch(
            "custom_components.bark_alerts.controller.persistent_notification.async_dismiss"
        ) as dismiss,
    ):
        await BarkAlertsSwitch(controller, first).async_turn_on()
        create.assert_not_called()
        await BarkAlertsSwitch(controller, second).async_turn_on()
        assert controller.armed and controller.dry_run
        create.assert_called_once()
        assert "Dry run is ON" in create.call_args.args[1]
        await edge(hass, rig.selected["bark"])
        assert not rig.sends and controller.outcome == "dry_run"
        await BarkAlertsSwitch(controller, "dry_run").async_turn_off()
        dismiss.assert_called_once()
        assert controller.armed and not controller.dry_run


async def test_disarm_and_unload_dismiss_test_warning(hass, controller):
    with (
        patch(
            "custom_components.bark_alerts.controller.persistent_notification.async_create"
        ),
        patch(
            "custom_components.bark_alerts.controller.persistent_notification.async_dismiss"
        ) as dismiss,
    ):
        controller.set_control("dry_run", True)
        controller.set_control("armed", True)
        controller.set_control("armed", False)
        assert dismiss.call_count == 1
        controller.set_control("armed", True)
        controller.async_stop()
        assert dismiss.call_count == 2


async def test_new_camera_selector_is_multiple_and_empty_is_rejected(hass, rig):
    wizard = BarkAlertsFlow()
    wizard.hass, wizard.handler, wizard.context = hass, DOMAIN, {"source": "user"}
    result = await wizard.async_step_user()
    assert result["data_schema"].schema[CONF_CAMERA].config["multiple"]
    result = await wizard.async_step_user({CONF_CAMERA: []})
    assert result["errors"] == {"base": "invalid_camera"}
    result = await wizard.async_step_user(
        {CONF_CAMERA: [rig.selected["camera"].entity_id, rig.other["camera"].entity_id]}
    )
    assert result["step_id"] == "broadlink"
    assert len(wizard._data[CONF_CAMERA_IDS]) == 2


async def test_legacy_entry_keeps_single_camera_and_starts_disabled(
    hass, rig, controller
):
    assert CONF_CAMERA_IDS not in controller.entry.data
    assert len(monitor_sources(hass, controller.entry.data)) == 1
    assert not controller.armed and not controller.dry_run
    await edge(hass, rig.other["bark"])
    assert not rig.sends


async def test_notification_reaches_ha_and_is_removed_when_disarmed(hass, controller):
    from homeassistant.components import persistent_notification

    updates = []
    unsubscribe = persistent_notification.async_register_callback(
        hass, lambda kind, notifications: updates.append((kind, notifications))
    )
    try:
        controller.set_control("dry_run", True)
        controller.set_control("armed", True)
        await hass.async_block_till_done()
        notification = next(iter(updates[0][1].values()))
        assert "Dry run is ON" in notification["message"]
        controller.set_control("armed", False)
        await hass.async_block_till_done()
        assert updates[-1][0] is persistent_notification.UpdateType.REMOVED
        assert len(updates) == 2
    finally:
        unsubscribe()
