"""Take over Home Assistant's built-in timer intents.

Claiming our own sentences isn't enough to keep core's timers out of the
picture: the built-in intents package has far more timer phrasing than we
write ("pause the timer", "add 5 minutes to the timer", "how much time is
left"...), and some of it would still reach core's HassStartTimer &
friends, which run timers on the satellite itself.

So when override_builtin_timer is on, we replace core's handlers for every
built-in timer intent with ones that drive our TimerManager. Whatever
sentence (or LLM tool call) produces a timer intent, it lands in our pool.
Core's handlers are kept and put back on unload or when the option is
turned off.

The one exception is a delayed command ("turn off the lights in 10
minutes"): that's HassStartTimer with a conversation_command slot, which
isn't a kitchen timer at all, so it's passed through to core's handler.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent

from .const import DOMAIN, STATE_ACTIVE, STATE_PAUSED
from .timer_manager import TimerManager, format_duration, get_manager

_LOGGER = logging.getLogger(__name__)

DATA_ORIGINALS = f"{DOMAIN}_builtin_originals"

TAKEOVER_INTENTS = (
    intent.INTENT_START_TIMER,
    intent.INTENT_CANCEL_TIMER,
    intent.INTENT_CANCEL_ALL_TIMERS,
    intent.INTENT_INCREASE_TIMER,
    intent.INTENT_DECREASE_TIMER,
    intent.INTENT_PAUSE_TIMER,
    intent.INTENT_UNPAUSE_TIMER,
    intent.INTENT_TIMER_STATUS,
)


def _registered(hass: HomeAssistant) -> dict[str, intent.IntentHandler]:
    return hass.data.get(intent.DATA_KEY, {})


def _seconds(slots: dict[str, Any], prefix: str = "") -> int:
    """Total seconds from {prefix}hours/minutes/seconds slots."""
    total = 0
    for unit, factor in (("hours", 3600), ("minutes", 60), ("seconds", 1)):
        if (slot := slots.get(f"{prefix}{unit}")) is not None:
            total += factor * int(slot["value"])
    return total


def _name(slots: dict[str, Any]) -> str:
    return (slots.get("name", {}).get("value") or "").strip()


def _describe(slot) -> str:
    return f"the {slot.label} timer" if slot.label else "the timer"


class _TakeoverHandler(intent.IntentHandler):
    """Base: borrows core's slot schema/description so LLM tools still work."""

    def __init__(self, original: intent.IntentHandler | None) -> None:
        self._original = original
        self.description = getattr(original, "description", None)

    @property
    def slot_schema(self) -> dict | None:
        return getattr(self._original, "slot_schema", None)

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        response = intent_obj.create_response()
        manager = get_manager(intent_obj.hass)
        if manager is None:
            response.async_set_speech("Voice Timers isn't set up.")
            return response
        response.async_set_speech(await self._async_speak(manager, slots))
        return response

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        raise NotImplementedError

    def _resolve(
        self,
        manager: TimerManager,
        slots: dict[str, Any],
        states: tuple[str, ...] = (STATE_ACTIVE, STATE_PAUSED),
        none_speech: str = "You have no timers running.",
    ):
        """Find the one timer the command refers to, or the speech for why not."""
        name = _name(slots)
        slot, reason = manager.find(
            label=name or None,
            duration_seconds=_seconds(slots, "start_") or None,
            states=states,
        )
        if slot is not None:
            return slot, None
        if reason == "none":
            return None, none_speech
        if reason == "not_found":
            what = f"a {name} timer" if name else "that timer"
            return None, f"I couldn't find {what}."
        return None, "Which timer? You have " + ", ".join(
            manager.status_parts()
        ) + "."


class StartTimerTakeover(_TakeoverHandler):
    intent_type = intent.INTENT_START_TIMER

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        if (
            intent_obj.slots.get("conversation_command", {}).get("value")
            and self._original is not None
        ):
            # Delayed command, not a kitchen timer — let core run it.
            return await self._original.async_handle(intent_obj)
        return await super().async_handle(intent_obj)

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        seconds = _seconds(slots)
        result = await manager.async_start(_name(slots), seconds / 60)
        if not result.ok and result.reason == "bad_duration":
            return "Sorry, I didn't catch how long."
        if not result.ok:
            return f"Sorry, all {manager.slot_count} timers are already in use."
        if result.label:
            return f"{result.label.capitalize()} timer set for {format_duration(seconds)}."
        return f"Timer set for {format_duration(seconds)}."


