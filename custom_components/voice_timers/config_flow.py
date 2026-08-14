"""Config flow for Voice Timers.

Single-instance integration: setup just confirms install (no external
service/account to authenticate against), then all real configuration
lives in the Options flow so it can be changed later without deleting
and re-adding the integration.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    ANNOUNCE_DOMAIN,
    CONF_ANNOUNCE_TARGETS,
    CONF_OVERRIDE_BUILTIN_TIMER,
    CONF_RING_MAX_MINUTES,
    CONF_RING_REPEAT_SECONDS,
    CONF_TIMER_SLOTS,
    DEFAULT_OVERRIDE_BUILTIN_TIMER,
    DEFAULT_RING_MAX_MINUTES,
    DEFAULT_RING_REPEAT_SECONDS,
    DEFAULT_TIMER_SLOTS,
    DOMAIN,
    MAX_TIMER_SLOTS,
    MIN_TIMER_SLOTS,
)


class VoiceTimersConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """First (and only) setup step — just confirm and create the entry.

        All tunable settings live in the options flow so they're editable
        later without removing/re-adding the integration.
        """
        # Single instance only — remove this guard if multiple independent
        # timer pools ever becomes a real use case.
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Voice Timers", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> VoiceTimersOptionsFlow:
        """Get the options flow for this handler."""
        # `config_entry` is provided to the options flow automatically by HA
        # (self.config_entry); assigning it manually was deprecated in
        # 2024.11 and removed since, so we don't pass or store it.
        return VoiceTimersOptionsFlow()


class VoiceTimersOptionsFlow(config_entries.OptionsFlow):
    """Handle options — slot count, builtin-override toggle, ring behavior."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TIMER_SLOTS,
                    default=current.get(CONF_TIMER_SLOTS, DEFAULT_TIMER_SLOTS),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_TIMER_SLOTS, max=MAX_TIMER_SLOTS)),
                # Defaults ON. Description string (see translations/en.json)
                # explains what turning it off does — this is the field the
                # user explicitly asked to default on with a visible way to
                # turn it off, not hidden/undocumented.
                vol.Required(
                    CONF_OVERRIDE_BUILTIN_TIMER,
                    default=current.get(
                        CONF_OVERRIDE_BUILTIN_TIMER, DEFAULT_OVERRIDE_BUILTIN_TIMER
                    ),
                ): bool,
                vol.Required(
                    CONF_RING_REPEAT_SECONDS,
                    default=current.get(
                        CONF_RING_REPEAT_SECONDS, DEFAULT_RING_REPEAT_SECONDS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
                vol.Required(
                    CONF_RING_MAX_MINUTES,
                    default=current.get(
                        CONF_RING_MAX_MINUTES, DEFAULT_RING_MAX_MINUTES
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                # Which satellites to announce on. Leave empty for "all
                # satellites" (the original package's behavior).
                vol.Optional(
                    CONF_ANNOUNCE_TARGETS,
                    default=current.get(CONF_ANNOUNCE_TARGETS, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=ANNOUNCE_DOMAIN, multiple=True
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
