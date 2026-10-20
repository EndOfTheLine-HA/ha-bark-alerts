"""Isolated HA registries and fake services: never connect to real hardware."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


def add_entry(hass, domain, *, data=None, options=None, unique_id=None):
    entry = ConfigEntry(
        domain=domain,
        title=f"Test {domain}",
        data=data or {},
        options=options or {},
        source="user",
        unique_id=unique_id,
        version=1,
        minor_version=1,
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    # Insert without setting up real Frigate or Broadlink integrations.
    hass.config_entries._entries[entry.entry_id] = entry
    return entry


@pytest.fixture
async def hass(tmp_path):
    source = Path(__file__).parents[1] / "custom_components" / "bark_alerts"
    shutil.copytree(
        source,
        tmp_path / "custom_components" / "bark_alerts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = ConfigEntries(instance, {})
    loader.async_setup(instance)
    dr.async_setup(instance)
    await dr.async_load(instance, load_empty=True)
    await er.async_load(instance, load_empty=True)
    yield instance
    await instance.async_stop(force=True)


@pytest.fixture
async def rig(hass):
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    frigate = add_entry(hass, "frigate")
    broadlink = add_entry(hass, "broadlink")

    def camera(key):
        device = devices.async_get_or_create(
            config_entry_id=frigate.entry_id,
            identifiers={("frigate", f"{frigate.entry_id}:{key}")},
            name=key,
        )
        result = {}
        for label, domain, kind in (
            ("camera", "camera", "camera"),
            ("bark", "binary_sensor", "audio_sensor"),
            ("animal", "binary_sensor", "audio_sensor"),
            ("dog", "binary_sensor", "occupancy_sensor"),
        ):
            name = key if label == "camera" else f"{key}_{label}"
            entity = registry.async_get_or_create(
                domain,
                "frigate",
                f"{frigate.entry_id}:{kind}:{name}",
                config_entry=frigate,
                device_id=device.id,
                suggested_object_id=name,
            )
            hass.states.async_set(
                entity.entity_id, "idle" if domain == "camera" else "off"
            )
            result[label] = entity
        return result

    selected, other = camera("example_yard"), camera("other_yard")
    device = devices.async_get_or_create(
        config_entry_id=broadlink.entry_id,
        identifiers={("broadlink", "000000000001")},
        name="Example RF transmitter",
    )
    remote = registry.async_get_or_create(
        "remote",
        "broadlink",
        "000000000001",
        config_entry=broadlink,
        device_id=device.id,
        suggested_object_id="example_remote",
    )
    rf = registry.async_get_or_create(
        "radio_frequency",
        "broadlink",
        "000000000001",
        config_entry=broadlink,
        device_id=device.id,
    )
    hass.states.async_set(remote.entity_id, "on")
    sends, learns = [], []

    async def send(call):
        sends.append(call)

    async def learn(call):
        learns.append(call)

    hass.services.async_register("remote", "send_command", send)
    hass.services.async_register("remote", "learn_command", learn)
    await hass.async_block_till_done()
    return SimpleNamespace(
        selected=selected,
        other=other,
        device=device,
        remote=remote,
        rf=rf,
        sends=sends,
        learns=learns,
        registry=registry,
        frigate=frigate,
    )


@pytest.fixture
def learned_storage(hass):
    """Synthetic storage only, never read the user's HA storage or RF packets."""

    def save(data, unique_id="000000000001"):
        key = f"broadlink_remote_{unique_id}_codes"
        path = Path(hass.config.path(".storage", key))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "minor_version": 1, "key": key, "data": data}),
            encoding="utf-8",
        )
        return path

    return save
