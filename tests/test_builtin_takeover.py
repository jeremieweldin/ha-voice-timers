"""Built-in timer intents are routed to Voice Timers instead of core."""
from __future__ import annotations

from datetime import timedelta

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.components import conversation
from homeassistant.components.intent import timers as core_timers
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util

from custom_components.voice_timers import builtin_takeover
from custom_components.voice_timers.timer_manager import format_duration, get_manager

from .conftest import setup_voice_timers


def _handler(hass: HomeAssistant, intent_type: str) -> intent.IntentHandler:
    return hass.data[intent.DATA_KEY][intent_type]


async def _say(hass: HomeAssistant, intent_type: str, **slots) -> str:
    response = await intent.async_handle(
        hass,
        "test",
        intent_type,
        {name: {"value": value} for name, value in slots.items()},
    )
    return response.speech["plain"]["speech"]


async def _converse(hass: HomeAssistant, text: str) -> str:
    result = await conversation.async_converse(hass, text, None, Context(), language="en")
    return result.response.speech["plain"]["speech"]


async def test_override_replaces_every_core_timer_handler(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass)
    for name in builtin_takeover.TAKEOVER_INTENTS:
        assert isinstance(_handler(hass, name), builtin_takeover._TakeoverHandler), name
    # Core's slot schema is borrowed, so LLM tool definitions stay intact.
    assert _handler(hass, intent.INTENT_START_TIMER).slot_schema is not None


async def test_override_off_leaves_core_alone(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass, override=False)
    assert isinstance(
        _handler(hass, intent.INTENT_START_TIMER), core_timers.StartTimerIntentHandler
    )


