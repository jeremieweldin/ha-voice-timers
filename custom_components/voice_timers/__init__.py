"""The Voice Timers integration.

Named voice timers (multi-slot, e.g. "set a washer timer for 50 minutes")
with repeating ring announcements — a HACS-installable replacement for the
YAML package version, so setup is a config flow instead of hand-authoring
timer/input_text/input_boolean helpers.

See HANDOFF.md at the repo root for architecture notes, what's stubbed
vs. implemented, and the open questions flagged for whoever picks this
scaffold up next.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_LABEL,
    ATTR_MINUTES,
    DOMAIN,
    PLATFORM,
    SERVICE_CANCEL,
    SERVICE_START,
    SERVICE_STOP_RINGING,
)
from . import intent as voice_timers_intent

_LOGGER = logging.getLogger(__name__)

SERVICE_START_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_LABEL, default=""): cv.string,
        vol.Required(ATTR_MINUTES): vol.All(vol.Coerce(float), vol.Range(min=0.1)),
    }
)
SERVICE_CANCEL_SCHEMA = vol.Schema({vol.Required(ATTR_LABEL): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Voice Timers from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entry": entry}

    await hass.config_entries.async_forward_entry_setups(entry, [PLATFORM])

    # --- Services -----------------------------------------------------
    # TODO(claude-code): wire these to the coordinator/entity manager
    # once timer_manager.py exists (see HANDOFF.md, "Timer state owner").
    async def _handle_start(call: ServiceCall) -> None:
        _LOGGER.debug("voice_timers.start called: %s", call.data)
        # TODO: find a free slot, start it, fire EVENT_TIMER_STARTED

    async def _handle_cancel(call: ServiceCall) -> None:
        _LOGGER.debug("voice_timers.cancel called: %s", call.data)
        # TODO: find slot by label, cancel it, fire EVENT_TIMER_CANCELLED

    async def _handle_stop_ringing(call: ServiceCall) -> None:
        _LOGGER.debug("voice_timers.stop_ringing called")
        # TODO: flip the ringing flag off (see const.EVENT_TIMER_FINISHED
        # consumer in the entity platform)

    hass.services.async_register(DOMAIN, SERVICE_START, _handle_start, schema=SERVICE_START_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _handle_cancel, schema=SERVICE_CANCEL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP_RINGING, _handle_stop_ringing)

    # --- Intents / sentences -------------------------------------------
    # NOTE: sentence-registration mechanism for a Python custom_component
    # is a flagged open question — see HANDOFF.md "Sentence registration"
    # before trusting this call does what its name implies.
    await voice_timers_intent.async_setup_intents(hass, entry)

    # Re-register intents if the override toggle (or anything else that
    # affects which sentences are claimed) changes via the options flow.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — re-register intents in case the
    override_builtin_timer toggle (or slot count) changed."""
    await voice_timers_intent.async_setup_intents(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, [PLATFORM])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
