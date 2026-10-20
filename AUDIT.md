# Source, privacy, and verification audit

Date: 2026-10-20

## Scope and provenance

This is a new Home Assistant helper integration, not a copy of a private HA
configuration or a fork of Frigate/Broadlink. The starting behavior was reviewed
read-only: direct bark detection and an optional same-camera, recent-dog-gated
animal-sound fallback. The implementation is generic and uses existing HA
entities and native remote actions.

Reviewed interfaces:

- Frigate Home Assistant integration 5.15.6 camera/audio/occupancy registry-ID
  formats and per-camera device associations.
- Home Assistant 2026.10.2 config flows, entity/device registries, state events,
  entity platforms, and Broadlink remote actions/RF-capability registration.
- Official Frigate audio/MQTT and Home Assistant Broadlink documentation linked
  from the README.

The camera lookup uses registry identifiers and device/config-entry ownership,
not household entity-name suffixes or friendly-name guesses. A renamed source
continues to resolve to the selected entity. Another camera cannot satisfy the
optional dog gate.

## Physical actions and defaults

- Setup does not learn, transmit, or test a code.
- Every new setup, startup, reload, or reconfigure is disarmed and in dry run.
- Automatic transmission requires explicit arming and disabling dry run.
- The clearly labelled manual test button intentionally bypasses those two
  toggles, but still obeys cooldown and busy-operation rejection.
- The learning button explicitly delegates receive-only RF learning to
  Broadlink and may overwrite the same learned group/command name. It is not
  a guarantee of capture and does not send a test beep afterward.
- There is one in-flight operation per entry, no delayed beep queue, and no
  automatic retry after errors. Cooldown applies per entry, not globally.
- Stop/unload detaches listeners and cancels tracked work. It cannot recall a
  command already requested/transmitted by the underlying service.
- Only beep usage is in scope. Code validation cannot prove what a user's
  arbitrary packet or learned command actually does.

## Private material excluded

No real RF codes, household entity IDs, private network addresses, device MACs,
tokens, home audio/video, calibration data, camera maps, or HA backups were
copied into this package. Packet tests generate small synthetic byte sequences.

Raw commands entered by a future user remain in that user's local config entry
and HA backups. Integration diagnostics exclude payloads, command/group names,
source identifiers, and device names. Exceptions from remote services are not
echoed by this integration because they can contain codes. Native HA/Broadlink
logs, action traces, and local config exports still require private handling.

## Completed local validation

- Ruff lint and formatting checks.
- Integration imports with Home Assistant 2026.10.2 on Python 3.14.
- Automated tests with isolated HA registries, state machines, config-flow
  manager, real entity platforms, and fake remote service handlers.
- Camera → Broadlink → command → settings flow; missing/disabled sources and
  IR-only devices rejected; optional fallback requires both same-camera sources.
- Actual HA setup of all eight named-command-mode entities, options reload,
  same-pair reconfiguration, duplicate-pair rejection, and unload.
- Safe defaults, dry run, per-entry cooldown, burst rejection, unavailable
  devices, stale/retained/startup events, same-camera gating/expiry, and entity
  renames.
- Explicit manual test behavior, native RF-learning delegation, generic failure
  reporting, cancellation, raw-code handling, and diagnostics redaction.
- HACS layout, metadata, translation parity, and absence of embedded private
  addresses or real RF payloads in the integration source.
- Local 256/512-pixel PNG brand assets generated from the included original SVG.
  The community icon is not an official Frigate, Broadlink, or collar logo.

The test suite currently contains 58 passing tests. A native HA HTTP-library
deprecation warning appears in the lifecycle test; it is not an RF or integration
failure. Tests do not contact a physical transmitter.

## Not yet verified or performed

- No live HA deployment, existing-automation migration, Frigate changes, RF
  learning, or physical transmission was performed while building this project.
- No end-to-end camera/audio/Broadlink/collar test or independent audible-receipt
  verification. False-positive rates, range, receiver sleep, battery behavior,
  RF learning reliability, and model-specific compatibility remain unvalidated.
- No long-duration soak or multi-entry contention test against real hardware.
- No release or default-catalog submission. Repository publication and automated
  GitHub validation are separate from a physical validation or production rollout.

## Publication checks

The source repository is `EndOfTheLine-HA/ha-bark-alerts`. Its GitHub Actions
workflow runs pytest, Ruff, HACS, and Hassfest on pushes and pull requests. Check
the latest commit's Actions results for the current remote validation status;
the local checks above do not substitute for those results.

Before a public release, run the GitHub validators and perform a staged,
off-animal hardware check with user-owned codes. Disable the legacy bark
automation before enabling automatic sends on the same equipment.
