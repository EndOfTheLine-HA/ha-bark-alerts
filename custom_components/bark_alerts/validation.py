"""Validate user-owned command configuration without sending anything."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from .const import (
    CONF_BEEP_ONLY,
    CONF_COMMAND,
    CONF_COMMAND_MODE,
    CONF_DEVICE,
    CONF_RF_CODE,
    MODE_LEARNED,
    MODE_RAW,
)
from .discovery import DiscoveryError


def normalize_command_name(value: Any) -> str:
    """Validate one named-command component, not an RF packet."""
    if not isinstance(value, str):
        raise DiscoveryError("invalid_command")
    value = value.strip()
    if not value or len(value) > 100 or value.startswith("b64:"):
        raise DiscoveryError("invalid_command")
    return value


def normalize_command(data: dict[str, Any]) -> dict[str, Any]:
    """Keep only the chosen mode's fields, excluding stale private codes."""
    if data.get(CONF_BEEP_ONLY) is not True:
        raise DiscoveryError("beep_confirmation_required")
    mode = data.get(CONF_COMMAND_MODE)
    result = {CONF_COMMAND_MODE: mode, CONF_BEEP_ONLY: True}
    if mode == MODE_LEARNED:
        for key in (CONF_DEVICE, CONF_COMMAND):
            result[key] = normalize_command_name(data.get(key))
        return result
    if mode != MODE_RAW:
        raise DiscoveryError("invalid_command")
    code = str(data.get(CONF_RF_CODE, "")).strip()
    if code.startswith("b64:"):
        code = code[4:]
    if not code or len(code) > 8192:
        raise DiscoveryError("invalid_rf_code")
    try:
        packet = base64.b64decode(code, validate=True)
    except (ValueError, binascii.Error) as err:
        raise DiscoveryError("invalid_rf_code") from err
    if (
        len(packet) < 8
        or len(packet) > 4096
        or packet[0] not in (0xB1, 0xB2, 0xB4, 0xD7)
        or not 2 <= int.from_bytes(packet[2:4], "little") <= len(packet) - 4
    ):
        raise DiscoveryError("invalid_rf_code")
    result[CONF_RF_CODE] = f"b64:{code}"
    return result
