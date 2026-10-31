# Handoff / status notes — Voice Timers custom integration

**Status: implemented, tested against HA core, not yet on the live box.**
v0.2.0 added the built-in timer takeover (below) and a pytest suite that
runs against real Home Assistant core (2026.2) including the default
conversation agent — see `tests/`. It has **not yet been run on the live
HAOS instance** — see the live-test checklist at the bottom.

## v0.2.0: built-in timer takeover

Goal: the satellites' built-in timers must never be used. Claiming our own
sentences wasn't enough — core's intents package has far more timer phrasing
("pause the timer", "add 5 minutes", "how much time is left"), which would
still reach core's handlers. So with `override_builtin_timer` on,
`builtin_takeover.py` replaces core's handlers for all eight timer intents
(`HassStartTimer`, `HassCancelTimer`, `HassCancelAllTimers`,
`HassIncreaseTimer`, `HassDecreaseTimer`, `HassPauseTimer`,
`HassUnpauseTimer`, `HassTimerStatus`) with ones that drive `TimerManager`,
and restores core's on unload / option off. Notes:

- Works because the default agent only renders core's canned response when
  the handler set no speech — ours always sets speech.
- Core's handlers are registered by the `intent` component, which
  `manifest.json` now lists as a dependency, so ours always register after.
- Core's `slot_schema`/`description` are borrowed, so LLM agents' timer tools
  keep working and also land in our pool.
- `HassStartTimer` with a `conversation_command` slot (a delayed command,
  "turn off the lights in 10 minutes") is passed to core's original handler.
- The manager gained pause/resume, add/remove time (removing past zero
  finishes the timer, like core), cancel-all, and lookup by name or original
  length. "cancel the timer" while one is ringing just silences it.

Also fixed in v0.2.0 (both found by the new tests, both would have hit the
live box): HA auto-calls `intent.py`'s `async_setup_intents(hass)` as an
intent platform with one argument, which crashed on the old two-argument
signature; and the "already registered" flag was a module global instead of
per-hass.

## Why this exists

Started as a YAML `packages/` automation (`voice_named_timers.yaml` +
`smart_timer_intents.yaml`) — worked, but required hand-provisioning 6
`timer:` helpers + 6 `input_text:` label helpers + 1 `input_boolean:`
per install, unsuited to sharing. This integration replaces that: a config
flow provisions everything, and the slot count is an option. Behavior
(wording, stop-words, status phrasing, announce loop) was ported from the
original YAML, not redesigned. The originals are archived in
`original_timer_source.zip` at the repo root (reference only — safe to delete
or gitignore; not part of the shipped integration).

## The linchpin question, resolved

The scaffold flagged "how does a custom_component ship sentences?" as the
open question everything depended on. Answer:

- HA's default conversation agent loads sentences ONLY from the bundled
  `home_assistant_intents` package and from `<config>/custom_sentences/<lang>/`.
  It does **not** scan `custom_components/`.
- The programmatic `async_register_sentence()` was **removed in HA 2025.10.1**.

So the integration **writes `config/custom_sentences/en/voice_timers.yaml`
itself** at setup and calls `conversation.reload`; it removes the file on
uninstall. Intent *handlers* are still registered from Python via
`intent.async_register`. This lives in `sentences.py`. `override_builtin_timer`
controls whether the two bare "set a timer for N minutes" patterns are written.

## Architecture (as built)

- `timer_manager.py` — `TimerManager`, the single source of truth per entry:
  N slots, `async_start`/`async_cancel`/`async_stop_ringing`, finish scheduling
  via `async_track_point_in_time`, one shared ring loop (`assist_satellite.
  announce`, repeats every `ring_repeat_seconds` up to `ring_max_minutes`),
  a dispatcher signal that sensors re-render on, and `parse_minutes()` (spoken-
  number fallback). `get_manager(hass)` resolves the single instance.
- `sentences.py` — generates + installs/removes the custom-sentences YAML.
- `__init__.py` — builds the manager, wires the 3 services to it, installs
  sentences, and reloads the whole entry on any options change.
- `sensor.py` — thin read-only views over the manager (idle/active + attrs).
- `intent.py` — handlers call the manager; wording ported from the YAML.
- `config_flow.py` — single-instance setup + options (slots, override, ring
  interval, ring max, announce targets). Uses the modern OptionsFlow pattern
  (no manual `self.config_entry` assignment).

## Live-test checklist (do this on the HAOS instance)

1. Install via HACS custom repo, restart, add the integration. Confirm N
   `sensor.voice_timer_*` entities + one device, and that
   `config/custom_sentences/en/voice_timers.yaml` was written.
2. Voice: set named + unnamed timers; "what timers are running" (check
   pluralization); cancel by name (hit + miss); let one finish → repeating
   announcement on satellites; "stop" silences it; confirm the ~5-min cutoff.
3. Options: change slot count (entities add/remove after the auto-reload),
   toggle override (bare "set a timer for N minutes" routing changes), pick a
   specific announce target.
4. Remove the integration → sentences file gone, phrases stop matching.
5. Takeover (on a real satellite, e.g. Voice PE): "set a timer for 2
   minutes" must NOT show the satellite's own LED/countdown timer; "pause the
   timer", "add a minute to the timer", "how much time is left" answer from
   our pool; the HA log shows "took over built-in timer intents" once.
6. Before step 3's override toggle, remove the old YAML packages
   (`voice_named_timers.yaml`, `smart_timer_intents.yaml`): their sentence
   triggers are checked before intents and would shadow these.

### Things most likely to need a tweak after real testing

- **`{vt_label:label}` wildcard capture** — hassil wildcards can be greedy;
  the original relied on the literal word "timer" as an anchor. Verify named
  set/cancel capture the label cleanly and don't swallow extra words.
- **Override precedence** — with override on, confirm the bare pattern actually
  wins over core's built-in timer intent (may need testing both prefer-local
  and agent settings).
- **Generic stop words** ("stop", "thank you", "thanks") are claimed globally
  and answer "Okay." even when nothing is ringing (faithful to the original).
  Easy to scope to only-when-ringing if it hijacks other phrases.
- **Spoken numbers** — `{vt_minutes}` is a range list (hassil should handle
  "five" and "5"); `parse_minutes()` is a fallback. Verify word-numbers.

## Before a public HACS submission

Repo URLs/codeowner (`@jeremieweldin`) and a LICENSE (MIT) are in place. Bump
`manifest.json` `version` per release and tag it. Run HACS's quality-scale
checklist if aiming for default-repo inclusion.
