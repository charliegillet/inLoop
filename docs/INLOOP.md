# inLoop

Run `./inloop` from the project directory, or double-click `inLoop.command`.
The launcher starts the local app when needed and opens <http://127.0.0.1:8790>.
Use `./inloop --no-open` to start without opening a browser. No frontend build or npm runtime is needed.

inLoop reads the existing caption stream; it does not open another Bluetooth connection or start/stop microphone capture. Keep the existing capture service running. Closing the browser leaves capture and the local app running.

The interface uses real caption, device, GPS and Health data where available, plus read-only open issues and PRs involving your GitHub account (yhinai). The connected Android phone supplies GPS and Health Connect readings directly over authorized ADB, using a private snapshot refreshed every five seconds. Each Health reading retains its own measurement timestamp. Missing readings remain unavailable. The device list shows the Mac LAN IP and phone Wi-Fi IP; the Mac’s Tailscale IP is available in its tooltip. GPS matches use recorded fixes at or before the selected speech time; older speech may have no matching fix. Audio processing uses Deepgram and automatic task suggestions use finalized transcript text sent to Gemini.

App-only logs: `logs/inloop-app.log`. Saved sessions, tasks and GPS fixes are stored in the private `logs/inloop-app.sqlite3` database. Nothing is deployed to or written to alhinai.dev. On desktop the dashboard fits the viewport; long lists and the transcript scroll independently.

The phone update preserves the existing website and direct-Mac uploads. Its additive source patch and rebuild notes are in `scripts/inloop-phone-snapshot.patch` and `scripts/inloop-phone-snapshot.md`. APKs, signing keys, snapshots, and readings stay private under ignored logs. No motion recognizer was changed.

## Google Maps

Location uses Google satellite imagery with the selected phone GPS fix. Google 3D Maps is enabled when `GOOGLE_MAPS_BROWSER_KEY` is set in the local `.env` to a **browser Maps key authorized for `http://127.0.0.1:8790/*`** with the required Maps JavaScript/3D access. This is a browser-visible key; never use the Gemini/server API key here. Refresh inLoop after configuring it. The existing website key rejects localhost, so the app keeps a working Google satellite map when no local 3D key is configured. No website key restrictions are changed.

The interface follows the personal website palette and uses headings above the cards. Live drafts and finalized captions appear newest first at the top. Scrolling into older speech preserves the visible passage as new entries arrive; “New speech ↑” returns to the latest speech.
