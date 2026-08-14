"""Intent handlers for Voice Timers.

*** READ BEFORE TRUSTING THIS FILE ***
The IntentHandler classes below (subclassing homeassistant.helpers.intent
.IntentHandler) are standard, well-documented HA pattern and should be
correct as structured. What is NOT verified is the exact mechanism by
which a *custom_component* (as opposed to core) ships the actual sentence
templates that get matched to these intents. Core integrations bundle
sentence YAML in a way that's wired up through the `conversation`
component's language-pack loading; that path was not confirmed against
current HA developer docs as part of this scaffold.

Before treating async_setup_intents() as functional, check:
  https://developers.home-assistant.io/docs/voice/intent-recognition/

Specifically confirm:
  1. Whether a custom_component can ship its own sentence YAML the same
     way core integrations do (likely something under a `data/` or
     similar structure the conversation component scans), or whether
     custom components are expected to use `conversation.async_set_agent`
     level hooks instead.
  2. Whether hass.helpers.intent.async_register alone is sufficient, or
     whether sentences additionally need registering with
     `hassil`/`conversation` explicitly for a non-core component.

This is exactly the kind of thing that looked-right-but-wasn't caused
real bugs earlier in this project's YAML-package version (wrong file
extension silently ignored, punctuation silently breaking a whole
trigger list) — so this note exists specifically so that class of
mistake doesn't get shipped silently here too.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent

from .const import (
    CONF_OVERRIDE_BUILTIN_TIMER,
    DEFAULT_OVERRIDE_BUILTIN_TIMER,
    DOMAIN,
    INTENT_CANCEL_NAMED_TIMER,
    INTENT_SET_NAMED_TIMER,
    INTENT_STOP_RINGING,
    INTENT_TIMER_STATUS,
)

_LOGGER = logging.getLogger(__name__)


class SetNamedTimerIntent(intent.IntentHandler):
    """Handle 'set a {label} timer for {minutes} minutes'."""

    intent_type = INTENT_SET_NAMED_TIMER
    slot_schema = {
        vol.Optional("label"): cv.string,
        vol.Required("minutes"): vol.Coerce(float),
    }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        label = slots.get("label", {}).get("value", "")
        minutes = slots["minutes"]["value"]

        # TODO: call into the timer manager / voice_timers.start service
        # instead of a bare log line once timer_manager.py exists.
        _LOGGER.debug("SetNamedTimerIntent: label=%r minutes=%r", label, minutes)

        response = intent_obj.create_response()
        if label:
            response.async_set_speech(f"{label.capitalize()} timer set for {minutes:g} minutes.")
        else:
            response.async_set_speech(f"Timer set for {minutes:g} minutes.")
        return response


class CancelNamedTimerIntent(intent.IntentHandler):
    """Handle 'cancel the {label} timer'."""

    intent_type = INTENT_CANCEL_NAMED_TIMER
    slot_schema = {vol.Required("label"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        label = slots["label"]["value"]

        # TODO: call into the timer manager; respond differently if no
        # matching timer was found (mirrors the YAML package's behavior).
        _LOGGER.debug("CancelNamedTimerIntent: label=%r", label)

        response = intent_obj.create_response()
        response.async_set_speech(f"Cancelled the {label} timer.")
        return response


class TimerStatusIntent(intent.IntentHandler):
    """Handle 'what timers are running'."""

    intent_type = INTENT_TIMER_STATUS

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        # TODO: pull real state from the timer manager and format the
        # same "you have N timers: ..." response the YAML version built.
        response = intent_obj.create_response()
        response.async_set_speech("You have no timers running.")
        return response


class StopRingingIntent(intent.IntentHandler):
    """Handle 'stop' / 'okay stop' / 'thank you' while a timer is ringing."""

    intent_type = INTENT_STOP_RINGING

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        # TODO: flip the ringing flag off via the timer manager.
        response = intent_obj.create_response()
        response.async_set_speech("Okay.")
        return response


_REGISTERED_HANDLERS: dict[str, intent.IntentHandler] = {}


async def async_setup_intents(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register (or re-register) intent handlers for this entry.

    Called on setup and again whenever options change, since the
    override_builtin_timer toggle affects which sentences this
    integration should claim (see const.py comment on the default).
    """
    override_builtin = entry.options.get(
        CONF_OVERRIDE_BUILTIN_TIMER, DEFAULT_OVERRIDE_BUILTIN_TIMER
    )

    for handler_cls in (
        SetNamedTimerIntent,
        CancelNamedTimerIntent,
        TimerStatusIntent,
        StopRingingIntent,
    ):
        handler = handler_cls()
        intent.async_register(hass, handler)
        _REGISTERED_HANDLERS[handler.intent_type] = handler

    # TODO: this is the override_builtin_timer branch point. When True,
    # the sentence set for SetNamedTimerIntent should include the BARE
    # pattern ("set a timer for {minutes} minutes", no label) so it wins
    # over core's built-in ad-hoc timer intent — mirroring what
    # voice_named_timers.yaml already does today. When False, only the
    # named pattern ("set a {label} timer for ...") should be registered,
    # letting bare "set a timer for X minutes" fall through to HA core's
    # own timer intent instead.
    #
    # This branch can't be implemented correctly until the sentence-
    # registration mechanism itself (see module docstring) is confirmed,
    # since *where* the sentence list lives determines how conditional
    # inclusion/exclusion is even expressed.
    _LOGGER.debug(
        "Voice Timers: override_builtin_timer=%s (sentence-set branching "
        "not yet implemented — see intent.py TODO)",
        override_builtin,
    )
