"""Timer slot entities for Voice Timers.

Each configured slot (see CONF_TIMER_SLOTS) is exposed as its own sensor
entity, state = "idle" or "active" (mirrors core `timer` domain state
strings so this feels familiar), with label/remaining/finishes_at as
attributes — no separate input_text/timer helpers to hand-provision.

Entities are thin views over the shared TimerManager: they hold no timer
state of their own, they read it from the manager and re-render whenever
the manager dispatches a state-changed signal. Slot count is read at setup;
changing it via the options flow reloads the entry (see __init__.py), which
re-creates the platform with the new count.
"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_FINISHES_AT,
    ATTR_LABEL,
    ATTR_REMAINING,
    DOMAIN,
    ENTITY_ID_FORMAT_SLOT,
    SIGNAL_STATE_UPDATED,
)
from .timer_manager import TimerManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up timer slot entities for this config entry."""
    manager: TimerManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    entities = [
        VoiceTimerSlot(entry, manager, slot_index=i)
        for i in range(1, manager.slot_count + 1)
    ]
    async_add_entities(entities)


class VoiceTimerSlot(SensorEntity):
    """One named-timer slot — a read-only view over the TimerManager."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, entry: ConfigEntry, manager: TimerManager, slot_index: int
    ) -> None:
        self._entry = entry
        self._manager = manager
        self._slot_index = slot_index
        self._attr_unique_id = f"{entry.entry_id}_slot_{slot_index}"
        self._attr_name = f"Voice Timer {slot_index}"
        self.entity_id = f"sensor.{ENTITY_ID_FORMAT_SLOT.format(slot_index)}"

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager state-change signals."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_STATE_UPDATED}_{self._entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return self._manager.slot_snapshot(self._slot_index)["state"]

    @property
    def extra_state_attributes(self) -> dict:
        snap = self._manager.slot_snapshot(self._slot_index)
        return {
            ATTR_LABEL: snap["label"],
            ATTR_REMAINING: snap["remaining_seconds"],
            ATTR_FINISHES_AT: snap["finishes_at"],
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
