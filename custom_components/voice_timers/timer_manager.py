"""Shared timer-state owner for Voice Timers.

This is the single source of truth the services, intents, and sensor
entities all read from — the equivalent of the old YAML package's
`timer.voice_N` + `input_text.voice_N_label` + `input_boolean.voice_timer_
ringing` trio, but owned entirely in-process so nothing has to be
hand-provisioned.

Design (ported from the original package, see HANDOFF.md):
  - N slots, each idle or active with a label and a finish time.
  - A finished timer resets its slot to idle immediately and hands its
    announcement to a single shared ringing loop, so one "stop" silences
    every ringing timer at once (mirrors the original's shared
    `voice_timer_ringing` boolean rather than a per-slot flag).
  - The ring loop announces on assist_satellite targets, repeating every
    `ring_repeat_seconds` until stopped or `ring_max_minutes` elapses.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import (
    ANNOUNCE_DOMAIN,
    ANNOUNCE_SERVICE,
    CONF_ANNOUNCE_TARGETS,
    DOMAIN,
    CONF_RING_MAX_MINUTES,
    CONF_RING_REPEAT_SECONDS,
    CONF_TIMER_SLOTS,
    DEFAULT_RING_MAX_MINUTES,
    DEFAULT_RING_REPEAT_SECONDS,
    DEFAULT_TIMER_SLOTS,
    EVENT_TIMER_CANCELLED,
    EVENT_TIMER_FINISHED,
    EVENT_TIMER_STARTED,
    SIGNAL_STATE_UPDATED,
    STATE_ACTIVE,
    STATE_IDLE,
    STATE_PAUSED,
)

_LOGGER = logging.getLogger(__name__)


def get_manager(hass: HomeAssistant) -> "TimerManager | None":
    """Return the single active TimerManager, if the integration is set up.

    Single-instance integration, so intents/services just grab the one
    manager rather than resolving a specific config entry.
    """
    for entry_data in hass.data.get(DOMAIN, {}).values():
        manager = entry_data.get("manager")
        if manager is not None:
            return manager
    return None


# --- Spoken-number fallback --------------------------------------------
# The generated custom-sentences use a {minutes} range list, which hassil
# normally resolves to an int (handling "5" and "five"). This is a belt-
# and-suspenders fallback for anything that arrives as raw text, ported
# from the word→number converter in the original voice_named_timers.yaml.
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}


def parse_minutes(value: object) -> float | None:
    """Coerce a minutes value (number, digit string, or number words) to a
    number, or None if it can't be understood."""
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        return value
    raw = str(value).strip().lower()
    if not raw:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", raw):
        return float(raw) if "." in raw else int(raw)
    total = 0
    matched = False
    for part in raw.replace("-", " ").split():
        if part in _TENS:
            total += _TENS[part]
            matched = True
        elif part in _ONES:
            total += _ONES[part]
            matched = True
    return total if matched else None


_NUMBER_WORDS = {value: word for word, value in _ONES.items() if value >= 2}


def format_duration(total_seconds: float) -> str:
    """Speakable duration, e.g. '1 hour and 30 minutes', '45 seconds'."""
    total = max(0, int(round(total_seconds)))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = [
        f"{value} {unit}{'s' if value != 1 else ''}"
        for value, unit in ((hours, "hour"), (minutes, "minute"), (seconds, "second"))
        if value
    ]
    if not parts:
        return "0 seconds"
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


