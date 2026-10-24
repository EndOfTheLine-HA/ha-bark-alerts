# Changelog

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
