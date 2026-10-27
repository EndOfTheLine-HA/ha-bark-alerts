"""Resolve Frigate and Broadlink sources without guessing entity names."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_CAMERA_ID, CONF_CAMERA_IDS


class DiscoveryError(ValueError):
    """A translated, non-sensitive configuration error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CameraSources:
    """Registry IDs survive entity renames."""

    camera_id: str
    name: str
    bark_id: str
    animal_id: str | None
    dog_id: str | None


def selected_camera_ids(data: dict) -> list[str]:
    """Read multi-camera entries and older single-camera entries."""
    if CONF_CAMERA_IDS in data:
        return data[CONF_CAMERA_IDS]
    return [data[CONF_CAMERA_ID]]


def monitor_sources(
    hass: HomeAssistant, data: dict, *, strict: bool = True
) -> list[CameraSources]:
    """Validate every selected camera without borrowing another's sensors."""
    result = []
    for key in selected_camera_ids(data):
        try:
            result.append(camera_sources(hass, key))
        except DiscoveryError:
            if strict:
                raise
    if not result:
        raise DiscoveryError("invalid_camera")
    return result


def camera_sources(hass: HomeAssistant, camera_id: str) -> CameraSources:
    """Find only sensors belonging to the selected Frigate camera."""
    registry = er.async_get(hass)
    camera = registry.async_get(camera_id)
    if (
        camera is None
        or camera.domain != "camera"
        or camera.platform != "frigate"
        or camera.disabled_by is not None
        or camera.device_id is None
        or camera.config_entry_id is None
    ):
        raise DiscoveryError("invalid_camera")
    prefix = f"{camera.config_entry_id}:camera:"
    if not camera.unique_id.startswith(prefix):
        raise DiscoveryError("unsupported_camera")
    camera_key = camera.unique_id[len(prefix) :]
    if not camera_key or camera_key == "birdseye":
        raise DiscoveryError("unsupported_camera")

    def find(kind: str, label: str) -> str | None:
        unique_id = f"{camera.config_entry_id}:{kind}:{camera_key}_{label}"
        entity_id = registry.async_get_entity_id("binary_sensor", "frigate", unique_id)
        sensor = registry.async_get(entity_id) if entity_id else None
        if (
            sensor is not None
            and sensor.device_id == camera.device_id
            and sensor.config_entry_id == camera.config_entry_id
            and sensor.disabled_by is None
        ):
            return sensor.id
        return None

    bark = find("audio_sensor", "bark")
    if bark is None:
        raise DiscoveryError("missing_bark")
    return CameraSources(
        camera.id,
        camera.name or camera.original_name or camera_key,
        bark,
        find("audio_sensor", "animal"),
        find("occupancy_sensor", "dog"),
    )


def broadlink_remote(hass: HomeAssistant, device_id: str) -> er.RegistryEntry:
    """Require an RF-capable Broadlink device, not an IR-only mini."""
    registry = er.async_get(hass)
    entities = er.async_entries_for_device(registry, device_id)
    remotes = [
        entity
        for entity in entities
        if entity.platform == "broadlink"
        and entity.domain == "remote"
        and entity.disabled_by is None
    ]
    if len(remotes) != 1:
        raise DiscoveryError("invalid_broadlink")
    if not any(
        entity.platform == "broadlink" and entity.domain == "radio_frequency"
        for entity in entities
    ):
        raise DiscoveryError("rf_not_supported")
    return remotes[0]


def entity_id(hass: HomeAssistant, registry_id: str | None) -> str | None:
    """Resolve the current entity ID of an enabled registry entry."""
    entity = er.async_get(hass).async_get(registry_id) if registry_id else None
    return entity.entity_id if entity and entity.disabled_by is None else None
