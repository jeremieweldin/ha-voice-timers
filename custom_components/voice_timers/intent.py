"""Intent handlers for Voice Timers.

These handlers receive intents matched by HA's default conversation agent
from the sentences written to <config>/custom_sentences/en/ (see
sentences.py). They own no state — they call into the shared TimerManager
and speak the responses ported from the original YAML package.
"""
from __future__ import annotations

import logging

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
        else:
            response.async_set_speech(f"I couldn't find a {label} timer running.")
        return response


class TimerStatusIntent(intent.IntentHandler):
    """Handle 'what timers are running'."""

    intent_type = INTENT_TIMER_STATUS

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        manager = get_manager(intent_obj.hass)
        parts = manager.status_parts() if manager else []

        if not parts:
            response.async_set_speech("You have no timers running.")
        elif len(parts) == 1:
            response.async_set_speech(f"You have one timer: {parts[0]}.")
        else:
            response.async_set_speech(
                f"You have {len(parts)} timers: "
                f"{', '.join(parts[:-1])}, and {parts[-1]}."
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

_REGISTERED = False


async def async_setup_intents(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register intent handlers (idempotent — re-registering overwrites).

    Which *sentences* map to these intents (including whether the bare
    "set a timer for N minutes" pattern is claimed) is handled in
    sentences.py based on the override_builtin_timer option; the handlers
    themselves are the same regardless.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    for handler_cls in _HANDLER_CLASSES:
        intent.async_register(hass, handler_cls())
    _REGISTERED = True
