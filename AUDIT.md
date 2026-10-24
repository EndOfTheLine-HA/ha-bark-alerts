# Source, privacy, and verification audit

Release review: 2026-10-23

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
- For 0.1.2, Broadlink's version-1 learned-code store key/envelope and grouped
  command structure, reviewed against the pinned
  [Core remote implementation](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/broadlink/remote.py).
  There is no public listing action; the compatibility adapter reads only the
  selected remote's store in an executor and returns names, not packet values.
  It does not call Store migration/save methods or access live remote internals.
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
Learned-name discovery never logs storage exceptions or includes packet values in
forms/config entries. It validates the selected remote's registry-derived store
identifier, reads only that one file with a size bound, and checks the storage
version, key, and data shape. Missing/unreadable/unknown storage falls back to
typed names. Dropdown labels cannot establish a command's physical effect.

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
- Version 0.1.1 compatibility regressions cover `B1` raw-code input, optional
  `b64:` prefixes, longer synthetic packets, and setup without transmission.
  Malformed framing, oversized data, IR packets, and unknown headers remain
  rejected. No real captured codes are used as fixtures.
- Compatibility checks use synthetic packet fixtures only; no user-owned command
  value is stored in source, fixtures, logs, or diagnostics.

Version 0.1.2 adds synthetic tests for names-only storage reads, transmitter/group
isolation, malformed/unknown/oversized/unreadable stores, path validation,
dependent dropdowns, manual-name fallback, required confirmation, separate raw
setup with no store read or packet prefill, mode changes, and real HA lifecycle
reconfiguration. Storage tests assert that existing bytes stay unchanged and
missing stores are not created.

Release regressions also cover two repetitions with a two-second delay in both
command modes for direct bark, same-camera animal fallback, and explicit manual
tests. They assert one remote service request and one request-counter increment,
not two independently confirmed RF transmissions. Cooldown and dry-run gates
remain in effect. The HA lifecycle test preserves repetition settings across an
options reload and explicit entry reload while resetting the enable switches.
Re-arming does not replay a retained detection from the disarmed interval.

The updated suite has 112 passing tests. A native HA HTTP-library deprecation
warning appears in the lifecycle test; it is not an RF or integration failure.
Tests do not contact a physical transmitter.

## Hardware and publication boundary

- The automated suite never deploys to a live HA instance, changes an existing
  automation, alters Frigate, learns a real code, or contacts a transmitter.
- Physical validation is installation-specific. Any private hardware-check
  records stay outside this repository. This audit does not certify a collar
  model or establish universal delivery, false-positive rates, range, receiver
  sleep behavior, battery performance, or RF-learning reliability.
- No automated test provides independent audible-receipt verification,
  long-duration hardware soak coverage, or a real multi-entry contention test.
- A versioned GitHub release and HACS custom-repository installation are not
  default-catalog acceptance or a production rollout. Publication never changes
  live HA switches or automatically migrates a legacy automation.

## Publication checks

The source repository is `EndOfTheLine-HA/ha-bark-alerts`. Its GitHub Actions
workflow runs pytest, Ruff, HACS, and Hassfest on pushes and pull requests. Check
the latest commit's Actions results for the current remote validation status;
the local checks above do not substitute for those results.

Before a public release, run the GitHub validators and perform a staged,
off-animal hardware check with user-owned codes. Disable the legacy bark
automation before enabling automatic sends on the same equipment.
