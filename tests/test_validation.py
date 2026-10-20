"""Only synthetic packets; no learned collar codes belong in this repository."""

import base64

import pytest

from custom_components.bark_alerts.const import (
    CONF_BEEP_ONLY,
    CONF_COMMAND,
    CONF_COMMAND_MODE,
    CONF_DEVICE,
    CONF_RF_CODE,
)
from custom_components.bark_alerts.discovery import DiscoveryError
from custom_components.bark_alerts.validation import normalize_command


def packet(kind=0xB2):
    return base64.b64encode(bytes([kind, 0, 4, 0, 1, 2, 3, 4])).decode()


@pytest.mark.parametrize("kind", [0xB2, 0xB4, 0xD7])
@pytest.mark.parametrize("prefix", ["", "b64:"])
def test_rf_packet_modes(kind, prefix):
    result = normalize_command(
        {
            CONF_COMMAND_MODE: "raw",
            CONF_BEEP_ONLY: True,
            CONF_RF_CODE: prefix + packet(kind),
            CONF_DEVICE: "unused private group",
            CONF_COMMAND: "unused command",
        }
    )
    assert result[CONF_RF_CODE] == "b64:" + packet(kind)
    assert CONF_DEVICE not in result and CONF_COMMAND not in result


@pytest.mark.parametrize("code", ["", "garbage!!!", packet(0x26), "AA==", "A" * 9000])
def test_invalid_and_ir_packets_rejected(code):
    with pytest.raises(DiscoveryError, match="invalid_rf_code"):
        normalize_command(
            {CONF_COMMAND_MODE: "raw", CONF_BEEP_ONLY: True, CONF_RF_CODE: code}
        )


def test_named_mode_discards_old_raw_code():
    result = normalize_command(
        {
            CONF_COMMAND_MODE: "learned",
            CONF_BEEP_ONLY: True,
            CONF_DEVICE: " example ",
            CONF_COMMAND: " beep ",
            CONF_RF_CODE: "private stale code",
        }
    )
    assert result[CONF_DEVICE] == "example" and result[CONF_COMMAND] == "beep"
    assert CONF_RF_CODE not in result


@pytest.mark.parametrize("field", [CONF_DEVICE, CONF_COMMAND])
@pytest.mark.parametrize("value", ["", "   ", "b64:invalid", "x" * 101])
def test_invalid_names(field, value):
    with pytest.raises(DiscoveryError, match="invalid_command"):
        normalize_command(
            {
                CONF_COMMAND_MODE: "learned",
                CONF_BEEP_ONLY: True,
                CONF_DEVICE: "example",
                CONF_COMMAND: "beep",
                field: value,
            }
        )


def test_requires_explicit_beep_confirmation():
    with pytest.raises(DiscoveryError, match="beep_confirmation_required"):
        normalize_command({CONF_COMMAND_MODE: "raw", CONF_RF_CODE: packet()})
