"""Only explicit button presses can initiate a manual send or RF learning."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BarkAlertsConfigEntry
from .const import CONF_COMMAND_MODE, MODE_LEARNED
from .entity import BarkAlertsEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BarkAlertsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    keys = ["test_beep"]
    if entry.data[CONF_COMMAND_MODE] == MODE_LEARNED:
        keys.append("learn_beep")
    async_add_entities(BarkAlertsButton(entry.runtime_data, key) for key in keys)


class BarkAlertsButton(BarkAlertsEntity, ButtonEntity):
    """A clearly labelled physical-test button and receive-only learning button."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller, key: str) -> None:
        super().__init__(controller, key)
        self.key = key
        self._attr_icon = "mdi:volume-high" if key == "test_beep" else "mdi:remote"

    async def async_press(self) -> None:
        if self.key == "test_beep":
            await self.controller.async_alert(
                "manual", manual=True, context=self._context
            )
        else:
            await self.controller.async_learn(context=self._context)
