# Wireless phone GPS and Health

This is a GPS/Health path only. Vexo audio goes directly over Bluetooth to the Mac and Pipecat/Deepgram; it never passes through this phone receiver. Gemini Decision classifies finalized transcript actions in the app, independently of phone telemetry.

The Tailscale integration was originally verified with Android Flip Tracker v1.16 (versionCode17), built from source at:
`/Users/alhinai/Documents/Codex/2026-10-13/ca-x20/work/alhinai.dev/android/flip-tracker`.
The original source checkout and website were not deployed or changed.

- Phone: `main-phone.tail287a74.ts.net`
- Destination: `https://mac.tail287a74.ts.net:8443/api/telemetry/update`
- Tailscale Serve forwards only to the dedicated local receiver `127.0.0.1:8791`; the dashboard is not exposed.
- `inloop_phone_ingress.py` authenticates uploads and atomically writes `logs/phone-telemetry.json` (0600).
- The private credential is `logs/phone-telemetry.token` (0600); never commit it or the APK/build output.
- LaunchAgent `~/Library/LaunchAgents/dev.inloop.phone-telemetry.plist` keeps the receiver running at login.
- inLoop prefers fresh ADB snapshots when the phone is attached. Without ADB it can use authenticated Tailscale snapshots received within 180 seconds, with website telemetry as a further fallback.
- The phone uploads its latest available snapshot once per minute through an independent worker. Website uploading, retry state and credentials remain unchanged.
- Original sensor timestamps are retained; upload cadence does not imply a fresh GPS measurement every minute.

Updated Android source, APK and build log are private under `logs/phone-direct-build/`.
Build uses the existing Android SDK, JDK17 and original signing key in the sibling `android-build` directory of the source checkout. Future builds should inject `INLOOP_TOKEN` through a private build environment; the current private build tree contains the build constant and must remain ignored.

Historical integration verification (versionCode17): phone→Mac Tailscale uploadHTTP200; unauthorized upload401; inLoop state source=tailscale; website received a fresh upload after upgrade. Receiver health: `https://mac.tail287a74.ts.net:8443/health`.

Keep Mac awake and Tailscale connected. No USB is required for telemetry once installed.

The later additive update, versionCode18 (`1.17-inloop`), preserves these uploads and adds private ADB snapshots. See [the current phone snapshot guide](../scripts/inloop-phone-snapshot.md). Its isolated build is under ignored `logs/inloop-phone-build/`. The older `logs/phone-direct-build/` directory is a private source baseline, not a reason to downgrade the installed app.