class CancelTimerTakeover(_TakeoverHandler):
    intent_type = intent.INTENT_CANCEL_TIMER

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        if manager.is_ringing and not (_name(slots) or _seconds(slots, "start_")):
            # "cancel the timer" while one is going off means "be quiet".
            await manager.async_stop_ringing()
            return "Okay."
        slot, problem = self._resolve(manager, slots)
        if slot is None:
            return problem
        what = _describe(slot)
        manager.cancel_slot(slot)
        return f"Cancelled {what}."


class CancelAllTimersTakeover(_TakeoverHandler):
    intent_type = intent.INTENT_CANCEL_ALL_TIMERS

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        was_ringing = manager.is_ringing
        await manager.async_stop_ringing()
        count = manager.cancel_all()
        if count == 0 and was_ringing:
            return "Okay."
        if count == 0:
            return "You have no timers running."
        return "Cancelled your timer." if count == 1 else f"Cancelled all {count} timers."


class IncreaseTimerTakeover(_TakeoverHandler):
    intent_type = intent.INTENT_INCREASE_TIMER
    _sign = 1

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        slot, problem = self._resolve(manager, slots)
        if slot is None:
            return problem
        seconds = _seconds(slots)
        if seconds <= 0:
            return "Sorry, I didn't catch how long."
        what = _describe(slot)
        manager.adjust(slot, self._sign * seconds)
        verb = "Added" if self._sign > 0 else "Took"
        prep = "to" if self._sign > 0 else "off"
        return f"{verb} {format_duration(seconds)} {prep} {what}."


class DecreaseTimerTakeover(IncreaseTimerTakeover):
    intent_type = intent.INTENT_DECREASE_TIMER
    _sign = -1


class PauseTimerTakeover(_TakeoverHandler):
    intent_type = intent.INTENT_PAUSE_TIMER

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        slot, problem = self._resolve(manager, slots, states=(STATE_ACTIVE,))
        if slot is None:
            return problem
        manager.pause(slot)
        return f"Paused {_describe(slot)}."


class UnpauseTimerTakeover(_TakeoverHandler):
    intent_type = intent.INTENT_UNPAUSE_TIMER

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        slot, problem = self._resolve(
            manager, slots, states=(STATE_PAUSED,), none_speech="You have no paused timers."
        )
        if slot is None:
            return problem
        manager.resume(slot)
        return f"Resumed {_describe(slot)}."


class TimerStatusTakeover(_TakeoverHandler):
    intent_type = intent.INTENT_TIMER_STATUS

    async def _async_speak(self, manager: TimerManager, slots: dict[str, Any]) -> str:
        if _name(slots) or _seconds(slots, "start_"):
            slot, problem = self._resolve(manager, slots)
            if slot is None:
                return problem
            parts = manager.status_parts([slot])
        else:
            parts = manager.status_parts()
        if not parts:
            return "You have no timers running."
        if len(parts) == 1:
            return f"You have one timer: {parts[0]}."
        return f"You have {len(parts)} timers: {', '.join(parts[:-1])}, and {parts[-1]}."


_TAKEOVER_CLASSES = (
    StartTimerTakeover,
    CancelTimerTakeover,
    CancelAllTimersTakeover,
    IncreaseTimerTakeover,
    DecreaseTimerTakeover,
    PauseTimerTakeover,
    UnpauseTimerTakeover,
    TimerStatusTakeover,
)


@callback
def async_install(hass: HomeAssistant) -> None:
    """Replace core's timer intent handlers with ours (idempotent)."""
    if DATA_ORIGINALS in hass.data:
        return
    registered = _registered(hass)
    originals = {name: registered.get(name) for name in TAKEOVER_INTENTS}
    hass.data[DATA_ORIGINALS] = originals
    for handler_cls in _TAKEOVER_CLASSES:
        # Remove first so core doesn't log an "overwritten" warning per intent.
        intent.async_remove(hass, handler_cls.intent_type)
        intent.async_register(hass, handler_cls(originals.get(handler_cls.intent_type)))
    _LOGGER.info(
        "Voice Timers: took over built-in timer intents %s", ", ".join(TAKEOVER_INTENTS)
    )


@callback
def async_restore(hass: HomeAssistant) -> None:
    """Put core's timer intent handlers back (no-op if never installed)."""
    originals = hass.data.pop(DATA_ORIGINALS, None)
    if originals is None:
        return
    for name, original in originals.items():
        intent.async_remove(hass, name)
        if original is not None:
            intent.async_register(hass, original)
    _LOGGER.info("Voice Timers: restored Home Assistant's built-in timer intents")
