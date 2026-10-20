# Changelog

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
