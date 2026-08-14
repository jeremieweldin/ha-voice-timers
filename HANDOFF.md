# Handoff notes — Voice Timers custom integration

Written by Claude (chat) as a scaffold, intended to be picked up by
Claude Code for the real implementation work. This is genuinely a
skeleton, not a working integration — every file below has been
syntax-checked but none of it has been run against a live Home
Assistant instance.

## Why this exists

Started as a YAML `packages/` automation (`voice_named_timers.yaml` +
`smart_timer_intents.yaml`) — worked, but required hand-provisioning 6
`timer:` helpers + 6 `input_text:` label helpers + 1 `input_boolean:`
per install, entirely unsuited to sharing with other people. This
integration is meant to replace that: a config flow provisions
everything, and the timer-slot count becomes an option instead of a
block of YAML someone has to get exactly right.

## What's real vs. stubbed

| File | Status |
|---|---|
| `manifest.json` | Real, but `version` and repo URLs are placeholders — update before any HACS submission |
| `const.py` | Real — this is the actual contract other files depend on |
| `config_flow.py` | Real — single-instance setup + options flow with all 4 planned options (slots, override toggle, ring interval, ring max) |
| `translations/en.json` | Real — matches config_flow.py's step/field names exactly. **Check this stays in sync if you rename any option key.** |
| `sensor.py` | Structural only. Entities exist and read from `entry.options` on setup, but `start()`/`cancel()`/countdown logic is **not implemented** — see TODOs inline |
| `intent.py` | Structural only. `IntentHandler` classes exist with correct shape, but **the actual sentence-registration mechanism for a custom_component is unverified** — see the big warning at the top of that file before trusting anything else in it |
| `services.yaml` | Real schema, but the service handlers in `__init__.py` are empty stubs |
| `__init__.py` | Wiring is real (forwards to platform, registers services, calls intent setup, listens for options updates); the service handler bodies are stubs |

## Priority order for actually finishing this

1. **Resolve the sentence-registration question first.** Everything
   else is downstream of this. Check
   https://developers.home-assistant.io/docs/voice/intent-recognition/
   and specifically look at how an existing HACS voice-related
   integration (if any comparable one exists) ships its sentences —
   that's more reliable than docs alone for the custom_component-
   specific mechanism, since the dev docs mostly describe how *core*
   integrations do this.

2. **Design the shared timer-state owner** (referenced throughout as
   "TimerManager" but not yet created as a file). The YAML package
   version used per-entity `timer:` helpers, which meant a HA-core
   "finished" event to hook the announcement loop off of. This
   integration owns its own state, so it needs its own equivalent:
   something that
   - holds all N slots' state (replaces the `timer.voice_N` +
     `input_text.voice_N_label` pair from the YAML version)
   - schedules the finish callback (`async_track_point_in_time` or
     similar)
   - owns the repeating-announcement loop after a timer fires,
     independent of the slot's own state (the slot should probably
     reset to idle immediately on finish, same as the YAML version did,
     while a separate ringing-state flag drives the repeat loop —
     mirrors the old `input_boolean.voice_timer_ringing` split for a
     reason: multiple finished timers ringing at once need to share one
     stop-all behavior, not one per slot)
   - This is the natural place for `sensor.py`'s entities to read from
     rather than tracking state independently per-entity.

3. **Implement the three service handlers** in `__init__.py` against
   the TimerManager once it exists.

4. **Wire the intent handlers to call the services** instead of the
   placeholder log lines / canned speech in `intent.py`.

5. **Implement the `override_builtin_timer` branch** in
   `async_setup_intents()` — this is flagged inline in `intent.py`.
   Depends entirely on how sentence registration ends up working (step
   1), since that determines how to express "register set A of
   sentences vs. set B" in the first place.

6. **Live-test slot count changes via the options flow** — right now
   `sensor.py` only reads slot count at initial setup; the `_async_
   update_listener` in `__init__.py` currently only re-runs intent
   setup, not entity add/remove. Decide whether slot-count changes
   should require a reload (simpler, document it) or should add/remove
   entities live (nicer, more code).

7. **Reproduce the response wording behaviors** from the original YAML
   package once the above works — status listing with correct
   pluralization ("You have 2 timers: X with 3 minutes left, and Y with
   1 minute left"), the specific stop-words list, etc. These were
   already tuned once in the YAML version — TODO comments in `intent.py`
   point at where they need to land, but the actual phrasing logic
   should just be ported over, not redesigned.

8. **Before any HACS submission**: fill in real GitHub URLs in
   `manifest.json`, add a LICENSE file, decide on the actual
   `codeowners` GitHub handle, and run through HACS's quality-scale
   checklist (they publish one — required for default-repo inclusion,
   optional but recommended even for custom-repo-only distribution).

## Design decisions already made (don't relitigate without reason)

- **`override_builtin_timer` defaults to `True`.** Explicit product
  decision from the person this was built for — most people replacing
  the stock timer intent want full replacement; the option exists and
  is documented for the minority who want both systems side by side.
- **Sensor domain for timer slots**, not a custom domain and not
  reusing core's `timer:` domain. Reusing core's `timer` domain from a
  custom integration would fight with how that domain's config-entry
  system already works and isn't a supported extension point as far as
  this scaffold's author could tell — flag if you find otherwise, but
  don't spend too long trying to route around this without solid
  evidence it's actually being supported to do so.
- **One device grouping all timer slots** (`device_info` in
  `sensor.py`) rather than N standalone entities, purely for a tidier
  entity list — no functional dependency on this, fine to change.
