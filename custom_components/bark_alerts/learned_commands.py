"""Read only the selected Broadlink's saved names; never write its storage."""

from __future__ import annotations

import json
import re
from pathlib import Path

from homeassistant.core import HomeAssistant

from .discovery import DiscoveryError, broadlink_remote
from .validation import normalize_command_name

# Broadlink has no public action for listing names. This is its HA 2026.10.2
# version-1 storage format. Unknown formats fall back to manual name entry.
CODE_STORAGE_VERSION = 1
MAX_STORAGE_BYTES = 16 * 1024 * 1024


def _usable_name(value: object) -> bool:
    """Do not offer names that normalization would change or reject."""
    try:
        return normalize_command_name(value) == value
    except DiscoveryError:
        return False


def _read_names(path: Path, key: str) -> dict[str, list[str]]:
    """Run in an executor; discard payloads before returning to the flow."""
    try:
        with path.open("rb") as storage:
            content = storage.read(MAX_STORAGE_BYTES + 1)
        if len(content) > MAX_STORAGE_BYTES:
            return {}
        document = json.loads(content)
    except OSError, ValueError, RecursionError:
        # No exception text or storage content goes into logs/flow errors.
        return {}
    if (
        not isinstance(document, dict)
        or document.get("version") != CODE_STORAGE_VERSION
        or document.get("key") != key
        or not isinstance(document.get("data"), dict)
    ):
        return {}

    names = {}
    for device, commands in document["data"].items():
        if not _usable_name(device) or not isinstance(commands, dict):
            continue
        available = [
            name
            for name, code in commands.items()
            if _usable_name(name)
            and (
                isinstance(code, str)
                and bool(code)
                or isinstance(code, list)
                and bool(code)
                and all(isinstance(item, str) and bool(item) for item in code)
            )
        ]
        if available:
            names[device] = sorted(available, key=lambda name: (name.casefold(), name))
    return dict(sorted(names.items(), key=lambda item: (item[0].casefold(), item[0])))


async def async_learned_commands(
    hass: HomeAssistant, device_id: str
) -> dict[str, list[str]]:
    """Load a names-only catalog scoped by the selected remote's registry ID."""
    remote = broadlink_remote(hass, device_id)
    if re.fullmatch(r"[0-9a-f]{12}", remote.unique_id) is None:
        return {}
    key = f"broadlink_remote_{remote.unique_id}_codes"
    path = Path(hass.config.path(".storage", key))
    return await hass.async_add_executor_job(_read_names, path, key)
