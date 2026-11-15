# Architecture and ownership

The active inLoop setup uses Vexo band 43 as the audio and motion hardware. Audio goes directly over Bluetooth to this Mac; the phone supplies GPS and Health data, not caption audio. One bridge owns one active audio source.

```text
Vexo 43 → Bluetooth → Mac Vexo capture + Opus-to-PCM decode
                              ↓
                   authenticated local bridge
                              ↓
                   Pipecat → Deepgram Nova-3
                              ↓
               finalized transcript + speaker turns
                              ↓
                  journal → Markdown + captions
                                         ↓
                             inLoop live transcript
                                         └→ Gemini Decision 1 → suggested task/calendar/action candidates

Phone GPS + Health → private ADB snapshot / authenticated Tailscale ingress → inLoop
Vexo IMU → existing motion preview → Gemini Decision 1 (separate optional preview)
GitHub read-only API → inLoop issues and PRs
```

Pipecat orchestrates speech frames; Deepgram performs recognition and diarization. The local app uses `gemini-decision-1` through the Decisions API to classify exact-source candidates from finalized transcript snippets as `none`, `todo`, `calendar`, or `action_item`. It preserves source wording for resulting item titles; Decision scores fixed choices rather than generating text, dates, or invitations. The standalone motion preview separately uses the same model on raw IMU data; that preview is not required to run inLoop. No new motion-control or emotion classifier is part of this app.

## Component boundaries

| Component | Responsibility |
| --- | --- |
| `config.py` | One non-executing dotenv parser; process values override file values |
| `backend_settings.py` | Backend protocol and validated Deepgram settings |
| `bridge.py` | Authentication, source ownership, backend selection, event creation, persistence ordering and caption fan-out |
| `deepgram_stt.py` | Cloud transport, provider timestamps, bounded recovery and pending-save retry |
| `pipecat_stt.py` + `pipecat_worker.py` | Active private-process Pipecat frame pipeline and official Deepgram STT service; reuses the existing Deepgram source/save state machine |
| `stt.py` + `whisper.py` | Optional local worker lifecycle, replay, speech segmentation and MLX decoding |
| `common.py` | Audio types, bounded queues, quality measurements and local recognition policy |
| `storage.py` | Authoritative journal, idempotent commit, replay and daily projection |
| `tui.py` | Optional terminal caption consumption, search, selection and bookmarks |
| `vexo_source.py` | Single-owner Vexo BLE capture, packet validation and PCM decoding |
| `inloop_app.py` + `web/` | Loopback web app, caption subscription, local sessions/tasks, time-matched GPS and read-only GitHub |
| `phone_telemetry.py` + `inloop_phone_ingress.py` | Phone GPS/Health ingestion with freshness checks and retained reading timestamps |
| `scripts/live_gemini_motion.py` | Existing optional raw-IMU Gemini Decision 1 preview, separate from the caption/task app |
| `diagnostics.py` | Explicit bounded local recording; inactive by default |
| `cli.py` + `vexo` | Consistent command surface; delegates to existing lifecycle and verification implementations |

Deepgram mode does not import the local Whisper adapter or load its model. The viewer reads shared configuration without importing the bridge. Provider-specific reconnect/drain logic remains in each adapter because the transports have different semantics. The active Pipecat process acknowledges audio only after service processing and returns complete terminal metadata before an epoch drains. Its SDK cannot reconnect silently under an existing source clock. There is no additional hosted speech service or queue server beyond Deepgram. inLoop keeps its own local SQLite workspace for sessions, tasks and timestamped GPS fixes; the transcript journal remains authoritative for saved speech. No automatic speech-provider fallback is enabled.

## Audio and caption contract

- Public bridge port: `8787`. Audio ingress: `/v1/listen`. Caption JSON: `/listen`.
- Loopback web app: `http://127.0.0.1:8790`; its browser WebSocket is `/api/live`. Caption/provider credentials stay on the server.
- Loopback-only health: `http://127.0.0.1:8788/health`.
- Binary audio is raw little-endian PCM16, mono, 16 kHz, with complete even-length samples. A WAV container, compressed Opus or different advertised format is rejected. Arbitrary raw bytes cannot independently prove their actual format or physical source.
- Use bearer authorization or the phone-compatible stream-token query parameter. Captions use a separate optional reader token, defaulting to the stream token. Never forward local credentials automatically to a remote viewer URL.
- Send `{"type":"CloseStream"}` to drain. A same-remote reconnect can replace the existing source; stale frames and closes cannot affect its replacement. This is a single-device policy, not multi-tenant identity isolation.
- Legacy phone-audio results retain the Omi `Results`/`segments` compatibility format. Its compatibility speaker label is not speaker identification. Active Deepgram diarization produces anonymous speaker turns, not verified personal identities. Caption events include partials, immutable finals, gaps, status and replay boundaries.