async def test_unload_restores_core_handlers(hass: HomeAssistant) -> None:
    entry = await setup_voice_timers(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    for name in builtin_takeover.TAKEOVER_INTENTS:
        assert not isinstance(_handler(hass, name), builtin_takeover._TakeoverHandler), name


async def test_start_status_cancel(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass)
    assert await _say(hass, intent.INTENT_START_TIMER, minutes=5, name="pizza") == (
        "Pizza timer set for 5 minutes."
    )
    assert await _say(hass, intent.INTENT_START_TIMER, seconds=30) == (
        "Timer set for 30 seconds."
    )
    assert hass.states.get("sensor.voice_timer_1").state == "active"

    status = await _say(hass, intent.INTENT_TIMER_STATUS)
    assert status.startswith(
        "You have two timers: a pizza timer with 5 minutes left, and a timer with "
    )

    # No name with two running is ambiguous; by name or by length works.
    assert (await _say(hass, intent.INTENT_CANCEL_TIMER)).startswith("Which timer?")
    assert await _say(hass, intent.INTENT_CANCEL_TIMER, start_seconds=30) == (
        "Cancelled the timer."
    )
    assert await _say(hass, intent.INTENT_CANCEL_TIMER, name="Pizza") == (
        "Cancelled the pizza timer."
    )
    assert await _say(hass, intent.INTENT_TIMER_STATUS) == "You have no timers running."


async def test_pause_resume_and_adjust(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass)
    manager = get_manager(hass)
    await _say(hass, intent.INTENT_START_TIMER, minutes=10, name="tea")

    assert await _say(hass, intent.INTENT_PAUSE_TIMER) == "Paused the tea timer."
    assert hass.states.get("sensor.voice_timer_1").state == "paused"
    # Time passing while paused doesn't finish it.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=20))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.voice_timer_1").state == "paused"
    assert await _say(hass, intent.INTENT_PAUSE_TIMER) == "You have no timers running."

    assert await _say(hass, intent.INTENT_UNPAUSE_TIMER) == "Resumed the tea timer."
    assert await _say(hass, intent.INTENT_UNPAUSE_TIMER) == "You have no paused timers."

    assert await _say(hass, intent.INTENT_INCREASE_TIMER, minutes=5) == (
        "Added 5 minutes to the tea timer."
    )
    assert manager.in_use_slots()[0].duration_seconds == 15 * 60
    assert await _say(hass, intent.INTENT_DECREASE_TIMER, minutes=2) == (
        "Took 2 minutes off the tea timer."
    )

    # Taking off more than is left finishes it (and starts ringing).
    await _say(hass, intent.INTENT_DECREASE_TIMER, hours=1)
    await hass.async_block_till_done()
    assert manager.in_use_slots() == []
    assert manager.is_ringing
    assert await _say(hass, intent.INTENT_CANCEL_TIMER) == "Okay."
    assert not manager.is_ringing


async def test_status_lists_every_timer_and_calls_out_paused(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass)
    await _say(hass, intent.INTENT_START_TIMER, minutes=2, name="dinner")
    await _say(hass, intent.INTENT_START_TIMER, minutes=3, name="bath")
    await _say(hass, intent.INTENT_START_TIMER, minutes=10, name="pizza")
    assert await _say(hass, intent.INTENT_PAUSE_TIMER, name="pizza") == (
        "Paused the pizza timer."
    )
    for say in (
        lambda: _say(hass, intent.INTENT_TIMER_STATUS),
        lambda: _converse(hass, "what timers are running"),  # our own sentence
    ):
        assert await say() == (
            "You have three timers: a dinner timer with 2 minutes left, a bath timer "
            "with 3 minutes left, and a pizza timer that's paused with 10 minutes left."
        )
    assert await _say(hass, intent.INTENT_TIMER_STATUS, name="pizza") == (
        "You have one pizza timer that's paused with 10 minutes left."
    )
    assert (await _say(hass, intent.INTENT_CANCEL_TIMER)).startswith(
        "Which timer? You have three timers: a dinner timer"
    )


async def test_status_uses_an_before_vowels(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass)
    await _say(hass, intent.INTENT_START_TIMER, minutes=5, name="oven")
    await _say(hass, intent.INTENT_START_TIMER, minutes=5, name="egg")
    assert (await _say(hass, intent.INTENT_TIMER_STATUS)).startswith(
        "You have two timers: an oven timer"
    )


async def test_cancel_all(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass)
    await _say(hass, intent.INTENT_START_TIMER, minutes=1)
    await _say(hass, intent.INTENT_START_TIMER, minutes=2)
    assert await _say(hass, intent.INTENT_CANCEL_ALL_TIMERS) == "Cancelled all 2 timers."
    assert await _say(hass, intent.INTENT_CANCEL_ALL_TIMERS) == (
        "You have no timers running."
    )


async def test_core_sentences_reach_our_handlers(hass: HomeAssistant) -> None:
    """Phrases only core's intent package knows still end up in our pool.

    No device_id here — core's own handler would refuse ("timers are not
    supported on this device"), so a successful answer proves the takeover.
    """
    await setup_voice_timers(hass)
    manager = get_manager(hass)

    assert await _converse(hass, "set a timer for 3 minutes") == "Timer set for 3 minutes."
    assert len(manager.in_use_slots()) == 1

    assert await _converse(hass, "pause the timer") == "Paused the timer."
    assert await _converse(hass, "resume the timer") == "Resumed the timer."
    assert (await _converse(hass, "add 2 minutes to the timer")) == (
        "Added 2 minutes to the timer."
    )
    assert (await _converse(hass, "remove 1 minute from the timer")) == (
        "Took 1 minute off the timer."
    )
    assert (await _converse(hass, "how much time is left on the timer")).startswith(
        "You have one timer with"
    )
    assert await _converse(hass, "cancel all timers") == "Cancelled your timer."


async def test_cancel_by_length_through_named_sentence(hass: HomeAssistant) -> None:
    """'cancel the 30 second timer' hits our {label} sentence; length still works."""
    await setup_voice_timers(hass)
    await _converse(hass, "set a 30 second timer")
    await _converse(hass, "set a pasta timer for 5 minutes")
    assert await _converse(hass, "cancel the 30 second timer") == "Cancelled the timer."
    assert await _converse(hass, "cancel the five minute timer") == (
        "Cancelled the pasta timer."
    )
    assert await _converse(hass, "cancel the 2 minute timer") == (
        "I couldn't find a 2 minute timer running."
    )


async def test_override_off_core_sentences_go_to_core(hass: HomeAssistant) -> None:
    """Control for the test above: without the takeover, core answers."""
    await setup_voice_timers(hass, override=False)
    assert await _converse(hass, "pause the timer") != "Paused the timer."
    assert get_manager(hass).in_use_slots() == []


async def test_delayed_command_passes_through_to_core(hass: HomeAssistant) -> None:
    await setup_voice_timers(hass)
    handler = _handler(hass, intent.INTENT_START_TIMER)
    calls = []

    class FakeCore(intent.IntentHandler):
        intent_type = intent.INTENT_START_TIMER

        async def async_handle(self, intent_obj):
            calls.append(intent_obj.slots)
            return intent_obj.create_response()

    handler._original = FakeCore()
    await intent.async_handle(
        hass,
        "test",
        intent.INTENT_START_TIMER,
        {"minutes": {"value": 5}, "conversation_command": {"value": "turn off the lights"}},
    )
    assert len(calls) == 1
    assert get_manager(hass).in_use_slots() == []


def test_format_duration() -> None:
    assert format_duration(0) == "0 seconds"
    assert format_duration(1) == "1 second"
    assert format_duration(90) == "1 minute and 30 seconds"
    assert format_duration(3600 + 120 + 5) == "1 hour, 2 minutes and 5 seconds"
