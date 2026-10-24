<p align="center"><img src="custom_components/bark_alerts/brand/icon@2x.png" alt="Bark Alerts: camera detection and RF dog collar" width="256" height="256"></p>

# Bark Alerts — Automatic RF Dog-Collar Beeps from Frigate Bark Detection

A Home Assistant integration that turns **Frigate dog-bark detections into
automatic beep-only RF commands for a compatible dog collar**, sent through
Broadlink. Choose a Frigate camera, choose your Broadlink device, and configure
your own collar's learned beep command. No YAML or manual entity-ID mapping is
needed.

> [!WARNING]
> **An incorrectly learned or selected RF command could activate SHOCK instead
> of a beep. Read this before setup or testing.**
>
> Bark Alerts is intended for **beep-only use**. It cannot inspect an RF command
> and verify whether the collar will beep, vibrate, or deliver a shock. Naming a
> command `beep` or checking the beep-only confirmation does **not** make it safe.
> A wrong button, collar channel, saved command, or raw code can cause an
> unintended action, and automatic detections or configured repetitions can
> repeat that action.
>
> **Never learn, select, or automate shock or vibration commands. Remove the
> collar from the animal before learning or testing, and verify the actual
> response of the intended receiver before enabling automatic operation.**
> Recheck after relearning a command or changing the remote, receiver, channel,
> or configuration. Do not enable automation if the command's effect is uncertain.
>
> **Test beep (sends RF) transmits even with Armed off or Dry run on.** Those
> switches protect automatic operation; they do not block an explicit manual
> test. Disarming cannot cancel a command already sent or handed to Broadlink.
>
> Frigate can misclassify sounds and cannot establish which dog barked.
> Keep automatic operation disabled until you have checked detections in dry
> run, disable other automations targeting the collar, and supervise initial
> operation. Cooldowns are per entry, so multiple entries or other automations
> can produce additional commands.

This is an alerting companion, not a new audio classifier. Frigate performs the
audio/object detection; Bark Alerts connects those detections to an existing
Broadlink RF remote. No Frigate patches, cloud accounts, or copied household
configuration are required.

## Tested hardware and compatibility

The maintainer uses and has tested this integration with **one FunniPets
remote-controlled dog collar**, using its **beep command only**. The supplied
product listing describes the FunniPets two-collar set with beep, vibration,
and static-shock modes; **only one collar was used in integration testing**.

This is a limited compatibility report, not a guarantee for every FunniPets
model or hardware revision. Multi-collar operation, other collar models, and
shock/vibration operation have not been validated here. Shock and vibration
are outside this integration's intended use. A collar's brand or appearance
alone does not establish RF compatibility.

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

Version **0.1.2** adds learned-device and command dropdowns and separates raw-code
setup from named-command setup. It includes the 0.1.1 `B1` packet fix. See
[CHANGELOG.md](CHANGELOG.md). After updating, restart Home Assistant and reopen
setup; an already-open flow uses old code.

1. Add `https://github.com/EndOfTheLine-HA/ha-bark-alerts` to HACS custom
   repositories, category **Integration**, and download **Bark Alerts**.
2. Restart Home Assistant.
3. Add **Bark Alerts** through **Settings → Devices & services**.
4. Choose your **Frigate camera**, then your **Broadlink device**.
5. Choose a command source:
   - **Named command:** choose a saved device/group from the dropdown, then
     choose its beep command on the next screen. Only names from the selected
     Broadlink transmitter are listed. Both dropdowns also accept a typed name:
     for a new command, enter the names to use and press **Learn beep (receive
     RF)** on the new integration device afterward.
   - **Raw RF code:** the next screen shows only the private code field and
     beep-only confirmation. Paste your own captured Broadlink base64 RF packet.
     The optional `b64:` prefix is accepted. The field is masked; the code remains
     in your local HA config entry, not this repository.
6. Review the warning above and the default settings. The beep-only confirmation
   is your acknowledgement, not an automatic check of the RF command. Verify the
   receiver's actual response off the animal before enabling automatic operation.

The wizard does not send, learn, or physically test anything. The dropdowns use a
read-only lookup of the selected remote's local Broadlink version-1 code store;
only device/group and command names reach the forms. The lookup never changes
that store, copies packets into this integration, or reads other transmitters'
stores. It is a compatibility adapter, not a public Broadlink listing API.
Missing, unreadable, oversized, or unrecognized stores fall back to typed names.
Commands saved only in the Broadlink app, or raw codes embedded directly in HA
scripts, do **not** appear in these dropdowns. A name does not prove a command is
RF-compatible or beep-only; verify its effect before confirming it.

## First use and controls

New entries start with **Armed off** and **Dry run on**. Every HA restart, entry
reload, options change, or reconfiguration returns to those safe defaults. You
must re-arm explicitly; there is no automatic startup beep.

**After restarting or updating:** check **Sources ready**, explicitly turn
**Armed on**, and leave **Dry run on** while checking detection. Only turn
**Dry run off** when ready for automatic transmissions. Saved repetition and
cooldown options survive a restart; the live enable switches and counters do not.
Sources ready does not mean the entry is armed, and arming does not replay
detections that occurred while disarmed.

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

## Repetitions and troubleshooting

The default remains **one repetition** with a **one-second repetition delay**.
If a known beep command is received inconsistently, an optional setting is
**Beep command repetitions: 2** and **Delay between repetitions: 2 seconds**.
This requests two transmissions from Broadlink, so two audible beeps may be
expected. It is not a universal compatibility fix or a delivery guarantee.
Change one setting at a time and verify the effect with the collar **off the
animal**. Changing options reloads the entry and returns it to disarmed/dry-run;
check the saved values before explicitly re-enabling automatic operation.

One alert increments `command_requests` once, even when that request includes
two or three repetitions. The counter does not measure RF packets or audible
beeps. Configured repetitions are distinct from an automatic retry after failure;
the integration does not add retries or queue a later alert.

When an expected beep is missing:

1. Check the actual **Armed** and **Dry run** switches first, especially after a
   restart, reload, options change, or reconfiguration. **Last outcome** describes
   the previous processed event; it can still say `disarmed` after you re-arm.
2. Check the selected camera's bark/animal source history and **Last detection**.
   A sound that remains `on` is not a new event: it must return to `off` and then
   turn `on` again. An animal-sound fallback also needs that camera's recently
   observed dog occupancy in the current session.
3. Check the recorded outcome. `dry_run`, `dog_not_recent`, `cooldown`, `busy`,
   `source_unavailable`, and `remote_unavailable` identify different gates;
   they are not confirmations of a transmitted command.
4. If the outcome is **Command requested — reception not confirmed**, the remote
   service returned without raising an error to Bark Alerts. Broadlink can log
   some transmission failures without raising them. Privately review its logs
   and check receiver power, range, and interference. Do not publish logs or
   traces that may contain private codes.
5. Verify the manual command off the animal, then separately verify a new natural
   detection. A manual test bypasses arming/dry-run and source gates; its success
   alone does not prove automatic detection, and dry-run success does not prove
   physical delivery. Keep any legacy automation disabled during the live check
   to avoid duplicate senders.

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
