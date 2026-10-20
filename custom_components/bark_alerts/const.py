"""Constants for Bark Alerts."""

from homeassistant.const import Platform

DOMAIN = "bark_alerts"
VERSION = "0.1.0"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

CONF_CAMERA = "camera"
CONF_CAMERA_ID = "camera_registry_id"
CONF_BROADLINK = "broadlink_device"
CONF_COMMAND_MODE = "command_mode"
CONF_DEVICE = "command_device"
CONF_COMMAND = "beep_command"
CONF_RF_CODE = "rf_code"
CONF_BEEP_ONLY = "beep_only_confirmed"
CONF_COOLDOWN = "cooldown"
CONF_FALLBACK = "animal_fallback"
CONF_DOG_WINDOW = "dog_window"
CONF_REPEATS = "repeats"
CONF_DELAY = "repeat_delay"

MODE_LEARNED = "learned"
MODE_RAW = "raw"
DEFAULTS = {
    CONF_COOLDOWN: 30,
    CONF_FALLBACK: False,
    CONF_DOG_WINDOW: 300,
    CONF_REPEATS: 1,
    CONF_DELAY: 1,
}

OUTCOMES = (
    "idle",
    "disarmed",
    "dry_run",
    "command_requested",
    "cooldown",
    "busy",
    "dog_not_recent",
    "source_unavailable",
    "remote_unavailable",
    "error",
    "learning_requested",
)
