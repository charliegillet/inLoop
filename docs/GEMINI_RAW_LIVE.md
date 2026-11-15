# Raw Vexo motion → Gemini Decision live preview

This is the current live experiment. It does **not** use the earlier calibration as a reference. That recorded reference remains on disk for historical comparisons, but the live preview never reads it.

Run the launcher prepared on this Mac:

```sh
/Users/alhinai/vexo-captions/logs/Gemini-Live-Motion.command
```

The earlier `logs/Gemini-Motion-Test.command` launcher now opens this same raw live preview. Reproducing the historical reference benchmark requires explicitly running its separate benchmark script.

Or run the script directly with your existing credential file:

```sh
.venv/bin/python scripts/live_gemini_motion.py --env-file /absolute/path/to/private.env
```

The launcher starts a short screen-direction check, or restores that check's checkpoint if it is less than 24 hours old. **C** starts a new check. For each of left/right/up/down, return to centre, press **Space**, make one stroke toward that screen edge, then hold. Each capture lasts about 2.2 seconds and includes a short pre-roll. Stationary or interrupted captures are rejected for repetition. Completed strokes survive brief source reconnects; an interrupted trial is repeated. Changing the fit or wearing orientation needs a new C check.

After four strokes, **A** toggles automatic recognition; **Space** classifies manually. Automatic recognition waits for about 0.8 seconds of new observations and overlaps windows by 0.2 seconds instead of leaving a gap between two-second polls. A single API request can be in flight while the next observations accumulate. Each target window includes every received sample; bounded backlog and telemetry discontinuities still limit coverage. **Escape pauses**, **Q quits**, and arrow escape sequences are ignored. The launcher allows five minutes and at most 24 requests. Completed check examples are checkpointed privately in `logs/gemini-screen-check-current.json`, mode 0600, and accepted for 24 hours. This is the recent four-stroke check, never the earlier 17-trial calibration.

For an incorrect screen label, press **L/R/U/D** within eight seconds of the displayed prediction to label that exact observation as left/right/up/down. The latest classified raw window, not a later wrist position, replaces that direction's fresh example. The next request uses the correction; any in-flight decision from before the correction is discarded. This is explicit feedback in the request context, not model-weight training or automatic learning from the model's own guesses.

Try holding still, tilting slowly, turning, moving back and forth, then a gentle shake. Do each movement for 2–3 seconds. A held pose with no continuing movement can correctly be classified as still; this experiment identifies physical motion, not an intended screen command.

The target input contains every received sample in its window, with no resampling or numeric rounding: the band's millisecond timestamp and accelerometer X/Y/Z in g plus gyroscope X/Y/Z in degrees/second. These are the SDK's decoded sensor readings in physical units, not electrical sensor-register values. Units and column names accompany them. Acceleration includes gravity. No calculated roll/pitch, motion summaries, microphone audio, screenshots or old calibration are included. When four fresh screen examples are available, a compact 12-point representation of each new stroke accompanies the full target window. The model separately scores movement type and screen direction; it is not trained or fine-tuned by these examples.

Movement choices are `swipe`, `circle`, `still`, `tilting`, `rotating`, `back_and_forth`, `shaking`, `impact`, and `unknown`. The additional screen-direction decision chooses left/right/up/down/unknown using the fresh check. Both scores are shown independently. These are hypotheses to validate on real movements; an impact is not proof of a deliberate band tap. Confidence is the model's score, not an established accuracy for this person.

The existing Bluetooth owner publishes motion; this viewer opens no second band connection. It uses the same single-viewer lock as the motion/control tools, so close another motion viewer first while leaving captions open. The lease enables 25 Hz motion and faster local snapshot publication. One cloud request can be in flight at a time; no unbounded queue is created. Responses from an old source generation, a paused request epoch, stale data, or a request window older than two seconds are rejected. Detected telemetry holes are not compressed into a contiguous gesture.

There is **no Mac input path** in this preview. Classification labels do not click, scroll or move the pointer. Command intent remains a separate future integration; the fresh direction check is not proof of accurate pointing in all postures.

Private status is `logs/gemini-live-status.json`. Small per-run JSON reports contain labels, scores, token counts, request latency, sample count and window duration; they do not retain raw target windows or credentials. The separate recent-check checkpoint retains its four labeled strokes so closing the viewer does not lose them. Its 24-hour limit governs reuse, not a guarantee of immediate file deletion. API failures pause/end the experiment without printing provider bodies or automatically retrying. A request already sent may finish after quitting, but its result cannot perform an action.

A live, reference-free smoke request returned `still` at about 83% confidence with a 532 ms API round trip. This establishes delivery and parsing only, not correctness across movements. The offline tests cover fresh-window construction, duplicate/invalid sample handling, discontinuities, wrong-band/stale/disconnected input, source-generation changes, raw sample preservation, and rejection of stale responses.
