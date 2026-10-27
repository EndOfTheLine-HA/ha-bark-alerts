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
    CONF_CAMERA_IDS,
    CONF_COMMAND,
    CONF_COMMAND_MODE,
    CONF_COOLDOWN,
    CONF_DELAY,
    CONF_DEVICE,
    CONF_DOG_WINDOW,
    CONF_FALLBACK,
    CONF_HISTORY,
    CONF_REPEATS,
    CONF_RF_CODE,
    DEFAULTS,
    DOMAIN,
    MODE_KEEP,
    MODE_LEARNED,
    MODE_RAW,
)
from .discovery import (
    DiscoveryError,
    broadlink_remote,
    camera_sources,
    monitor_sources,
    selected_camera_ids,
)
from .validation import normalize_command, normalize_command_name


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
    fields[vol.Required(CONF_HISTORY, default=defaults.get(CONF_HISTORY, False))] = (
        selector.BooleanSelector()
    )
    return vol.Schema(fields)


class BarkAlertsFlow(ConfigFlow, domain=DOMAIN):
    """Pair selected cameras with one existing RF-capable Broadlink device."""

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
        camera_field = vol.Required(CONF_CAMERA)
        if self._reconfigure:
            camera_field = vol.Required(
                CONF_CAMERA,
                default=[
                    entity.entity_id
                    for key in selected_camera_ids(self._reconfigure.data)
                    if (entity := registry.async_get(key))
                ],
            )
        errors = {}
        if user_input is not None:
            try:
                selected = user_input[CONF_CAMERA]
                if isinstance(selected, str):
                    selected = [selected]
                if not selected:
                    raise DiscoveryError("invalid_camera")
                sources = [camera_sources(self.hass, key) for key in selected]
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                self._data[CONF_CAMERA_IDS] = list(
                    dict.fromkeys(source.camera_id for source in sources)
                )
                self._data[CONF_CAMERA_ID] = sources[0].camera_id
                return await self.async_step_broadlink()
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    camera_field: selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="camera",
                            integration="frigate",
                            include_entities=cameras,
                            multiple=True,
                        )
                    )
                }
            ),
        )

    async def async_step_broadlink(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        device_field = vol.Required(CONF_BROADLINK)
        if self._reconfigure:
            device_field = vol.Required(
                CONF_BROADLINK, default=self._reconfigure.data[CONF_BROADLINK]
            )
        if user_input is not None:
            try:
                broadlink_remote(self.hass, user_input[CONF_BROADLINK])
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                self._data[CONF_BROADLINK] = user_input[CONF_BROADLINK]
                camera_key = ",".join(sorted(selected_camera_ids(self._data)))
                pair_id = f"{camera_key}:{user_input[CONF_BROADLINK]}"
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
                    device_field: selector.DeviceSelector(
                        selector.DeviceSelectorConfig(integration="broadlink")
                    )
                }
            ),
        )

    async def async_step_command(self, user_input=None) -> ConfigFlowResult:
        """Choose a mode before showing only that mode's fields."""
        errors = {}
        saved_command = None
        if (
            self._reconfigure
            and self._data.get(CONF_BROADLINK) == self._reconfigure.data[CONF_BROADLINK]
        ):
            try:
                saved_command = normalize_command(self._reconfigure.data)
            except DiscoveryError:
                pass
        modes = [MODE_LEARNED, MODE_RAW]
        if saved_command:
            modes.insert(0, MODE_KEEP)
        if user_input is not None:
            mode = user_input.get(CONF_COMMAND_MODE)
            if mode not in modes:
                errors["base"] = "invalid_command_mode"
            else:
                for key in (CONF_DEVICE, CONF_COMMAND, CONF_RF_CODE, CONF_BEEP_ONLY):
                    self._data.pop(key, None)
                if mode == MODE_KEEP:
                    self._data.update(saved_command)
                    return await self.async_step_behavior()
                self._data[CONF_COMMAND_MODE] = mode
                if mode == MODE_RAW:
                    return await self.async_step_raw_command()
                return await self.async_step_learned_device()
        return self.async_show_form(
            step_id="command",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COMMAND_MODE, default=modes[0]
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=modes,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="command_mode",
                        )
                    ),
                }
            ),
        )

    async def async_step_learned_device(self, user_input=None) -> ConfigFlowResult:
        """Accept a typed device/group name for an existing or new command."""
        errors = {}
        if user_input is not None:
            try:
                self._data[CONF_DEVICE] = normalize_command_name(
                    user_input.get(CONF_DEVICE)
                )
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                return await self.async_step_learned_command()
        return self.async_show_form(
            step_id="learned_device",
            errors=errors,
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE): selector.TextSelector()}
            ),
        )

    async def async_step_learned_command(self, user_input=None) -> ConfigFlowResult:
        """Accept a typed command name and require beep-only confirmation."""
        errors = {}
        if user_input is not None:
            try:
                command = normalize_command(
                    {
                        CONF_COMMAND_MODE: MODE_LEARNED,
                        CONF_DEVICE: self._data[CONF_DEVICE],
                        CONF_COMMAND: user_input.get(CONF_COMMAND),
                        CONF_BEEP_ONLY: user_input.get(CONF_BEEP_ONLY),
                    }
                )
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                self._data.update(command)
                return await self.async_step_behavior()
        return self.async_show_form(
            step_id="learned_command",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COMMAND): selector.TextSelector(),
                    vol.Required(
                        CONF_BEEP_ONLY, default=False
                    ): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_raw_command(self, user_input=None) -> ConfigFlowResult:
        """Raw mode never displays learned-name fields or prefills a code."""
        errors = {}
        if user_input is not None:
            try:
                command = normalize_command(
                    {
                        CONF_COMMAND_MODE: MODE_RAW,
                        CONF_RF_CODE: user_input.get(CONF_RF_CODE, ""),
                        CONF_BEEP_ONLY: user_input.get(CONF_BEEP_ONLY),
                    }
                )
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                self._data.update(command)
                return await self.async_step_behavior()
        return self.async_show_form(
            step_id="raw_command",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RF_CODE): selector.TextSelector(
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
                sources = monitor_sources(self.hass, self._data)
                broadlink_remote(self.hass, self._data[CONF_BROADLINK])
                if user_input[CONF_FALLBACK] and not (
                    all(source.animal_id and source.dog_id for source in sources)
                ):
                    raise DiscoveryError("missing_fallback")
            except DiscoveryError as err:
                errors["base"] = err.code
            else:
                options = {
                    key: user_input.get(key, default)
                    for key, default in DEFAULTS.items()
                }
                title = (
                    f"Bark alerts: {sources[0].name}"
                    if len(sources) == 1
                    else "Bark alerts: multi-camera monitor"
                )
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
                sources = monitor_sources(self.hass, self.config_entry.data)
                if user_input[CONF_FALLBACK] and not (
                    all(source.animal_id and source.dog_id for source in sources)
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
