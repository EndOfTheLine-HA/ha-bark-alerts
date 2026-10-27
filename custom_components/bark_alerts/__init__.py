"""Generic Frigate bark alerts through an existing Broadlink RF remote."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_BROADLINK, CONF_FALLBACK, DEFAULTS, PLATFORMS
from .controller import BarkAlertsController
from .discovery import DiscoveryError, broadlink_remote, monitor_sources
from .history import BarkHistory
from .media_source import register_history_view

type BarkAlertsConfigEntry = ConfigEntry[BarkAlertsController]


async def async_setup_entry(hass: HomeAssistant, entry: BarkAlertsConfigEntry) -> bool:
    """Attach to existing entities; never send or learn during setup."""
    try:
        sources = monitor_sources(hass, entry.data, strict=False)
        remote = broadlink_remote(hass, entry.data[CONF_BROADLINK])
        if entry.options.get(CONF_FALLBACK, DEFAULTS[CONF_FALLBACK]) and not (
            all(source.animal_id and source.dog_id for source in sources)
        ):
            raise DiscoveryError("missing_fallback")
    except DiscoveryError as err:
        raise ConfigEntryNotReady(
            translation_domain="bark_alerts", translation_key=err.code
        ) from err
    controller = BarkAlertsController(hass, entry, sources, remote.id)
    entry.runtime_data = controller
    controller.history = BarkHistory(hass, entry, controller.async_notify)
    await controller.history.initialize()
    register_history_view(hass)
    controller.async_start()
    entry.async_on_unload(controller.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BarkAlertsConfigEntry) -> bool:
    """Detach listeners and cancel pending work when unloaded."""
    entry.runtime_data.async_stop()
    if entry.runtime_data.history:
        await entry.runtime_data.history.close()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: BarkAlertsConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
