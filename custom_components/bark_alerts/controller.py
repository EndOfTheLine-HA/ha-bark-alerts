"""Event-driven bark handling with no queue or automatic retry."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, STATE_OFF, STATE_ON
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BROADLINK,
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
)
from .discovery import (
    CameraSources,
    DiscoveryError,
    broadlink_remote,
    camera_sources,
    entity_id,
)

_LOGGER = logging.getLogger(__name__)


class BarkAlertsController:
    """One camera/remote pairing. RF dispatch is not proof of audible reception."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        sources: CameraSources,
        remote_id: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.sources = sources
        self.remote_id = remote_id
        self.clock = clock
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        # Deliberately never restored: a restart/reconfigure requires re-arming.
        self.armed = False
        self.dry_run = True
        self.outcome = "idle"
        self.last_detection: datetime | None = None
        self.last_request: datetime | None = None
        self.request_count = 0
        self.dry_run_count = 0
        self._last_dog: float | None = None
        self._next_allowed = 0.0
        self._lock = asyncio.Lock()
        self._stopped = False
        self._bindings_valid = True
        self._state_unsub: Callable[[], None] | None = None
        self._unsubs: list[Callable[[], None]] = []
        self._tasks: set[asyncio.Task] = set()
        self._watched: set[str] = set()

    def option(self, key: str) -> Any:
        return self.entry.options.get(key, DEFAULTS[key])

    def _state(self, registry_id: str | None) -> str | None:
        current_id = entity_id(self.hass, registry_id)
        state = self.hass.states.get(current_id) if current_id else None
        return state.state if state else None

    @property
    def ready(self) -> bool:
        return (
            not self._stopped
            and self._bindings_valid
            and self._state(self.sources.bark_id) in (STATE_ON, STATE_OFF)
            and self._state(self.remote_id) == STATE_ON
            and self.hass.services.has_service("remote", "send_command")
        )

    @property
    def dog_recent(self) -> bool:
        state = self._state(self.sources.dog_id)
        return (
            self._last_dog is not None
            and state in (STATE_ON, STATE_OFF)
            and (
                state == STATE_ON
                or self.clock() - self._last_dog <= self.option(CONF_DOG_WINDOW)
            )
        )

    @callback
    def async_start(self) -> None:
        self._bind_sources()
        self._unsubs.extend(
            [
                self.hass.bus.async_listen(
                    er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed
                ),
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STOP, lambda _: self.async_stop()
                ),
            ]
        )

    @callback
    def _bind_sources(self) -> None:
        if self._state_unsub:
            self._state_unsub()
            self._state_unsub = None
        try:
            self.sources = camera_sources(self.hass, self.entry.data[CONF_CAMERA_ID])
            self.remote_id = broadlink_remote(
                self.hass, self.entry.data[CONF_BROADLINK]
            ).id
            self._bindings_valid = not self.option(CONF_FALLBACK) or bool(
                self.sources.animal_id and self.sources.dog_id
            )
        except DiscoveryError:
            self._bindings_valid = False
        registry_ids = (
            self.sources.camera_id,
            self.sources.bark_id,
            self.sources.animal_id,
            self.sources.dog_id,
            self.remote_id,
        )
        self._watched = {
            current for key in registry_ids if (current := entity_id(self.hass, key))
        }
        if self._watched:
            self._state_unsub = async_track_state_change_event(
                self.hass, list(self._watched), self._state_changed
            )
        self.async_notify()

    @callback
    def _registry_changed(self, event: Event) -> None:
        changed_id = event.data.get("entity_id")
        changed = er.async_get(self.hass).async_get(changed_id) if changed_id else None
        camera = er.async_get(self.hass).async_get(self.sources.camera_id)
        if changed_id not in self._watched and not (
            changed
            and (
                changed.id == self.sources.camera_id
                or changed.device_id == self.entry.data[CONF_BROADLINK]
                or (
                    camera
                    and changed.platform == "frigate"
                    and changed.device_id == camera.device_id
                )
            )
        ):
            return
        self._bind_sources()

    @callback
    def _state_changed(self, event: Event) -> None:
        old, new = event.data.get("old_state"), event.data.get("new_state")
        current_id = event.data["entity_id"]
        if current_id == entity_id(self.hass, self.sources.dog_id):
            if new is None or new.state not in (STATE_ON, STATE_OFF):
                self._last_dog = None
            elif old is not None and old.state == STATE_OFF and new.state == STATE_ON:
                self._last_dog = self.clock()
        self.async_notify()
        # Ignore startup, retained ON, recovery from unavailable, and attributes.
        if (
            old is None
            or new is None
            or old.state != STATE_OFF
            or new.state != STATE_ON
        ):
            return
        source: str | None = None
        if current_id == entity_id(self.hass, self.sources.bark_id):
            source = "bark"
        elif self.option(CONF_FALLBACK) and current_id == entity_id(
            self.hass, self.sources.animal_id
        ):
            source = "animal"
        if source:
            task = self.hass.async_create_task(
                self.async_alert(source, context=event.context),
                f"{DOMAIN} alert",
                eager_start=False,
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    @callback
    def async_notify(self) -> None:
        if not self._stopped:
            async_dispatcher_send(self.hass, self.signal)

    @callback
    def _record(self, outcome: str, source: str) -> None:
        self.outcome = outcome
        self.async_notify()
        if not self._stopped:
            self.hass.bus.async_fire(
                f"{DOMAIN}_alert",
                {"entry_id": self.entry.entry_id, "source": source, "outcome": outcome},
            )

    async def async_alert(
        self,
        source: str,
        *,
        manual: bool = False,
        context: Context | None = None,
    ) -> None:
        """Request at most one bounded send; never retry or queue a later beep."""
        if self._stopped:
            return
        if not manual:
            self.last_detection = dt_util.utcnow()
            if not self.armed:
                self._record("disarmed", source)
                return
            if not self._bindings_valid or self._state(self.sources.bark_id) not in (
                STATE_ON,
                STATE_OFF,
            ):
                self._record("source_unavailable", source)
                return
            if source == "animal" and not self.dog_recent:
                self._record("dog_not_recent", source)
                return
        if self._lock.locked():
            self._record("busy", source)
            if manual:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="busy"
                )
            return
        async with self._lock:
            if self.clock() < self._next_allowed:
                self._record("cooldown", source)
                if manual:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="cooldown"
                    )
                return
            if not manual and self.dry_run:
                self._next_allowed = self.clock() + self.option(CONF_COOLDOWN)
                self.dry_run_count += 1
                self._record("dry_run", source)
                return
            if self._state(self.remote_id) != STATE_ON:
                self._record("remote_unavailable", source)
                if manual:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="remote_unavailable"
                    )
                return
            self._next_allowed = self.clock() + self.option(CONF_COOLDOWN)
            data = {
                "num_repeats": int(self.option(CONF_REPEATS)),
                "delay_secs": self.option(CONF_DELAY),
            }
            if self.entry.data[CONF_COMMAND_MODE] == MODE_LEARNED:
                data.update(
                    device=self.entry.data[CONF_DEVICE],
                    command=[self.entry.data[CONF_COMMAND]],
                )
            else:
                data["command"] = [self.entry.data[CONF_RF_CODE]]
            task = asyncio.current_task()
            self._tasks.add(task)
            try:
                async with asyncio.timeout(30):
                    await self.hass.services.async_call(
                        "remote",
                        "send_command",
                        data,
                        blocking=True,
                        context=context,
                        target={"entity_id": entity_id(self.hass, self.remote_id)},
                    )
            except HomeAssistantError, ValueError, OSError, TimeoutError:
                # Upstream exceptions may contain raw RF codes; do not log them.
                _LOGGER.warning("Broadlink beep request failed; no automatic retry")
                self._record("error", source)
                if manual:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="send_failed"
                    ) from None
            else:
                self.last_request = dt_util.utcnow()
                self.request_count += 1
                self._record("command_requested", source)
            finally:
                self._tasks.discard(task)

    async def async_learn(self, context: Context | None = None) -> None:
        """Explicit receive-only action; follow Broadlink's native notifications."""
        if self._stopped or self.entry.data[CONF_COMMAND_MODE] != MODE_LEARNED:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_learned"
            )
        if self._lock.locked():
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="busy")
        if self._state(self.remote_id) != STATE_ON:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="remote_unavailable"
            )
        async with self._lock:
            task = asyncio.current_task()
            self._tasks.add(task)
            try:
                async with asyncio.timeout(120):
                    await self.hass.services.async_call(
                        "remote",
                        "learn_command",
                        {
                            "device": self.entry.data[CONF_DEVICE],
                            "command": [self.entry.data[CONF_COMMAND]],
                            "command_type": "rf",
                        },
                        blocking=True,
                        context=context,
                        target={"entity_id": entity_id(self.hass, self.remote_id)},
                    )
            except HomeAssistantError, ValueError, OSError, TimeoutError:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="learn_failed"
                ) from None
            finally:
                self._tasks.discard(task)
            self._record("learning_requested", "manual")

    @callback
    def async_stop(self) -> None:
        """Discard pending tasks; do not leave a delayed command behind."""
        self._stopped = True
        self.armed = False
        if self._state_unsub:
            self._state_unsub()
            self._state_unsub = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for task in tuple(self._tasks):
            task.cancel()
        self._tasks.clear()
