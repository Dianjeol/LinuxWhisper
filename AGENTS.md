# Project: low-latency dictation app for Omarchy

## Primary goal

After releasing right Alt/AltGr, insert the complete text at the cursor in the focused application as quickly as possible and make it available in the existing Omarchy clipboard history. Correct, complete transcription remains a prerequisite; truncating text is not an optimization.

The only persistently logged metric is **Alt released → paste command acknowledged by Hyprland**, in milliseconds, one value per successful dictation. It includes decoder finalization, clipboard handoff, and the paste command. Hyprland does not confirm text processing or visible rendering by an arbitrary target application. Never present this proxy as a measured on-screen rendering time or move the measurement boundary earlier to produce better numbers.

## Mandatory performance rules

- No change may intentionally worsen this latency. New features belong outside the critical path. If a trade-off is unavoidable, let the user decide first.
- Critical path: final audio frames → complete decoder finalization → clipboard ready → paste acknowledged. Before that, no log/history file writes, terminal output, notifications, text post-processing services, or additional network requests.
- No blanket sleeps, artificial keyboard delays, character-by-character input, focus changes, or application launches for pasting. Wait for actual protocol responses, not estimated readiness times.
- Prepare the microphone and WebSocket before `READY`. Stream while Alt is held; do not wait until release to upload. Discard audio outside the held-key interval locally.
- `CloseStream` processes the remaining audio. Do not replace it with `ForceEndTurn`: a quick acknowledgment of the last interim result is not a complete transcript.
- Only one paste operation per dictation. Let the existing Omarchy watcher capture clipboard history; no separate history database and no competing writes to Omarchy's history file.
- No VAD, word-timestamp, or secondary-metric processing in the audio/streaming path without a concrete, user-approved need. No new libraries or services without demonstrable benefit to the goal.
- Write the measurement only after paste acknowledgment. No audio frames, API keys, or transcripts in the performance log. Silence and failed handoffs do not produce a successful measurement.

## Workflow and evidence

- Reuse existing patterns in `bench.py` and `desktop.py`; prefer small, direct implementations over additional frameworks.
- Check critical-path changes before and after under comparable conditions with several real dictations. Compare the median and p95 of the single metric; do not present network variability as an improvement. Without a comparison, do not claim a speedup or freedom from regressions.
- Practically verify actual insertion into a GUI text field and a terminal, as well as capture in the existing clipboard history. Cover Unicode, cursor position, silence, and errors. No tests that only confirm source text or internal wiring.
- Preserve the complete final word and sample-accurate Alt boundaries. Audio loss invalidates the run.
- No persistent Hyprland bindings, autostarts, services, or desktop configuration changes unless requested. Only read installed Omarchy files under `/usr/share/omarchy`.
- Document behavior changes and checks actually performed in `README.md`. State limitations openly: not every application supports the same paste shortcuts; a non-editable or locked surface is not an input field.
