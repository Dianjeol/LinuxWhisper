# LinuxWhisper — complete text at your cursor, as fast as possible

**Performance is this app's primary goal:** after releasing the recording key, the complete text should appear at the cursor with as little waiting as possible. Truncating text is not an optimization.

- **Hold right Alt/AltGr, speak, release:** dictate directly.
- **Select text, hold F4, speak an instruction, release:** the agent's answer replaces the selection in the text field and is available in the clipboard and Omarchy's existing clipboard history.

Both paths use Deepgram Flux Multilingual, with German as the intentional default speech language, at the EU endpoint. F4 additionally uses [DeepSeek V4.1 Flash via OpenRouter](https://openrouter.ai/deepseek/deepseek-v4.1-flash), exactly `deepseek/deepseek-v4.1-flash`. Despite the app's name, it does not use a local Whisper model.

## Performance first

- The microphone and Deepgram WebSocket are open before **READY**. Audio streams while the key is held, not only afterward.
- `CloseStream` processes the remaining audio and the final word. No `ForceEndTurn`, artificial response limit, or insertion of unfinished partial results.
- F4 reads the selection and establishes DNS/TCP/TLS to OpenRouter during recording. Exactly one model request follows the complete transcript; no warm-up HTTP request.
- [Reasoning is disabled](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens); [provider routing prioritizes latency](https://openrouter.ai/docs/guides/routing/provider-selection#provider-sorting), not the lowest price. Long answers still take their full generation time.
- AltGr makes no OpenRouter request and reads no text selection. The agent path remains separate.
- Exactly one paste, no sleeps, no character-by-character typing, no focus changes. Clipboard preparation and window classification still run concurrently; no log writes before paste acknowledgment.
- The optional recording overlay runs in separate observer/render processes, prepared before **READY**. It reads key edges independently: no audio processing, polling timer, live waveform, or per-frame messages from the dictation process. There is no overlay hook between key release and paste acknowledgment.
- An overlay still consumes memory and compositor resources. Process isolation is not a promise of literally zero overhead or measured freedom from latency regressions.

## Setup

Requirements: Omarchy with Hyprland/Wayland, Python ≥ 3.11, a microphone, Omarchy's clipboard capture running, and read access to keyboard devices under `/dev/input/event*`. The recording indicator uses Quickshell, already included in Omarchy. These permissions allow keyboard input to be read; do not run the app with `sudo`.

In the project directory:

```bash
sudo pacman -S --needed python python-pip base-devel linux-api-headers portaudio wl-clipboard quickshell
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

New accounts receive free initial API credit when [signing up for Deepgram](https://console.deepgram.com/signup). After that, [usage pricing](https://deepgram.com/pricing) applies. Create an API key there and set it in Bash for the current session without saving it in shell history:

```bash
read -rsp 'Deepgram API key: ' DEEPGRAM_API_KEY; echo
export DEEPGRAM_API_KEY
./run
```

`./run` uses `DEEPGRAM_API_KEY` and, for F4, also `OPENROUTER_API_KEY`. If either value is missing from the environment, the launcher loads an interactive Bash with `~/.bashrc`. Export the keys there. No `.env` file is loaded. AltGr still works without an OpenRouter key; F4 reports the missing key. Never commit API keys.

Create an OpenRouter key: [OpenRouter Keys](https://openrouter.ai/settings/keys). For the current Bash session:

```bash
read -rsp 'OpenRouter API key: ' OPENROUTER_API_KEY; echo
export OPENROUTER_API_KEY
./run
```

## Usage

Wait for **READY**, focus a text field, and dictate. The microphone and connection are then prepared. **Ctrl+C** exits; run only one instance at a time. The app itself does not configure bindings, autostarts, or services.

- AltGr and F4 remain visible to other apps; existing app shortcuts may react. AltGr key combinations also start recording. Left Alt does not. During a recording, only releasing its own key ends it.
- Text is pasted once: `Ctrl+V` in apps, `Shift+Insert` in windows with Omarchy's `terminal` tag. No additional Enter, no focus changes.
- Stay in the intended text field while processing finishes. Locked surfaces and alternative paste shortcuts are not universally supported; terminals handle newlines according to their configuration.
- Open clipboard history: **Super+Ctrl+V**. The app uses the existing Omarchy watcher, not its own history.

```bash
./run --once                 # One AltGr or F4 recording, then exit
./run --no-overlay           # Dictation without the visual indicator
./run --help                 # All options, including language and log path
.venv/bin/python -m sounddevice  # List audio devices
```

### Recording indicator

A small charcoal capsule appears at the bottom center of Quickshell's default display while AltGr or F4 is held: a static ivory sound mark, warm recording dot, and a keycap. **Listening / Release to paste** identifies dictation; **Voice edit / Release to apply** identifies F4. It disappears on the matching key release, not after the network response.

The surface is click-through, never accepts keyboard focus, and reserves no desktop space. No transcript, microphone level, elapsed-time display, continuous animation, or additional microphone access. Both visual processes start before **READY**, receive neither API key, and exit with the app. The main process only arms the indicator before each **READY**; it never waits for the renderer during recording or finalization. Additional presses while a take is being finalized are ignored by the indicator until the app is ready again.

Use `--no-overlay` to disable it. If Quickshell cannot initialize, the app prints a startup warning and dictation remains available. The indicator is feedback, not confirmation that a target application accepted text.


### F4: edit selected text by voice

1. **Make a fresh selection** of the desired text in the target window.
2. **Hold F4** and say, for example, “Schreibe diesen Text bitte freundlicher” (“Please make this text friendlier”).
3. **Release F4**; leave the window, cursor, and selection unchanged until the answer arrives.

The spoken instruction and the selection read at the start of recording are sent together to OpenRouter. Only the complete result is inserted, without an additional agent introduction. Each recording is independent; there is no chat history.

The selection is read through Wayland's **PRIMARY** (`wl-paste --primary`), without a copy shortcut or changes to the regular clipboard. The application must provide this text selection; a native Chromium text field was among the cases checked. PRIMARY is system-wide: it cannot identify a stale selection from another window. Always make a fresh selection in the target window; apps without PRIMARY support are unsuitable for this F4 path.

An empty/unreadable selection, silence, API errors, or an incomplete model answer result in no paste. No model request is made without a spoken instruction. TLS preparation may already have taken place. If a change in the focused window is detected, the completed answer remains only in the clipboard. Cursor/selection changes within the same window are not detected; the focus check is not an atomic lock against later focus changes.

In a terminal, the answer is inserted at the input cursor; it does not rewrite selected terminal output. Newlines can execute commands there — do not generate executable content without reviewing it.

### Optional autostart

For a checkout at `~/Work/LinuxWhisper`, add this to `~/.config/hypr/autostart.lua`:

```lua
o.launch_on_start(os.getenv("HOME") .. "/Work/LinuxWhisper/run")
```

Adjust the project path if needed. API keys must remain available in the environment or through `~/.bashrc`. The app starts in the background at the next Hyprland session start, not on a configuration reload.

## Data and latency

The microphone remains open; audio outside the held-key interval is discarded locally. While AltGr or F4 is held, audio is transmitted to Deepgram, but the app does not save it to a file. **F4 additionally sends the text selection and the complete instruction transcript to OpenRouter and its model provider.** Deepgram's EU endpoint does not guarantee EU processing at OpenRouter. Do not select confidential text that must not be sent to these providers.

The inserted text replaces the clipboard and remains in the local Omarchy clipboard history. The app writes no history of its own and saves no transcripts, selections, or answers to files. The prompt is not a guarantee of protection against manipulative content in the selection.

### Remote privacy policy

- **Deepgram: EU-only and zero content retention.** Every Flux WebSocket uses `api.eu.deepgram.com` with `mip_opt_out=true`. There is no US/global endpoint option or automatic geographic fallback. According to [Deepgram's data policy](https://developers.deepgram.com/trust-security/your-data), this combination keeps processing in the EU, excludes model improvement, and retains audio/transcripts only for the duration needed to process the request. Request metadata and usage logs remain; this is not zero retained records.
- **OpenRouter: ZDR-only, no provider data collection; global routing.** Every F4 request sets `provider.zdr=true`, `provider.data_collection="deny"`, and `provider.require_parameters=true`, while retaining latency-first routing and disabled reasoning. Failover can only select endpoints eligible under those privacy constraints. A rejected request is not retried with weaker settings or a different model. The existing DeepSeek model remains unchanged. **EU residency is not enforced for OpenRouter**, as explicitly selected for this setup.
- [OpenRouter ZDR](https://openrouter.ai/docs/guides/features/zdr) permits implicit in-memory prompt caching. There is no documented DeepSeek request parameter to disable that cache; do not interpret ZDR as “no temporary processing or memory.”
- Request parameters do not override account/workspace [input/output logging](https://openrouter.ai/docs/guides/features/input-output-logging) or [Broadcast destinations](https://openrouter.ai/docs/guides/features/broadcast). **Keep prompt/completion logging and data-sharing opt-ins disabled, and remove Broadcast/observability destinations** in your OpenRouter account/workspace for maximum privacy. This repository does not change account settings and cannot certify them. OpenRouter's own ZDR policy excludes prompts only when you have not opted into logging; operational/billing metadata is separate.
- The local clipboard history intentionally retains pasted text. Remote content-retention controls do not disable that existing desktop feature.

References: [Deepgram MIP opt-out](https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program), [OpenRouter provider controls](https://openrouter.ai/docs/guides/routing/provider-selection), and [OpenRouter regional routing boundaries](https://openrouter.ai/docs/guides/features/in-region-routing).


For each successful, nonempty **AltGr dictation**, one number in milliseconds is written to:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/sound/latency.log
```

The measurement is **Alt released → paste command acknowledged by Hyprland**: it includes the remaining audio, complete decoder finalization with `CloseStream`, and clipboard handoff. It confirms neither processing nor visible rendering by the target application; subsequent history storage is also outside the measurement.

Log writes and terminal output occur only afterward. The log contains no audio, transcripts, or API keys. Silence and failed handoffs produce no successful value; a later log error can occur even after text has been pasted. Development rules: [AGENTS.md](AGENTS.md).

F4 values are not mixed into this AltGr log. The agent's additional model generation is part of the actual wait for complete insertion; it is not hidden by moving the measurement boundary earlier.

## Verification status

### Recording overlay and privacy update

- Started the updated `./run` with the real microphone, actual keyboard device, Quickshell, and real EU Deepgram WebSocket through **READY**. The default speech language remains German. `./run --help` and `bash -n run` passed.
- Visually checked the actual AltGr and F4 layer-shell surfaces on Hyprland. Injected binary key events through temporary FIFO devices exercised the production observer: unrelated-key releases, matching releases, cross-keyboard release, finalization lockout, and F4 mode. Focus stayed unchanged when the overlay appeared. Checked renderer termination and child cleanup. Physical key presses, multi-monitor placement, and physical pointer click-through were not automated.
- Pasted `Grüße, Jörg — 完全な文。` into a native Chromium text field at its existing cursor, preserving surrounding text. Read the exact UTF-8 bytes in a real Foot terminal using its Omarchy `terminal` tag and `Shift+Insert`. Confirmed the synthetic text in the existing Omarchy clipboard history by reading it, not writing it.
- A real OpenRouter call with the new ZDR/no-data-collection controls returned the exact requested Unicode text; it replaced a fresh native PRIMARY selection without changing the prefix or suffix. No EU residency is claimed for OpenRouter. Account logging/Broadcast settings were not changed or verified.
- Ran the main AltGr loop against real EU Deepgram with `mip_opt_out=true`, synthetic silence, and `--no-overlay`: no paste, no successful latency value, unchanged clipboard. A real failing clipboard subprocess likewise produced no paste or successful latency value. The silence fixture injected audio/key events; it did not record the microphone.
- `.venv/bin/python -m unittest -v test_flow`: six passing regression tests covering sample boundaries, Unicode/completeness, provider errors inside HTTP 200, and suppression of private Deepgram/OpenRouter error bodies.

Five real-time replays per group used the same public English speech sample, 80 ms packets, real EU Deepgram with MIP opt-out, full `CloseStream` finalization, and Hyprland paste acknowledgment. The updated group kept the overlay visible:

| Alt released → paste acknowledged | Before overlay | Overlay visible |
| --- | ---: | ---: |
| Median | 175.8 ms | 177.9 ms |
| p95 (nearest rank, n=5) | 288.8 ms | 200.4 ms |

These are synthetic key/audio replays, not physical dictations. Desktop activity and network variability were not controlled; five samples do not establish either a speedup or freedom from regressions. A controlled microphone before/after comparison remains outstanding. No claim of literally zero overhead.

### Earlier F4 checks


- Started through `./run --once` with a real microphone and real Deepgram WebSocket through **READY**; checked `./run --help` and `bash -n run`.
- Streamed a German test speech recording in real time to the actual Deepgram EU endpoint, followed by a real request to the OpenRouter model named above. The recording contained “Schreibe diesen Text bitte freundlicher.”
- Visibly replaced a real keyboard selection in a native Chromium text field, including “Grüße, Jörg”, unchanged text before/after the selection, and a complete sentence ending. Also executed the main loop's F4 branch with injected key/audio events; its AltGr latency log remained empty. The GUI fixture focused the test window; production code does not change focus.
- Read the actual model answer into a Foot terminal classified with Omarchy's `terminal` tag using `Shift+Insert` and compared it exactly. Confirmed capture in the existing Omarchy history through read-only inspection.
- Checked silence and missing PRIMARY selection with real Deepgram: no model request, no paste, clipboard unchanged. A real OpenRouter HTTP 401 was cleanly rejected. A detected window change prevented pasting; the answer remained in the clipboard.
- Ran three Deepgram speech replays before and three after the change, each with the complete final word; executed AltGr finalization and paste acknowledgment. These are not physical dictations or reliable evidence of a speedup or freedom from regressions. A controlled before/after microphone comparison with median/p95 is still missing.
- `.venv/bin/python -m unittest -v test_flow`: four passing regression tests covering sample-accurate AltGr/F4 boundaries despite releasing the other key, Unicode/formatting, interrupted/empty answers, and confidential error responses.

Physical AltGr/F4 key presses and a fresh session start were not checked automatically. In the existing environment, `pip check` reports an unrelated missing `systemd-python` dependency for `proton-vpn-daemon`; the app introduces no new dependency.

Previously documented: autostart launch path through `uwsm-app` through **READY**, including without an inherited API key; `hyprctl reload` and `hyprctl configerrors` without errors. No Hyprland bindings, autostarts, or services were configured, and no configuration files were changed for F4.

## License

[MIT](LICENSE).
