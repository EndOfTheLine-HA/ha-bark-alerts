"""Real HA state events, fake Broadlink services, and an injected monotonic clock."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.bark_alerts.const import (
    CONF_BEEP_ONLY,
    CONF_BROADLINK,
    CONF_CAMERA_ID,
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
from custom_components.bark_alerts.controller import BarkAlertsController
from custom_components.bark_alerts.diagnostics import async_get_config_entry_diagnostics
from custom_components.bark_alerts.discovery import camera_sources

from .conftest import add_entry


@pytest.fixture
async def controller(hass, rig):
    entry = add_entry(
        hass,
        DOMAIN,
        data={
            CONF_CAMERA_ID: rig.selected["camera"].id,
            CONF_BROADLINK: rig.device.id,
            CONF_COMMAND_MODE: "learned",
            CONF_DEVICE: "private collar group",
            CONF_COMMAND: "private beep",
            CONF_BEEP_ONLY: True,
        },
        options=dict(DEFAULTS),
    )
    clock = [1000.0]
    result = BarkAlertsController(
        hass,
        entry,
        camera_sources(hass, rig.selected["camera"].id),
        rig.remote.id,
        clock=lambda: clock[0],
    )
    entry.runtime_data = result
    result.test_clock = clock
    result.async_start()
    await hass.async_block_till_done()
    yield result
    result.async_stop()
    await hass.async_block_till_done()


async def edge(hass, entity):
    hass.states.async_set(entity.entity_id, "off")
    await hass.async_block_till_done()
    hass.states.async_set(entity.entity_id, "on")
    await hass.async_block_till_done()


async def test_new_entry_disarmed_and_dry_run(hass, rig, controller):
    assert controller.armed is False and controller.dry_run is False
    await edge(hass, rig.selected["bark"])
    assert controller.outcome == "disarmed"
    assert not rig.sends


async def test_dry_run_never_sends(hass, rig, controller):
    controller.dry_run = True
    controller.armed = True
    await edge(hass, rig.selected["bark"])
    assert controller.outcome == "dry_run" and controller.dry_run_count == 1
    assert not rig.sends


async def test_actual_request_has_one_selected_remote_and_bounded_repeats(
    hass, rig, controller
):
    controller.armed, controller.dry_run = True, False
    await edge(hass, rig.selected["bark"])
    assert len(rig.sends) == 1
    assert rig.sends[0].data == {
        "entity_id": rig.remote.entity_id,
        "command": ["private beep"],
        "device": "private collar group",
        "num_repeats": 1,
        "delay_secs": 1,
    }
    assert controller.outcome == "command_requested"
    assert controller.last_request is not None


@pytest.mark.parametrize("mode", ["learned", "raw"])
@pytest.mark.parametrize("source", ["bark", "animal", "manual"])
async def test_two_repetitions_use_one_request_for_each_command_and_trigger(
    hass, rig, controller, mode, source
):
    from .test_validation import packet

    data = dict(controller.entry.data)
    if mode == "raw":
        data.pop(CONF_DEVICE)
        data.pop(CONF_COMMAND)
        data.update({CONF_COMMAND_MODE: mode, CONF_RF_CODE: "b64:" + packet()})
    hass.config_entries.async_update_entry(
        controller.entry,
        data=data,
        options={
            **DEFAULTS,
            CONF_REPEATS: 2,
            CONF_DELAY: 2,
            CONF_FALLBACK: source == "animal",
        },
    )
    # The manual button deliberately works while disarmed and in dry run.
    controller.armed, controller.dry_run = source != "manual", source == "manual"
    if source == "manual":
        await controller.async_alert(source, manual=True)
    else:
        if source == "animal":
            await edge(hass, rig.selected["dog"])
        await edge(hass, rig.selected[source])

    expected = {
        "entity_id": rig.remote.entity_id,
        "num_repeats": 2,
        "delay_secs": 2,
        "command": [data[CONF_RF_CODE] if mode == "raw" else data[CONF_COMMAND]],
    }
    if mode == "learned":
        expected["device"] = data[CONF_DEVICE]
    assert len(rig.sends) == 1
    assert rig.sends[0].data == expected
    # Count service requests, not repetitions or confirmed audible beeps.
    assert controller.request_count == 1 and controller.dry_run_count == 0
    assert controller.outcome == "command_requested"
    assert (controller.last_detection is None) == (source == "manual")

    if source == "manual":
        with pytest.raises(HomeAssistantError):
            await controller.async_alert(source, manual=True)
    else:
        await edge(hass, rig.selected[source])
    assert controller.outcome == "cooldown"
    assert len(rig.sends) == 1 and controller.request_count == 1


async def test_two_repetitions_do_not_bypass_dry_run(hass, rig, controller):
    controller.dry_run = True
    hass.config_entries.async_update_entry(
        controller.entry, options={**DEFAULTS, CONF_REPEATS: 2, CONF_DELAY: 2}
    )
    controller.armed = True
    await edge(hass, rig.selected["bark"])
    assert controller.outcome == "dry_run"
    assert controller.dry_run_count == 1 and controller.request_count == 0
    assert not rig.sends


async def test_arming_does_not_replay_a_detection_from_while_disarmed(
    hass, rig, controller
):
    hass.config_entries.async_update_entry(
        controller.entry, options={**DEFAULTS, CONF_REPEATS: 2, CONF_DELAY: 2}
    )
    await edge(hass, rig.selected["bark"])
    assert controller.outcome == "disarmed" and not rig.sends
    controller.armed, controller.dry_run = True, False
    controller.async_notify()
    await hass.async_block_till_done()
    assert not rig.sends
    hass.states.async_set(rig.selected["bark"].entity_id, "on", {"updated": True})
    await hass.async_block_till_done()
    assert not rig.sends
    await edge(hass, rig.selected["bark"])
    assert len(rig.sends) == 1
    assert rig.sends[0].data["num_repeats"] == 2
    assert controller.request_count == 1


async def test_cooldown_discards_duplicate_without_queue(hass, rig, controller):
    controller.armed, controller.dry_run = True, False
    await edge(hass, rig.selected["bark"])
    await edge(hass, rig.selected["bark"])
    assert len(rig.sends) == 1 and controller.outcome == "cooldown"
    controller.test_clock[0] += 31
    await hass.async_block_till_done()
    assert len(rig.sends) == 1
    await edge(hass, rig.selected["bark"])
    assert len(rig.sends) == 2


@pytest.mark.parametrize("before", [None, "unavailable", "unknown", "on"])
async def test_startup_recovery_and_attribute_updates_do_not_send(
    hass, rig, controller, before
):
    controller.armed, controller.dry_run = True, False
    key = rig.selected["bark"].entity_id
    if before is None:
        hass.states.async_remove(key)
    else:
        hass.states.async_set(key, before)
    await hass.async_block_till_done()
    rig.sends.clear()
    controller.test_clock[0] += 31
    hass.states.async_set(key, "on", {"new_attribute": True})
    await hass.async_block_till_done()
    assert not rig.sends


async def test_other_camera_never_triggers(hass, rig, controller):
    controller.armed, controller.dry_run = True, False
    await edge(hass, rig.other["bark"])
    assert not rig.sends


async def test_same_camera_dog_gate_and_expiry(hass, rig, controller):
    controller.armed, controller.dry_run = True, False
    hass.config_entries.async_update_entry(
        controller.entry, options={**DEFAULTS, CONF_FALLBACK: True}
    )
    await edge(hass, rig.other["dog"])
    await edge(hass, rig.selected["animal"])
    assert not rig.sends and controller.outcome == "dog_not_recent"
    await edge(hass, rig.selected["dog"])
    await edge(hass, rig.selected["animal"])
    assert len(rig.sends) == 1
    hass.states.async_set(rig.selected["dog"].entity_id, "off")
    await hass.async_block_till_done()
    controller.test_clock[0] += 301
    await edge(hass, rig.selected["animal"])
    assert len(rig.sends) == 1 and controller.outcome == "dog_not_recent"


async def test_retained_dog_on_is_not_new_presence(hass, rig, controller):
    controller.armed = True
    hass.config_entries.async_update_entry(
        controller.entry, options={**DEFAULTS, CONF_FALLBACK: True}
    )
    hass.states.async_set(rig.selected["dog"].entity_id, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(rig.selected["dog"].entity_id, "on")
    await hass.async_block_till_done()
    await edge(hass, rig.selected["animal"])
    assert controller.outcome == "dog_not_recent"


@pytest.mark.parametrize("state", ["off", "unavailable", "unknown"])
async def test_remote_not_ready_never_sends(hass, rig, controller, state):
    controller.armed, controller.dry_run = True, False
    hass.states.async_set(rig.remote.entity_id, state)
    await edge(hass, rig.selected["bark"])
    assert not controller.ready and not rig.sends
    assert controller.outcome == "remote_unavailable"


async def test_entity_renames_follow_registry_ids(hass, rig, controller):
    controller.armed, controller.dry_run = True, False
    bark = rig.registry.async_update_entity(
        rig.selected["bark"].entity_id, new_entity_id="binary_sensor.renamed_bark"
    )
    remote = rig.registry.async_update_entity(
        rig.remote.entity_id, new_entity_id="remote.renamed_rf"
    )
    hass.states.async_set(remote.entity_id, "on")
    await hass.async_block_till_done()
    await edge(hass, bark)
    assert rig.sends[0].data["entity_id"] == remote.entity_id


async def test_failure_is_private_and_not_retried(hass, rig, controller, caplog):
    controller.armed, controller.dry_run = True, False
    with patch.object(
        type(hass.services),
        "async_call",
        side_effect=HomeAssistantError("PRIVATE_RF_CODE"),
    ):
        await controller.async_alert("bark")
    assert controller.outcome == "error" and controller.request_count == 0
    assert "PRIVATE_RF_CODE" not in caplog.text
    assert not rig.sends


async def test_inflight_event_is_dropped(hass, rig, controller):
    controller.armed, controller.dry_run = True, False
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_send(call):
        rig.sends.append(call)
        started.set()
        await release.wait()

    hass.services.async_register("remote", "send_command", slow_send)
    first = asyncio.create_task(controller.async_alert("bark"))
    await started.wait()
    await controller.async_alert("bark")
    assert controller.outcome == "busy"
    release.set()
    await first
    assert len(rig.sends) == 1


async def test_manual_test_is_explicit_even_in_dry_run(hass, rig, controller):
    controller.dry_run = True
    assert not controller.armed and controller.dry_run
    await controller.async_alert("manual", manual=True)
    assert len(rig.sends) == 1
    with pytest.raises(HomeAssistantError):
        await controller.async_alert("manual", manual=True)
    assert len(rig.sends) == 1


async def test_learn_uses_native_rf_receive_only(hass, rig, controller):
    await controller.async_learn()
    assert not rig.sends and len(rig.learns) == 1
    assert rig.learns[0].data["command_type"] == "rf"
    assert controller.outcome == "learning_requested"


async def test_unload_removes_listener(hass, rig, controller):
    controller.armed, controller.dry_run = True, False
    controller.async_stop()
    await edge(hass, rig.selected["bark"])
    await controller.async_alert("bark")
    assert not rig.sends


async def test_diagnostics_exclude_identifiers_and_commands(hass, rig, controller):
    result = str(await async_get_config_entry_diagnostics(hass, controller.entry))
    for private in (
        "private collar group",
        "private beep",
        rig.device.id,
        rig.remote.entity_id,
        rig.selected["camera"].entity_id,
    ):
        assert private not in result


async def test_raw_code_is_sent_only_to_selected_remote(hass, rig, controller):
    from custom_components.bark_alerts.const import CONF_RF_CODE

    from .test_validation import packet

    code = "b64:" + packet()
    hass.config_entries.async_update_entry(
        controller.entry,
        data={
            CONF_CAMERA_ID: rig.selected["camera"].id,
            CONF_BROADLINK: rig.device.id,
            CONF_COMMAND_MODE: "raw",
            CONF_RF_CODE: code,
            CONF_BEEP_ONLY: True,
        },
    )
    await controller.async_alert("manual", manual=True)
    assert rig.sends[0].data["command"] == [code]
    assert "device" not in rig.sends[0].data
    assert code not in str(
        await async_get_config_entry_diagnostics(hass, controller.entry)
    )
    with pytest.raises(HomeAssistantError):
        await controller.async_learn()


async def test_removed_or_disabled_source_blocks_alerts(hass, rig, controller):
    from homeassistant.helpers import entity_registry as er

    controller.armed, controller.dry_run = True, False
    rig.registry.async_update_entity(
        rig.selected["camera"].entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    await edge(hass, rig.selected["bark"])
    assert not rig.sends and not controller.ready
    assert controller.outcome == "source_unavailable"


async def test_stopping_cancels_pending_operation(hass, rig, controller):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_send(call):
        started.set()
        await release.wait()

    hass.services.async_register("remote", "send_command", slow_send)
    task = asyncio.create_task(controller.async_alert("manual", manual=True))
    await started.wait()
    controller.async_stop()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert not controller.armed


@pytest.mark.parametrize("source", ["bark", "animal"])
@pytest.mark.parametrize("require_dog", [True, False])
async def test_visual_requirement_is_independent_of_bark_detection(
    hass, rig, controller, source, require_dog
):
    from custom_components.bark_alerts.const import CONF_REQUIRE_DOG

    hass.config_entries.async_update_entry(
        controller.entry,
        options={**DEFAULTS, CONF_FALLBACK: True, CONF_REQUIRE_DOG: require_dog},
    )
    controller._bind_sources()
    controller.armed = True
    await edge(hass, rig.selected[source])
    should_send = source == "bark" or not require_dog
    assert len(rig.sends) == int(should_send)
    assert controller.outcome == (
        "command_requested" if should_send else "dog_not_recent"
    )


@pytest.mark.parametrize("gate", ["disarmed", "dry_run", "cooldown"])
async def test_audio_only_fallback_still_respects_monitor_controls(
    hass, rig, controller, gate
):
    from custom_components.bark_alerts.const import CONF_REQUIRE_DOG

    hass.config_entries.async_update_entry(
        controller.entry,
        options={**DEFAULTS, CONF_FALLBACK: True, CONF_REQUIRE_DOG: False},
    )
    rig.registry.async_remove(rig.selected["dog"].entity_id)
    await hass.async_block_till_done()
    controller._bind_sources()
    assert controller.ready
    controller.armed = gate != "disarmed"
    controller.dry_run = gate == "dry_run"
    if gate == "cooldown":
        await edge(hass, rig.selected["animal"])
        assert len(rig.sends) == 1
    count = len(rig.sends)
    await edge(hass, rig.selected["animal"])
    assert len(rig.sends) == count
    assert controller.outcome == gate


async def test_legacy_options_keep_visual_requirement(hass, rig, controller):
    from custom_components.bark_alerts.const import CONF_REQUIRE_DOG

    options = {**DEFAULTS, CONF_FALLBACK: True}
    options.pop(CONF_REQUIRE_DOG)
    hass.config_entries.async_update_entry(controller.entry, options=options)
    controller._bind_sources()
    controller.armed = True
    await edge(hass, rig.selected["animal"])
    assert not rig.sends and controller.outcome == "dog_not_recent"


async def test_animal_fallback_off_ignores_animal_even_without_visual_requirement(
    hass, rig, controller
):
    from custom_components.bark_alerts.const import CONF_REQUIRE_DOG

    hass.config_entries.async_update_entry(
        controller.entry,
        options={**DEFAULTS, CONF_FALLBACK: False, CONF_REQUIRE_DOG: False},
    )
    controller._bind_sources()
    controller.armed = True
    await edge(hass, rig.selected["animal"])
    assert not rig.sends
