# Voice Timers

Named voice timers for Home Assistant Assist — "set a washer timer for
50 minutes" — with repeating ring announcements, installed as a proper
integration instead of a hand-authored YAML package.

**Status: early scaffold, not yet functional.** See `HANDOFF.md` for
what's implemented, what's stubbed, and what needs verifying before
this actually works.

## Planned features

- Set, cancel, and check status of multiple named timers by voice
- Configurable number of timer slots (default 6)
- Repeating "[name] timer is done" announcement until acknowledged or
  a configurable timeout
- **Override built-in timer sentences** (default: on) — when on,
  unnamed commands ("set a timer for 10 minutes") route through this
  integration's timer pool. When off, unnamed commands fall back to
  Home Assistant's built-in timer instead, so both systems can coexist
  if you want to keep using core's plain timer for anonymous timers.

## Installation (once functional)

Via HACS: add this repository as a custom repository, install, restart
Home Assistant, then add the integration from Settings → Devices &
Services → Add Integration → "Voice Timers".

## Migrating from the YAML package version

If you're moving from a hand-authored `voice_named_timers.yaml`
package, remove the old package file and its `timer:`/`input_text:`/
`input_boolean:` helper declarations once this integration is confirmed
working — it recreates that state internally, so the old helpers
become redundant (and would otherwise show up as orphaned entities).
