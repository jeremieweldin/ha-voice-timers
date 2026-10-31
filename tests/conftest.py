"""Shared fixtures for Voice Timers tests."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.voice_timers.const import (
    CONF_OVERRIDE_BUILTIN_TIMER,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ in every test."""
    yield


@pytest.fixture(autouse=True)
def isolated_config_dir(hass: HomeAssistant, tmp_path):
    """Give each test its own config dir.

    The integration writes custom_sentences/ there, and conversation.reload
    re-reads configuration.yaml, so it has to exist.
    """
    (tmp_path / "configuration.yaml").write_text("")
    hass.config.config_dir = str(tmp_path)
    yield tmp_path


async def setup_voice_timers(hass: HomeAssistant, override: bool = True) -> MockConfigEntry:
    """Set up the conversation stack plus Voice Timers."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Voice Timers",
        options={CONF_OVERRIDE_BUILTIN_TIMER: override},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