## Guarantees and limits

Accepted audio carries source-session and sample positions. Unsent PCM is bounded to ten seconds / 320,000 bytes and 2,048 packet records; overload records explicit gaps. Partials are provisional and are not saved as final transcripts.

The journal commits before publication and Markdown projection. Recognition results awaiting a failed save are retried without decoding again. Original provider provenance and source identity remain attached. The journal is authoritative; filesystem durability across power loss is not guaranteed.

Caption clients have bounded queues. Slow readers reconnect and replay reliable events rather than silently losing finals. Viewer replay uses the same paragraph rules as live consumption. Source offsets prevent duplicate finals across supported worker recovery paths.

Phone reply overflow or send failure closes that connection with code 1013 and increments `phone_delivery_errors`; journal and caption-viewer delivery continue. Reconnecting the official phone app does not guarantee replay of every missed phone reply.

Whisper remains an explicitly selectable legacy local alternative outside the active inLoop speech route. It uses a separate Python 3.14 process and one prewarmed MLX GPU model. Its eight-second turn cap can split a word. Speculative quiet-settle decoding is reused only after the turn closes with matching speech bounds and no resumed voice. Both recognizers retain pending state in RAM; full bridge crashes can lose unsaved work.

Operational status separates service availability, wearable/audio-source connectivity, audio freshness, provider readiness and saving. Latencies distinguish provider connection, partial/final arrival and persistence. They start from observable Mac/provider stages and exclude unknown wearable/BLE/phone/tunnel delays.

`receipt_to_final_sec` includes segment duration. Provider word-end metrics estimate delay using the original packet receipt clock; `final_word_packet_to_result_sec` measures the containing packet's observed receipt to result handling. None establishes acoustic-to-screen latency. See the [stage audit](OPTIMIZATION.md) for measurements and limits.

## Verification and change process

`./vexo dev test -q` runs offline regressions. CI checks those tests plus shell syntax and whitespace. Real-model/cloud checks are separate, explicit and use temporary bridges. The fault runner exercises eight distinct scenarios; it no longer nests another full unit run or synthesizes unused WAVs.

Dependency installs use the pinned bridge requirements and constraints. The optional Whisper environment is pinned separately. Runtime compatibility checks still permit supported aiohttp 3.x versions; fresh installs use the verified lock.

`/Users/alhinai/vexo-captions` on the Mac is the active deployment. The former Mini deployment is stopped and its Omi autostart/tunnel jobs are disabled. The original checkout and uncommitted state are preserved in the private Mac recovery package described in the [Mac handoff](HANDOFF_MAC.md). Earlier external merged trees and extended experiments remain in the recovery archive. [Archived narratives](archive/README.md) and [evidence receipts](evidence/README.md) retain their original scope. A receipt from a different source hash is historical evidence, not verification of the current build.

## inLoop data boundaries

The app subscribes to the bridge's existing caption stream; it does not open a second Bluetooth connection. It saves finalized events once and treats partials as provisional. Deterministic sentence candidates retain their source IDs and exact text. Gemini Decision classifies those candidates into `none`, `todo`, `calendar`, or `action_item`; only valid responses meeting the provisional confidence threshold are stored in the same local session. Item titles remain extractive source text, not generated summaries. Calendar candidates are review-only suggestions: no calendar API writes, invitations, task execution or other external actions occur automatically. Stored category/model/confidence metadata records the decision provenance; confidence is not a measured accuracy guarantee.

Phone snapshots retain GPS and per-metric Health timestamps. A GPS fix must precede the selected speech and be at most ten minutes old to attach; fixes older than two minutes are labelled last known. Older speech without a suitable fix stays unmatched. The newest phone snapshot does not establish that every underlying reading was just measured. Vexo is not the source of the phone's Health readings.

GitHub is read-only. Its issues/PRs come from the authenticated user's open involved items across repositories; it does not create issues, submit reviews or merge PRs. App mutations require same-origin requests and a local CSRF nonce. Provider keys, phone credentials and private build outputs are never browser assets.
