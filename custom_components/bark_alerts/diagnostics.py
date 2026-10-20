"""Diagnostics deliberately exclude commands, codes, device IDs, and names."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from . import BarkAlertsConfigEntry
from .const import CONF_COMMAND_MODE, DEFAULTS, VERSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: BarkAlertsConfigEntry,
) -> dict:
    controller = entry.runtime_data
    return {
        "version": VERSION,
        "command_mode": entry.data[CONF_COMMAND_MODE],
        "settings": {key: controller.option(key) for key in DEFAULTS},
        "armed": controller.armed,
        "dry_run": controller.dry_run,
        "ready": controller.ready,
        "outcome": controller.outcome,
        "command_requests": controller.request_count,
        "dry_run_alerts": controller.dry_run_count,
    }
