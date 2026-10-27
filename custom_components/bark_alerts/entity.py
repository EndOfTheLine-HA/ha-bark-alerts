"""Common local monitor device and push updates."""

from __future__ import annotations

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, VERSION
from .controller import BarkAlertsController


class BarkAlertsEntity(Entity):
    """Base entity; never expose RF codes in state attributes."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, controller: BarkAlertsController, key: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name=controller.entry.title,
            manufacturer="EndOfTheLine-HA",
            model="Frigate / Broadlink bark alerts",
            sw_version=VERSION,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self.controller.signal, self.async_write_ha_state
            )
        )
