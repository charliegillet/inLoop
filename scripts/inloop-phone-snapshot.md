# Direct phone telemetry for inLoop

The installed `dev.alhinai.fliptracker` update adds one private, atomic JSON snapshot at `files/inloop-telemetry.json`. The foreground service refreshes it every five seconds. inLoop reads it through an authorized ADB connection using `run-as`; it does not expose a phone HTTP port or request additional permissions.

`phone_telemetry.py` validates snapshot age, coordinates and numeric health values. Each reading retains its source timestamp. Missing readings stay missing. A stale or disconnected USB source is labelled unavailable; the existing authenticated phone ingress and website readings remain fallbacks.

## Rebuilding

1. Make an isolated copy of the installed app's matching source. Preserve its existing website upload and direct-Mac upload code. Never edit the reference website checkout.
2. Apply `scripts/inloop-phone-snapshot.patch` to that copy. Increase Android `versionCode` above the installed version.
3. Use the existing private signing keystore and build-time credentials. Never commit `BuildConfig`, APKs, keystores, local Gradle properties or build logs.
4. Build `assembleDebug` with the existing Android SDK and Java 17. Compare the APK signing certificate with the installed APK before installing.
5. Install with `adb install -r` to preserve permissions and application data; never uninstall as an update workaround. Start `.MainActivity` to resume the foreground service.
6. Verify `read_phone()` returns `source=adb`, a snapshot younger than 45 seconds, and actual metric timestamps. Do not log precise GPS or raw health readings in public evidence.

The local isolated build and pre-update APK are in ignored `logs/inloop-phone-build/`. The installed additive update is version code 18 (`1.17-inloop`). `INLOOP_ADB_DEVICE` can override the authorized device used by the Python reader. The Mac and phone IPs appear in the local app's device details; no device serial is sent to the browser.
