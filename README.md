# Bark Alerts for Home Assistant

Choose a Frigate camera, choose your Broadlink device, and configure your own
collar's **beep-only** command. No YAML or manual entity-ID mapping is needed.

This is an alerting companion, not a new audio classifier. Frigate performs the
audio/object detection; Bark Alerts connects those detections to an existing
Broadlink RF remote. No Frigate patches, cloud accounts, or copied household
configuration are required.

## Requirements

- Home Assistant **2026.10.2 or newer**.
- The [Frigate Home Assistant integration](https://github.com/blakeblackshear/frigate-hass-integration)
  configured with at least one individual camera. Modern registry identifiers
  are required; the source interface was reviewed against integration 5.15.6.
- [Frigate audio detection](https://docs.frigate.video/configuration/audio_detectors/)
  enabled for that camera, with `bark` in its listen labels. Its Home Assistant
  bark binary sensor must be enabled. Birdseye is not a supported source.
- An RF-capable device configured through Home Assistant's
  [Broadlink integration](https://www.home-assistant.io/integrations/broadlink/),
  exposing a remote and an RF transmitter. IR-only mini devices are not RF
  transmitters, even though they also have a remote entity.
- A compatible collar, its original remote, and your own learned beep command.
  Selecting a transmitter does not discover a collar or generate its RF code.
  RF band, encoding, and receiver compatibility still matter; not every collar
  can be controlled by Broadlink.

Optional animal-sound fallback additionally requires enabled `animal` audio and
`dog` occupancy sensors from **the same camera**.

## Install with HACS

Version **0.1.1** fixes rejection of raw RF captures with a `B1` packet header.
See [CHANGELOG.md](CHANGELOG.md). If updating from 0.1.0, restart Home Assistant
and reopen setup after the HACS download; an already-open flow uses old code.

1. Add `https://github.com/EndOfTheLine-HA/ha-bark-alerts` to HACS custom
   repositories, category **Integration**, and download **Bark Alerts**.
2. Restart Home Assistant.
3. Add **Bark Alerts** through **Settings → Devices & services**.
4. Choose your **Frigate camera**, then your **Broadlink device**.
5. Choose a command source:
   - **Named command:** enter the device/group and beep command names already
     learned by Broadlink. To learn a new command, enter the names to use and
     press **Learn beep (receive RF)** on the new integration device afterward.
   - **Raw RF code:** paste your own captured Broadlink base64 RF packet. The
     optional `b64:` prefix is accepted. The field is masked; the code remains
     in your local HA config entry, not this repository.
6. Confirm it is beep-only and review the default settings.

The wizard does not send, learn, or physically test anything. It does not inspect
Broadlink's private code storage to list or verify learned commands.

## First use and controls

New entries start with **Armed off** and **Dry run on**. Every HA restart, entry
reload, options change, or reconfiguration returns to those safe defaults. You
must re-arm explicitly; there is no automatic startup beep.

1. For a new named command, press **Learn beep (receive RF)** and follow the
   native Broadlink notifications. Press only the original remote's beep button.
   Learning the same device/group and command name again can overwrite that
   learned command. Use distinct names when appropriate.
2. The learning action may return without guaranteeing capture. Verify Broadlink
   notifications/logs and the learned result. Some RF devices have learning
   problems; privately captured raw RF codes are an alternative, not a guarantee
   of compatibility. No custom fixed-frequency capture tool is bundled.
3. With the collar **off the animal**, use **Test beep (sends RF)** only when
   ready for a physical test. This explicitly sends even while disarmed or in
   dry-run mode. It still respects cooldown and cannot queue a later test.
4. Turn **Armed on** while leaving **Dry run on** to observe detections without
   sending commands. The outcome sensor records what would happen.
5. Only after validating detection and the command, turn **Dry run off** to
   permit automatic beep requests. Disarm at any time to stop new requests.

Detection rules:

- Direct bark events use the selected camera's bark sensor.
- Optional animal fallback requires a fresh dog occupancy transition from that
  camera in this HA session. A continuously present, freshly observed dog also
  qualifies. A dog seen by another camera never authorizes the fallback.
- Only `off` → `on` sensor transitions count. Initial states, retained `on`,
  recovery from `unknown`/`unavailable`, and attribute-only updates are ignored.
  A sensor must return to `off` before its next event can trigger.
- Default cooldown is 30 seconds, configurable from 5 to 3,600 seconds. Default
  repetitions are one, with a maximum of three. Dry runs use the same cooldown.
- Busy events are discarded. There is no delayed RF queue or automatic retry,
  including after a failed request or an integration unload.

The device exposes Armed, Dry run, Sources ready, Last outcome, Last detection,
Last command request, and the explicit test/learning buttons. Outcome counters
are session-only. `bark_alerts_alert` events contain only the entry ID, source
(`bark`, `animal`, or `manual`), and outcome—not command payloads.

Use **Configure** for cooldown/fallback/repetition settings. Use **Reconfigure**
to choose another camera, Broadlink device, or command. Multiple entries can
target one transmitter; cooldown is per entry, not global across entries or
other automations. Do not pair multiple noisy sources to one collar without
reviewing their combined behavior.

## Safety, privacy, and limitations

- **Beep only.** No shock/vibration features or example codes are provided.
  The integration cannot determine what an arbitrary user-supplied RF command
  actually does. Beep confirmation is not technical proof of the command's effect.
- Never rely on a sound classifier to identify which animal barked or to make
  welfare/safety decisions. Background audio and other animals can cause errors.
- A successful service return means **command requested**, not verified RF
  delivery or an audible beep. Broadlink may swallow some transmission errors;
  receiver sleep, range, batteries, and interference can prevent reception.
- Disarming/unloading cannot undo a radio command already requested/transmitted.
- RF codes are private control credentials, not encrypted secrets in HA backups.
  Keep backups, raw codes, home audio, entity registries, and household details
  private. Integration diagnostics omit commands, codes, names, and source IDs;
  Home Assistant/Broadlink logs and service traces may still contain them.
- Disable any existing bark-to-collar automation before arming this integration
  against the same equipment. No automatic migration or live deployment occurs.

## Development and verification

```sh
uvx ruff check .
uvx ruff format --check .
uv run --python 3.14 --with homeassistant==2026.10.2 --with pytest --with pytest-asyncio python -m pytest -q
```

Tests use isolated Home Assistant registries/state events and mocked remote
services. No real transmitter is contacted. GitHub workflows are included for
pytest, Ruff, HACS, and Hassfest. See the latest commit's Actions results and
[AUDIT.md](AUDIT.md) for the verification boundary.

The original community icon source is `custom_components/bark_alerts/brand/icon.svg`.
Its 256/512-pixel PNG renders are included for HACS branding; it is not an
official manufacturer logo.

MIT licensed; community software, not affiliated with Frigate, Broadlink, or any
collar manufacturer. HACS custom-repository installation and default-catalog
inclusion are separate publication stages.
