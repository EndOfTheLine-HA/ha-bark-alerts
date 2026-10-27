# Changelog

## 0.2.2

- Reconfigure defaults to the existing Broadlink transmitter and offers
  Keep existing beep command when that transmitter is unchanged.
  Camera changes no longer require retyping learned names or pasting RF codes.
- Reuse only the command already stored by this Bark Alerts entry. Raw codes
  are never prefilled into forms or returned in diagnostics. Changing the
  transmitter requires explicit command setup and beep-only confirmation.

## 0.2.1

- Classify Bark Alerts as a service integration so existing monitors appear
  under Settings > Devices & services > Integrations instead of Helpers.
- Preserve all existing monitors, entity IDs, commands, camera selections and
  saved audio. No removal or re-creation is needed; restart HA after updating.
- Retain the configuration category on Armed and Dry run so this navigation
  change does not expose the controls to voice assistants by default.

## 0.2.0

- Select multiple Frigate cameras for one monitor, Armed switch and cooldown.
  Dog-gated animal fallback remains scoped to the triggering camera.
- Default Dry run to off while keeping Armed off on startup and reload.
  Arming with Dry run enabled, in either switch order, creates a persistent
  notification explaining that automatic beeps are blocked. Turning Dry run
  off, disarming or unloading clears it; arming never silently ends a test.
- Add opt-in local history for the latest 25 bark episodes across selected
  cameras, authenticated playback, capture status and an explicit clear action.
  Recordings come from the triggering camera even while disarmed or in cooldown.
- Preserve existing entries and entity IDs. Reconfigure one entry and disable
  redundant entries to consolidate older per-camera monitors.
- Retain the v0.1.4 removal of the Broadlink private-storage reader and typed
  command names. Configuration switches remain excluded from voice assistants
  by default. No automatic transmissions occur during setup or migration.

## 0.1.4

- Remove the Broadlink private-storage reader. Bark Alerts no longer opens or
  parses another integration's `.storage` data.
- Replace learned device/group and command dropdowns with typed name fields.
  Enter existing names exactly as Home Assistant knows them, or enter new names
  and use the receive-only Learn beep button after setup.
- Keep existing config entries compatible. Setup still sends nothing, requires
  beep-only confirmation, and starts disarmed with dry run enabled.
- Update flow text, documentation, audit notes, and regression tests to match
  the public Home Assistant action boundary.

## 0.1.3

- Mark the Armed and Dry run switches as configuration entities. Home Assistant
  does not expose configuration entities to Assist or cloud voice assistants by
  default, so live automatic transmissions cannot be switched on by voice. Both
  switches stay on the device page. If you already exposed them to a voice
  assistant, that exposure is kept; remove it under Settings > Voice
  assistants > Expose if you do not want it.
- Brand test no longer requires an SVG source now that the icon is raster
  artwork (fixes the failing check on main).
- Outcome names, the default entry title and the README use colons instead of
  em dashes, for example "Dry run: no command sent". Existing entry titles are
  unchanged.

## 0.1.2

- Add a learned device/group dropdown for the selected Broadlink transmitter,
  followed by a command dropdown scoped to the selected group. Both accept typed
  names for receive-only learning after setup.
- Read only device/group and command names from Broadlink's local version-1
  store. Never modify its storage or include packets in dropdowns, diagnostics,
  or the resulting named-command config entry. Unsupported/unreadable stores
  fall back to manual entry.
- Separate command-source selection from named-command and raw-code screens.
  Raw-code mode no longer shows irrelevant learned-name fields and never reads
  the learned-command store or prefills a private packet.
- Keep existing config entries compatible, beep-only confirmation mandatory,
  and startup/reload defaults disarmed with dry run on. Setup does not learn,
  transmit, or test a command.
- Add synthetic storage, dependent-dropdown, fallback, privacy, and real HA flow
  regressions. No user RF packets or device names are used in tests.
- Cover configurable two-repetition/two-second-delay requests for direct bark,
  dog-gated animal fallback, and explicit manual tests in named and raw modes.
  Verify one request-counter increment, cooldown, dry-run suppression, saved
  options across reload, and no replay of detections after re-arming.
- Document optional repetitions, post-restart re-arming, stale outcome labels,
  and the difference between a service request and audible reception. Keep the
  one-repetition default and all startup/reload safety behavior unchanged.

After installing this update through HACS, restart Home Assistant and reopen
setup to use the new flow.

## 0.1.1

- Accept Broadlink RF packets with a `B1` header in raw-code mode, with or
  without the `b64:` prefix. Previously these captures were incorrectly rejected.
- Preserve the user's packet unchanged. Strict base64 decoding, packet-size
  limits, declared-payload-length checks, and rejection of IR/unknown headers
  remain in place.
- Add synthetic regression tests for B1 setup, longer packets, and malformed
  inputs. No real learned RF codes are included in tests or source.

After updating/re-downloading through HACS, restart Home Assistant and reopen the
setup flow to load the corrected validator. Updating does not send a command;
the integration still starts disarmed and in dry-run mode.

## 0.1.0

- Initial HACS custom integration: Frigate camera selection, Broadlink RF device
  selection, private beep command configuration, safe defaults, and diagnostics.
