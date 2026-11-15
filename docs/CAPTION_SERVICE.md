# Vexo caption service

The active inLoop speech path is:

```text
Vexo band 43 → Bluetooth → Mac bridge → Pipecat → Deepgram Nova-3
                                                  ↓
                                       Transcript + speaker labels
                                                  ↓
                                      Journal → inLoop + notes
```

Vexo connects directly to the Mac. The Android phone supplies GPS and Health telemetry; it does not relay wearable audio. Deepgram performs speech recognition and diarization. The bridge assigns timestamps, saves finals, and publishes captions. Speaker labels distinguish voices; they are not verified personal identities.

## Daily use

From the project directory on the configured Mac:

```sh
./vexo status
./vexo check
./inloop
```

`./vexo captions` opens the terminal viewer. Closing a viewer leaves capture running. Raw audio is not recorded by default.

The bridge and capture worker have separate lifecycles. Do not start another receiver when a source already owns the band. After a deliberate source stop, start the configured service and receiver with:

```sh
./vexo start
./vexo source vexo --band 43 --transport ble
```

If discovery is needed, double-tap band 43 to open its advertising window. The source runs in the foreground; Ctrl+C disables the microphone and drains accepted audio. Stop capture before stopping or restarting the bridge.

| Command | Purpose |
| --- | --- |
| `./vexo status --json` | Inspect source, provider, pipeline, audio flow, and saving |
| `./vexo check` | Check configuration, dependencies, and live health |
| `./vexo captions` | Open the terminal viewer |
| `./vexo verify --phrase "Blue lantern seven" --timeout 60` | Verify an intentionally supplied phrase and saved captions |
| `./vexo start`, `./vexo stop`, `./vexo restart` | Manage the bridge; coordinate source shutdown first |

## Setup

The active configuration is `OMI_STT_BACKEND=deepgram`, `OMI_DEEPGRAM_PIPELINE=pipecat`, and enabled diarization. Existing `OMI_*` setting names and journal filenames remain compatibility identifiers, not a requirement for an Omi phone streamer.

The bridge uses CPython 3.15 in `.venv`; Pipecat runs in its isolated Python 3.14 environment. Capture uses `.venv-vexo`. Dependencies are pinned in the corresponding requirements and lockfiles. Preserve existing private `.env` settings during upgrades.

Deepgram credentials stay private. Pipecat streams audio to Deepgram and publishes provisional/final results; the bridge owns reconnection, source timing, and persistence. Measure the complete path before claiming a specific latency. See [Vexo setup](VEXO.md) and [operations](OPERATIONS.md) for installation and recovery.

## Action suggestions

After finalized captions reach inLoop, `gemini-decision-1` classifies transcript candidates as to-do, calendar suggestion, other action item, or no action. Suggestion text is taken from the transcript. Calendar suggestions are reviewable local records; no external calendar event is created automatically.

Gemini Decision is not part of speech recognition and does not supply speaker labels. [The app guide](INLOOP.md) describes its data flow and storage.

## Checks

```sh
./vexo dev test -q
./vexo dev faults
bash -n vexo run.sh tui.sh
git diff --check
```

For an explicit isolated Pipecat/Deepgram check:

```sh
./vexo dev smoke --backend deepgram --pipeline pipecat
```

This sends synthetic test audio to Deepgram using temporary ports and notes; it does not switch or restart the running service. Offline tests do not need a microphone or cloud credentials.

## Historical alternatives

The codebase retains older direct-Deepgram, local-Whisper, and Omi-phone paths for historical tests and explicit maintenance. They are not the active inLoop speech configuration and are not automatic fallbacks. Historical measurements and verification receipts describe the builds that produced them.

See [architecture](ARCHITECTURE.md), [verification evidence](evidence/README.md), [the recovery archive](archive/README.md), and [the Mac handoff](HANDOFF_MAC.md) for deeper context.
