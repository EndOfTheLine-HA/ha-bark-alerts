"""Non-sensitive alert outcomes and timestamps."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BarkAlertsConfigEntry
from .const import OUTCOMES
from .entity import BarkAlertsEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BarkAlertsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        BarkAlertsSensor(entry.runtime_data, key)
        for key in ("outcome", "last_detection", "last_request")
    )


class BarkAlertsSensor(BarkAlertsEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller, key: str) -> None:
        super().__init__(controller, key)
        self.key = key
        self._attr_device_class = (
            SensorDeviceClass.ENUM if key == "outcome" else SensorDeviceClass.TIMESTAMP
        )
        if key == "outcome":
            self._attr_options = list(OUTCOMES)

    @property
    def native_value(self):
        return getattr(self.controller, self.key)

    @property
    def extra_state_attributes(self):
        if self.key == "outcome":
            return {
                "command_requests": self.controller.request_count,
                "dry_run_alerts": self.controller.dry_run_count,
            }
        return None
