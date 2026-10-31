"""The Voice Timers integration.

Named voice timers (multi-slot, e.g. "set a washer timer for 50 minutes")
with repeating ring announcements — a HACS-installable replacement for the
YAML package version, so setup is a config flow instead of hand-authoring
timer/input_text/input_boolean helpers.

See HANDOFF.md at the repo root for background. The sentence-registration
question flagged there is resolved: sentences are written to
<config>/custom_sentences/en/ and loaded via conversation.reload (see
sentences.py), since custom components can't register sentences from Python.
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
    CONF_OVERRIDE_BUILTIN_TIMER,
    DEFAULT_OVERRIDE_BUILTIN_TIMER,
    DOMAIN,
    PLATFORM,
    SERVICE_CANCEL,
    SERVICE_START,
    SERVICE_STOP_RINGING,
)
from . import builtin_takeover
from . import intent as voice_timers_intent
from . import sentences
from .timer_manager import TimerManager, parse_minutes

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
    manager = TimerManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entry": entry, "manager": manager}

    await hass.config_entries.async_forward_entry_setups(entry, [PLATFORM])

    # --- Services -----------------------------------------------------
    async def _handle_start(call: ServiceCall) -> None:
        minutes = parse_minutes(call.data.get(ATTR_MINUTES))
        await manager.async_start(call.data.get(ATTR_LABEL, ""), minutes)

    async def _handle_cancel(call: ServiceCall) -> None:
        await manager.async_cancel(call.data[ATTR_LABEL])

    async def _handle_stop_ringing(call: ServiceCall) -> None:
        await manager.async_stop_ringing()

    hass.services.async_register(
        DOMAIN, SERVICE_START, _handle_start, schema=SERVICE_START_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL, _handle_cancel, schema=SERVICE_CANCEL_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP_RINGING, _handle_stop_ringing)

    # --- Intents + sentences ------------------------------------------
    await voice_timers_intent.async_setup_intents(hass, entry)
    override = entry.options.get(
        CONF_OVERRIDE_BUILTIN_TIMER, DEFAULT_OVERRIDE_BUILTIN_TIMER
    )
    await sentences.async_install_sentences(hass, override)
    # Override also swaps out core's timer intent handlers, so no timer
    # phrase (or LLM tool call) can start a timer on a satellite itself.
    if override:
        builtin_takeover.async_install(hass)
    else:
        builtin_takeover.async_restore(hass)

    # Reload the whole entry when options change — slot count, override
    # toggle, ring behavior, and announce targets are all picked up cleanly
    # by re-running setup (re-adds entities, rewrites sentences).
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry so option changes take full effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, [PLATFORM])
    if not unload_ok:
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data and (manager := data.get("manager")):
        await manager.async_shutdown()

    # If this was the last entry, tear down the shared services + sentences
    # and give core back its timer intents.
    if not hass.data[DOMAIN]:
        for service in (SERVICE_START, SERVICE_CANCEL, SERVICE_STOP_RINGING):
            hass.services.async_remove(DOMAIN, service)
        await sentences.async_remove_sentences(hass)
        builtin_takeover.async_restore(hass)

    return True
