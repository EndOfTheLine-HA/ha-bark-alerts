"""Camera → Broadlink device → user's beep command; no setup transmissions."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_BEEP_ONLY,
    CONF_BROADLINK,
    CONF_CAMERA,
    CONF_CAMERA_ID,
    CONF_COMMAND,
    CONF_COMMAND_MODE,
    CONF_COOLDOWN,
    CONF_DELAY,
    CONF_DEVICE,
    CONF_DOG_WINDOW,
    CONF_FALLBACK,
    CONF_REPEATS,
    CONF_RF_CODE,
    DEFAULTS,
    DOMAIN,
    MODE_LEARNED,
    MODE_RAW,
)
from .discovery import DiscoveryError, broadlink_remote, camera_sources
from .validation import normalize_command


def behavior_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Bound repeat counts and cooldowns instead of allowing event storms."""
    fields = {}
    for key, minimum, maximum in (
        (CONF_COOLDOWN, 5, 3600),
        (CONF_DOG_WINDOW, 5, 1800),
        (CONF_REPEATS, 1, 3),
        (CONF_DELAY, 1, 5),
    ):
        fields[vol.Required(key, default=defaults.get(key, DEFAULTS[key]))] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=minimum,
                    max=maximum,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        )
    fields[vol.Required(CONF_FALLBACK, default=defaults.get(CONF_FALLBACK, False))] = (
        selector.BooleanSelector()
    )
    return vol.Schema(fields)


class BarkAlertsFlow(ConfigFlow, domain=DOMAIN):
    """Pair a camera with one existing RF-capable Broadlink device."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = dict(DEFAULTS)
        self._reconfigure: ConfigEntry | None = None

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        registry = er.async_get(self.hass)
        cameras = [
            entity.entity_id
            for entity in registry.entities.values()
            if entity.domain == "camera"
            and entity.platform == "frigate"
            and entity.disabled_by is None
        ]
        if not cameras:
            return self.async_abort(reason="no_cameras")
        errors = {}
        if user_input is not None:
            try:
                sources = camera_sources(self.hass, user_input[CONF_CAMERA])
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                self._data[CONF_CAMERA_ID] = sources.camera_id
                return await self.async_step_broadlink()
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CAMERA): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="camera",
                            integration="frigate",
                            include_entities=cameras,
                        )
                    )
                }
            ),
        )

    async def async_step_broadlink(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                broadlink_remote(self.hass, user_input[CONF_BROADLINK])
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                self._data[CONF_BROADLINK] = user_input[CONF_BROADLINK]
                pair_id = f"{self._data[CONF_CAMERA_ID]}:{user_input[CONF_BROADLINK]}"
                await self.async_set_unique_id(pair_id)
                if any(
                    entry.unique_id == pair_id
                    and (
                        self._reconfigure is None
                        or entry.entry_id != self._reconfigure.entry_id
                    )
                    for entry in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")
                return await self.async_step_command()
        return self.async_show_form(
            step_id="broadlink",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BROADLINK): selector.DeviceSelector(
                        selector.DeviceSelectorConfig(integration="broadlink")
                    )
                }
            ),
        )

    async def async_step_command(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                command = normalize_command(user_input)
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                self._data.update(command)
                return await self.async_step_behavior()
        # Never prefill a private raw code, including on a failed submission.
        return self.async_show_form(
            step_id="command",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COMMAND_MODE, default=MODE_LEARNED
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[MODE_LEARNED, MODE_RAW],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="command_mode",
                        )
                    ),
                    vol.Optional(CONF_DEVICE): selector.TextSelector(),
                    vol.Optional(CONF_COMMAND): selector.TextSelector(),
                    vol.Optional(CONF_RF_CODE): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        CONF_BEEP_ONLY, default=False
                    ): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_behavior(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                sources = camera_sources(self.hass, self._data[CONF_CAMERA_ID])
                broadlink_remote(self.hass, self._data[CONF_BROADLINK])
                if user_input[CONF_FALLBACK] and not (
                    sources.animal_id and sources.dog_id
                ):
                    raise DiscoveryError("missing_fallback")
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                options = {key: user_input[key] for key in DEFAULTS}
                title = f"Bark alerts — {sources.name}"
                if self._reconfigure:
                    # The regular update listener owns reloading the entry.
                    self.hass.config_entries.async_update_entry(
                        self._reconfigure,
                        title=title,
                        data=self._data,
                        options=options,
                        unique_id=self.unique_id,
                    )
                    return self.async_abort(reason="reconfigured")
                return self.async_create_entry(
                    title=title, data=self._data, options=options
                )
        return self.async_show_form(
            step_id="behavior",
            errors=errors,
            data_schema=behavior_schema(self._options),
        )

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        self._reconfigure = self._get_reconfigure_entry()
        self._options.update(self._reconfigure.options)
        return await self.async_step_user(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BarkAlertsOptionsFlow()


class BarkAlertsOptionsFlow(OptionsFlow):
    """Advanced settings without changing the chosen source or command."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                sources = camera_sources(
                    self.hass, self.config_entry.data[CONF_CAMERA_ID]
                )
                if user_input[CONF_FALLBACK] and not (
                    sources.animal_id and sources.dog_id
                ):
                    raise DiscoveryError("missing_fallback")
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=behavior_schema(dict(self.config_entry.options)),
            errors=errors,
        )
