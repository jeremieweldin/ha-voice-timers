# Voice Timers

Named voice timers for Home Assistant Assist — *"set a washer timer for 50
minutes"* — with repeating spoken announcements when a timer finishes,
installed as a proper integration instead of a hand-authored YAML package.

Set, cancel, and check multiple named timers by voice. When one finishes it
announces *"washer timer is done."* on your Assist satellites and repeats until
you say **"stop"** (or a safety timeout elapses). Everything is provisioned by
the config flow — no `timer:` / `input_text:` / `input_boolean:` helpers to
create by hand.

## Features

- Set, cancel, and check status of multiple **named** timers by voice
- Configurable number of timer slots (default 6)
- Repeating *"[name] timer is done"* announcement via `assist_satellite`,
  until acknowledged or a configurable timeout
- One **"stop"** silences every ringing timer at once
- **Replace Home Assistant's built-in timers** (default: on) — every timer
  command goes through this integration's pool, so the built-in satellite
  timers are never used. This doesn't just claim a few sentences: it takes
  over all eight of Home Assistant's built-in timer intents (start, cancel,
  cancel all, add time, remove time, pause, resume, status), so any phrasing
  Home Assistant understands — or an LLM agent's timer tool call — lands
  here. Home Assistant's handlers are put back when the option is turned off
  or the integration is removed. Delayed commands (*"turn off the lights in
  10 minutes"*) are still handed to Home Assistant.
- Pause, resume, and add or remove time on any timer
- One tidy device grouping all slots as `sensor.voice_timer_N` entities
  (`idle`, `active`, or `paused`)

## What you can say

| Say | Does |
|---|---|
| "set a washer timer for 50 minutes" | Starts a named timer |
| "set a 10 minute timer for pizza" | Same, either word order |
| "set a timer for 5 minutes" / "set a 30 second timer" | Unnamed timer (when override is on) |
| "what timers are running" / "how much time is left" | Lists timers with time left |
| "cancel the washer timer" / "cancel the 5 minute timer" | Cancels one timer |
| "cancel all timers" | Cancels every timer |
| "pause the timer" / "resume the timer" | Pauses or resumes a timer |
| "add 5 minutes to the washer timer" / "take 2 minutes off the timer" | Adjusts a timer |
| "stop" / "okay stop" / "thank you" / "cancel the timer" (while ringing) | Silences a ringing timer |

The rows beyond the first three and the original "stop" phrases use Home
Assistant's own built-in timer sentences, so they need the override option
on. With more than one timer running, say which one (by name or length) or
you'll be asked.

## Installation (HACS custom repository)

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/jeremieweldin/ha-voice-timers` as an **Integration**.
2. Install **Voice Timers**, then **restart** Home Assistant.
3. Settings → Devices & Services → **Add Integration** → **Voice Timers**.
4. Use the integration's **Configure** button to set slot count, ring behavior,
   the built-in-timer override, and which satellites to announce on.

Requires Home Assistant 2024.12 or newer, and at least one `assist_satellite`
device for the spoken announcements.

## How it works (and a note on sentences)

Home Assistant's conversation agent only loads custom voice sentences from
`config/custom_sentences/<language>/`, and custom integrations can no longer
register sentences programmatically. So on setup this integration **writes**
`config/custom_sentences/en/voice_timers.yaml` and reloads the conversation
agent; on uninstall it removes that file. You don't need to touch it — but if
you ever want to tweak the phrasing, that's where it lives (it will be
overwritten when options change or the integration reloads).

## Options

- **Number of timer slots** — how many named timers can run at once.
- **Override built-in timer sentences** — see Features above.
- **Ring announcement repeat interval** — seconds between repeats (default 8).
- **Stop ringing automatically after** — safety cutoff in minutes (default 5).
- **Announce on these satellites** — leave empty to announce on all of them.

## Migrating from the YAML package version

If you're moving from a hand-authored `voice_named_timers.yaml` /
`smart_timer_intents.yaml` package: once this integration is confirmed working,
remove those package files and their `timer:` / `input_text:` /
`input_boolean:` helper declarations. This integration recreates that state
internally, so the old helpers become redundant orphaned entities. Also remove
any old `custom_sentences` entries for the same phrases to avoid double matches.

## Development

Tests run against a real Home Assistant core via
`pytest-homeassistant-custom-component` (Linux/WSL, Python 3.13):

```bash
pip install -r requirements_test.txt
pytest tests
```

## License

MIT — see [LICENSE](LICENSE).
