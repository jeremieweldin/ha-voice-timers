"""Intent handlers for Voice Timers.

These handlers receive intents matched by HA's default conversation agent
from the sentences written to <config>/custom_sentences/en/ (see
sentences.py). They own no state — they call into the shared TimerManager
and speak the responses ported from the original YAML package.
"""
from __future__ import annotations

import logging
import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent

from .const import (
    INTENT_CANCEL_NAMED_TIMER,
    INTENT_SET_NAMED_TIMER,
    INTENT_STOP_RINGING,
    INTENT_TIMER_STATUS,
)
from .timer_manager import get_manager, parse_minutes

_LOGGER = logging.getLogger(__name__)

# "cancel the 30 second timer" matches "cancel [the] {label} timer" with the
# label "30 second" — the wildcard can't tell a name from a length.
_DURATION_LABEL = re.compile(r"^(.+?)\s+(second|minute|hour)s?$")
_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


def _label_as_seconds(label: str) -> int | None:
    """'30 second' / 'five minute' -> seconds, or None if it isn't a length."""
    match = _DURATION_LABEL.match(label)
    if match is None:
        return None
    amount = parse_minutes(match.group(1))
    if not amount:
        return None
    return int(round(amount * _UNIT_SECONDS[match.group(2)]))


def _fmt_minutes(minutes: float) -> str:
    """Whole numbers speak as ints ('5'), fractions keep a decimal ('1.5')."""
    return str(int(minutes)) if float(minutes).is_integer() else f"{minutes:g}"


class SetNamedTimerIntent(intent.IntentHandler):
    """Handle 'set a {label} timer for {minutes} minutes'."""

    intent_type = INTENT_SET_NAMED_TIMER
    slot_schema = {
        vol.Optional("label"): cv.string,
        vol.Required("minutes"): vol.Any(vol.Coerce(float), cv.string),
    }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        label = slots.get("label", {}).get("value", "") or ""
        minutes = parse_minutes(slots["minutes"]["value"])

        response = intent_obj.create_response()
        manager = get_manager(intent_obj.hass)
        if manager is None:
            response.async_set_speech("Voice Timers isn't set up.")
            return response

        result = await manager.async_start(label, minutes or 0)
        if not result.ok and result.reason == "bad_duration":
            response.async_set_speech("Sorry, I didn't catch how many minutes.")
        elif not result.ok and result.reason == "no_slot":
            response.async_set_speech(
                f"Sorry, all {manager.slot_count} timers are already in use."
            )
        else:
            mins = _fmt_minutes(result.minutes)
            plural = "s" if result.minutes != 1 else ""
            if result.label:
                response.async_set_speech(
                    f"{result.label.capitalize()} timer set for {mins} minute{plural}."
                )
            else:
                response.async_set_speech(f"Timer set for {mins} minute{plural}.")
        return response


class CancelNamedTimerIntent(intent.IntentHandler):
    """Handle 'cancel the {label} timer'."""

    intent_type = INTENT_CANCEL_NAMED_TIMER
    slot_schema = {vol.Required("label"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        label = slots["label"]["value"].strip().lower()

        response = intent_obj.create_response()
        manager = get_manager(intent_obj.hass)
        if manager is None:
            response.async_set_speech("Voice Timers isn't set up.")
            return response

        if await manager.async_cancel(label):
            response.async_set_speech(f"Cancelled the {label} timer.")
        elif (seconds := _label_as_seconds(label)) and (
            slot := manager.find(duration_seconds=seconds)[0]
        ):
            what = f"the {slot.label} timer" if slot.label else "the timer"
            manager.cancel_slot(slot)
            response.async_set_speech(f"Cancelled {what}.")
        else:
            response.async_set_speech(f"I couldn't find a {label} timer running.")
        return response


class TimerStatusIntent(intent.IntentHandler):
    """Handle 'what timers are running'."""

    intent_type = INTENT_TIMER_STATUS

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        manager = get_manager(intent_obj.hass)
        response.async_set_speech(
            manager.status_sentence() if manager else "You have no timers running."
        )
        return response


class StopRingingIntent(intent.IntentHandler):
    """Handle 'stop' / 'okay stop' / 'thank you' while a timer is ringing."""

    intent_type = INTENT_STOP_RINGING

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        manager = get_manager(intent_obj.hass)
        if manager is not None:
            await manager.async_stop_ringing()

        response = intent_obj.create_response()
        response.async_set_speech("Okay.")
        return response


_HANDLER_CLASSES = (
    SetNamedTimerIntent,
    CancelNamedTimerIntent,
    TimerStatusIntent,
    StopRingingIntent,
)

# Per-hass flag (not a module global, which would outlive a hass instance).
DATA_REGISTERED = "voice_timers_intents_registered"


async def async_setup_intents(
    hass: HomeAssistant, entry: ConfigEntry | None = None
) -> None:
    """Register intent handlers (idempotent — re-registering overwrites).

    Home Assistant also calls this on its own with just `hass`, because a
    module named intent.py is an intent platform — hence the optional entry.

    Which *sentences* map to these intents (including whether the bare
    "set a timer for N minutes" pattern is claimed) is handled in
    sentences.py based on the override_builtin_timer option; the handlers
    themselves are the same regardless.
    """
    if hass.data.get(DATA_REGISTERED):
        return
    for handler_cls in _HANDLER_CLASSES:
        intent.async_register(hass, handler_cls())
    hass.data[DATA_REGISTERED] = True