@dataclass
class _Slot:
    """One named-timer slot."""

    number: int
    state: str = STATE_IDLE
    label: str = ""
    finishes_at: datetime | None = None
    # Original requested length, so "cancel the 5 minute timer" can match.
    duration_seconds: int = 0
    # Time left when paused (finishes_at is None while paused).
    paused_remaining: float | None = None
    _unsub: CALLBACK_TYPE | None = field(default=None, repr=False)

    @property
    def is_active(self) -> bool:
        return self.state == STATE_ACTIVE

    @property
    def in_use(self) -> bool:
        """Active or paused — either way the slot isn't free."""
        return self.state in (STATE_ACTIVE, STATE_PAUSED)

    def remaining_seconds(self, now: datetime) -> int | None:
        if self.state == STATE_PAUSED and self.paused_remaining is not None:
            return max(0, int(self.paused_remaining))
        if not self.is_active or self.finishes_at is None:
            return None
        return max(0, int((self.finishes_at - now).total_seconds()))

    def unschedule(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def clear(self) -> None:
        self.unschedule()
        self.state = STATE_IDLE
        self.label = ""
        self.finishes_at = None
        self.duration_seconds = 0
        self.paused_remaining = None


@dataclass
class StartResult:
    """Outcome of async_start, so callers can pick the right speech."""

    ok: bool
    reason: str | None = None  # "bad_duration" | "no_slot" when ok is False
    label: str = ""
    minutes: float = 0


class TimerManager:
    """Owns all timer state for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        slot_count = entry.options.get(CONF_TIMER_SLOTS, DEFAULT_TIMER_SLOTS)
        self._slots: list[_Slot] = [_Slot(number=i) for i in range(1, slot_count + 1)]

        # Shared ringing state (mirrors the old voice_timer_ringing boolean).
        self._ringing = False
        self._ring_messages: list[str] = []
        self._ring_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    # --- Introspection (read by sensor entities) -----------------------

    @property
    def slot_count(self) -> int:
        return len(self._slots)

    @property
    def is_ringing(self) -> bool:
        return self._ringing

    def slot_snapshot(self, number: int) -> dict:
        """State/attrs for slot `number`, or an idle snapshot if out of range."""
        now = dt_util.utcnow()
        for slot in self._slots:
            if slot.number == number:
                return {
                    "state": slot.state,
                    "label": slot.label,
                    "remaining_seconds": slot.remaining_seconds(now),
                    "finishes_at": (
                        slot.finishes_at.isoformat() if slot.finishes_at else None
                    ),
                }
        return {"state": STATE_IDLE, "label": "", "remaining_seconds": None, "finishes_at": None}

    def status_parts(self, slots: list[_Slot] | None = None) -> list[str]:
        """Human phrases for each timer in use, e.g. 'washer timer with 3
        minutes left' or 'pizza timer that's paused with 30 seconds left'.

        Defaults to every in-use slot; pass `slots` to describe just those.
        """
        now = dt_util.utcnow()
        parts: list[str] = []
        for slot in self.in_use_slots() if slots is None else slots:
            remaining = slot.remaining_seconds(now)
            if remaining is None:
                continue
            if remaining < 60:
                left = format_duration(remaining)
            else:
                mins = math.ceil(remaining / 60)  # ceil to whole minutes
                left = f"{mins} minute{'s' if mins != 1 else ''}"
            name = f"{slot.label} timer" if slot.label else "timer"
            paused = " that's paused" if slot.state == STATE_PAUSED else ""
            parts.append(f"{name}{paused} with {left} left")
        return parts

    def status_sentence(self, slots: list[_Slot] | None = None) -> str:
        """Spoken summary, e.g. 'You have three timers: a dinner timer with 2
        minutes left, a bath timer with 3 minutes left, and a pizza timer
        that's paused with 3 seconds left.'"""
        parts = self.status_parts(slots)
        if not parts:
            return "You have no timers running."
        if len(parts) == 1:
            return f"You have one {parts[0]}."
        listed = [f"{'an' if part[0] in 'aeiou' else 'a'} {part}" for part in parts]
        count = _NUMBER_WORDS.get(len(parts), str(len(parts)))
        return f"You have {count} timers: {', '.join(listed[:-1])}, and {listed[-1]}."

    def in_use_slots(self) -> list[_Slot]:
        return [s for s in self._slots if s.in_use]

    def find(
        self,
        label: str | None = None,
        duration_seconds: int | None = None,
        states: tuple[str, ...] = (STATE_ACTIVE, STATE_PAUSED),
    ) -> tuple[_Slot | None, str | None]:
        """Resolve which timer a command means.

        Matches on label (case-insensitive) and/or original duration. With
        neither given, it's only unambiguous when exactly one timer is in a
        matching state. Returns (slot, None) or (None, reason) where reason is
        "none" (nothing running), "not_found", or "ambiguous".
        """
        candidates = [s for s in self._slots if s.state in states]
        if not candidates:
            return None, "none"
        if label:
            target = label.strip().lower()
            candidates = [s for s in candidates if s.label.lower() == target]
        if duration_seconds:
            candidates = [s for s in candidates if s.duration_seconds == duration_seconds]
        if not candidates:
            return None, "not_found"
        if len(candidates) > 1:
            return None, "ambiguous"
        return candidates[0], None

    # --- Commands ------------------------------------------------------

    async def async_start(self, label: str, minutes: float) -> StartResult:
        """Start a timer in the first free slot."""
        label = (label or "").strip()
        if minutes is None or minutes <= 0:
            return StartResult(ok=False, reason="bad_duration")

        slot = next((s for s in self._slots if not s.in_use), None)
        if slot is None:
            return StartResult(ok=False, reason="no_slot")

        slot.state = STATE_ACTIVE
        slot.label = label
        slot.duration_seconds = int(round(minutes * 60))
        self._schedule(slot, dt_util.utcnow() + timedelta(minutes=minutes))

        self.hass.bus.async_fire(
            EVENT_TIMER_STARTED,
            {"slot": slot.number, "label": label, "minutes": minutes},
        )
        self._notify()
        return StartResult(ok=True, label=label, minutes=minutes)

    async def async_cancel(self, label: str) -> bool:
        """Cancel the timer matching `label` (case-insensitive).

        Returns True if one was found and cancelled.
        """
        target = (label or "").strip().lower()
        slot = next(
            (s for s in self._slots if s.in_use and s.label.lower() == target),
            None,
        )
        if slot is None:
            return False
        self.cancel_slot(slot)
        return True

    @callback
    def cancel_slot(self, slot: _Slot) -> None:
        """Cancel a specific in-use slot."""
        number, label = slot.number, slot.label
        slot.clear()
        self.hass.bus.async_fire(
            EVENT_TIMER_CANCELLED, {"slot": number, "label": label}
        )
        self._notify()

    @callback
    def cancel_all(self) -> int:
        """Cancel every in-use timer; returns how many were cancelled."""
        slots = self.in_use_slots()
        for slot in slots:
            self.cancel_slot(slot)
        return len(slots)

    @callback
    def adjust(self, slot: _Slot, delta_seconds: float) -> None:
        """Add (positive) or remove (negative) time from a timer.

        Removing more time than is left finishes it right away, like core.
        """
        now = dt_util.utcnow()
        remaining = (slot.remaining_seconds(now) or 0) + delta_seconds
        slot.duration_seconds = max(0, slot.duration_seconds + int(delta_seconds))
        if remaining <= 0:
            slot.unschedule()
            self._on_finished(slot)
            return
        if slot.state == STATE_PAUSED:
            slot.paused_remaining = remaining
        else:
            self._schedule(slot, now + timedelta(seconds=remaining))
        self._notify()

    @callback
    def pause(self, slot: _Slot) -> None:
        """Freeze a running timer's remaining time."""
        slot.paused_remaining = slot.remaining_seconds(dt_util.utcnow()) or 0
        slot.unschedule()
        slot.finishes_at = None
        slot.state = STATE_PAUSED
        self._notify()

    @callback
    def resume(self, slot: _Slot) -> None:
        """Restart a paused timer from where it stopped."""
        remaining = slot.paused_remaining or 0
        slot.paused_remaining = None
        slot.state = STATE_ACTIVE
        self._schedule(slot, dt_util.utcnow() + timedelta(seconds=remaining))
        self._notify()

    def _schedule(self, slot: _Slot, finishes_at: datetime) -> None:
        slot.unschedule()
        slot.finishes_at = finishes_at
        slot._unsub = async_track_point_in_time(
            self.hass, self._make_finish_cb(slot), finishes_at
        )

    async def async_stop_ringing(self) -> None:
        """Silence any/all currently-ringing timers."""
        if self._stop_event is not None:
            self._stop_event.set()
        self._ringing = False
        self._notify()

    # --- Finish + ring loop -------------------------------------------

    def _make_finish_cb(self, slot: _Slot) -> CALLBACK_TYPE:
        @callback
        def _fired(now: datetime) -> None:
            self._on_finished(slot)

        return _fired

    @callback
    def _on_finished(self, slot: _Slot) -> None:
        if not slot.in_use:
            return  # stale (already cancelled/reset)

        label = slot.label
        message = f"{label.capitalize()} timer is done." if label else "Your timer is done."
        number = slot.number

        slot._unsub = None  # the point-in-time fire consumed the callback
        slot.clear()

        self.hass.bus.async_fire(
            EVENT_TIMER_FINISHED, {"slot": number, "label": label}
        )

        self._ring_messages.append(message)
        if not self._ringing:
            self._ringing = True
            self._stop_event = asyncio.Event()
            self._ring_task = self.hass.async_create_background_task(
                self._ring_loop(), name="voice_timers_ring_loop"
            )
        self._notify()

    async def _ring_loop(self) -> None:
        interval = self.entry.options.get(
            CONF_RING_REPEAT_SECONDS, DEFAULT_RING_REPEAT_SECONDS
        )
        max_minutes = self.entry.options.get(
            CONF_RING_MAX_MINUTES, DEFAULT_RING_MAX_MINUTES
        )
        # Match the original's cap: repeat every `interval`s up to the
        # safety cutoff (e.g. 300 // 8 = 37 announcements ≈ 5 minutes).
        max_cycles = max(1, int(max_minutes) * 60 // max(1, int(interval)))
        stop = self._stop_event
        assert stop is not None

        cycle = 0
        try:
            while not stop.is_set() and cycle < max_cycles:
                for message in list(self._ring_messages):
                    if stop.is_set():
                        break
                    await self._announce(message)
                cycle += 1
                if stop.is_set():
                    break
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._ringing = False
            self._ring_messages.clear()
            self._ring_task = None
            self._notify()

    async def _announce(self, message: str) -> None:
        targets = self._resolve_targets()
        if not targets:
            _LOGGER.warning(
                "Voice Timers: no assist_satellite targets to announce %r", message
            )
            return
        try:
            await self.hass.services.async_call(
                ANNOUNCE_DOMAIN,
                ANNOUNCE_SERVICE,
                {"message": message},
                target={"entity_id": targets},
                blocking=True,
            )
        except Exception:  # noqa: BLE001 — never let one bad speaker kill the loop
            _LOGGER.exception("Voice Timers: announce failed for %r", message)

    def _resolve_targets(self) -> list[str]:
        configured = self.entry.options.get(CONF_ANNOUNCE_TARGETS) or []
        if configured:
            return list(configured)
        # Default: every satellite, like the original package.
        return [state.entity_id for state in self.hass.states.async_all(ANNOUNCE_DOMAIN)]

    # --- Lifecycle -----------------------------------------------------

    async def async_shutdown(self) -> None:
        """Cancel all scheduled finishes and stop the ring loop (on unload)."""
        for slot in self._slots:
            if slot._unsub is not None:
                slot._unsub()
                slot._unsub = None
        if self._stop_event is not None:
            self._stop_event.set()
        if self._ring_task is not None:
            self._ring_task.cancel()
            self._ring_task = None
        self._ringing = False
        self._ring_messages.clear()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, f"{SIGNAL_STATE_UPDATED}_{self.entry.entry_id}")
