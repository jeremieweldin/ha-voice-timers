"""Timer slot entities for Voice Timers.

Each configured slot (see CONF_TIMER_SLOTS) is exposed as its own
sensor entity, state = "idle" or "active" (mirrors core `timer` domain
state strings so this feels familiar), with label/remaining/finishes_at
as attributes rather than separate input_text/timer helper entities —
this is the main win over the YAML package version: nothing to
hand-provision, slot count is just a config-flow number.

*** SCAFFOLD STATUS ***
Structure and entity lifecycle (add/remove on options change) are
real. The actual countdown/ring logic is NOT implemented — see the
TODOs below and HANDOFF.md "Timer state owner" for the intended design
(a shared TimerManager the entities, services, and intents all read
from, rather than each entity independently tracking its own asyncio
timer handle).
"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_FINISHES_AT,
    ATTR_LABEL,
    ATTR_REMAINING,
    CONF_TIMER_SLOTS,
    DEFAULT_TIMER_SLOTS,
    DOMAIN,
    ENTITY_ID_FORMAT_SLOT,
    STATE_IDLE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up timer slot entities for this config entry."""
    slot_count = entry.options.get(CONF_TIMER_SLOTS, DEFAULT_TIMER_SLOTS)

    entities = [VoiceTimerSlot(entry, slot_index=i) for i in range(1, slot_count + 1)]
    async_add_entities(entities)

    # TODO(claude-code): handle slot_count changing via options update —
    # add new slot entities / remove trailing ones. Currently a slot-count
    # change only takes effect on integration reload, not live.


class VoiceTimerSlot(SensorEntity):
    """One named-timer slot.

    TODO: this currently only models static idle state. Needs:
      - start(label, minutes) -> schedules finish via
        async_track_point_in_time, sets state=active, label, finishes_at
      - cancel() -> clears state back to idle
      - a listener that fires EVENT_TIMER_FINISHED and hands off to
        whatever owns the repeating-announcement loop (see HANDOFF.md —
        likely a coordinator-level concern, not per-entity, since the
        "still ringing" repeat loop needs to run independent of any one
        slot once a timer fires and the slot resets to idle).
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, slot_index: int) -> None:
        self._entry = entry
        self._slot_index = slot_index
        self._attr_unique_id = f"{entry.entry_id}_slot_{slot_index}"
        self._attr_name = f"Voice Timer {slot_index}"
        self.entity_id = f"sensor.{ENTITY_ID_FORMAT_SLOT.format(slot_index)}"

        self._state = STATE_IDLE
        self._label = ""
        self._remaining_seconds: int | None = None
        self._finishes_at: str | None = None

    @property
    def native_value(self) -> str:
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_LABEL: self._label,
            ATTR_REMAINING: self._remaining_seconds,
            ATTR_FINISHES_AT: self._finishes_at,
        }

    @property
    def device_info(self):
        """Group all slots under one device for a tidy entity list."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Voice Timers",
            "manufacturer": "Voice Timers (custom)",
            "model": "Named Timer Pool",
        }
