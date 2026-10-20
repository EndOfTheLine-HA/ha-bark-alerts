"""Explicit arming and dry-run controls; both reset safely on reload."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BarkAlertsConfigEntry
from .entity import BarkAlertsEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BarkAlertsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        BarkAlertsSwitch(entry.runtime_data, key) for key in ("armed", "dry_run")
    )


class BarkAlertsSwitch(BarkAlertsEntity, SwitchEntity):
    """Runtime opt-in: never arm from a remembered state on startup."""

    def __init__(self, controller, key: str) -> None:
        super().__init__(controller, key)
        self.key = key
        self._attr_icon = "mdi:shield-check" if key == "armed" else "mdi:test-tube"

    @property
    def is_on(self) -> bool:
        return getattr(self.controller, self.key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        setattr(self.controller, self.key, True)
        self.controller.async_notify()

    async def async_turn_off(self, **kwargs: Any) -> None:
        setattr(self.controller, self.key, False)
        self.controller.async_notify()
