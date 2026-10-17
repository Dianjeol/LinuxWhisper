# LinuxWhisper

Speak instead of typing, or ask for a small change to text you've already written. LinuxWhisper is a lightweight dictation app for **Omarchy with Hyprland/Wayland**. It pastes the result into the text field you have focused, so you can stay in the application you're using.

There are two ways to use it:

- **Dictate:** hold right Alt/AltGr, speak, then release. Your words are transcribed and pasted at the cursor.
- **Edit by voice:** select some text, hold F4, and say what you'd like to change. The completed answer replaces your selection. This optional feature needs an OpenRouter API key.

**Performance comes first:** the goal is to keep the pause between releasing the key and receiving the complete text as short as possible. That means preparing ahead and streaming while you speak—not cutting off the last word or pasting an unfinished result.

A small recording indicator shows when you're holding a recording key. The inserted text is also available in Omarchy's existing clipboard history.

## Before you begin

You'll need:

- **Omarchy with Hyprland/Wayland**, a microphone, and an internet connection. This is not a general-purpose app for every Linux desktop.
- A **Deepgram account and API key** for speech recognition. An API key is the secret credential that lets the app use your account. New accounts receive initial API credit when [signing up](https://console.deepgram.com/signup); after that, [usage pricing](https://deepgram.com/pricing) applies.
- Optionally, an **[OpenRouter API key](https://openrouter.ai/settings/keys)** if you'd like to edit selected text with F4. Dictation works without it.
- Read access to keyboard devices under `/dev/input/event*`, and Omarchy's clipboard capture running. Keyboard-reading permissions are sensitive: they allow keyboard input to be read. Please don't run the app with `sudo` to work around a permission error. The installation commands below do not grant those permissions.

**This is a cloud-based app, not a local Whisper model.** Recorded speech goes to Deepgram. F4 also sends your selected text and spoken instruction to OpenRouter and its model provider. Deepgram is configured for EU-only processing; OpenRouter is not restricted to the EU. The [privacy section](#privacy-and-your-data) explains retention controls and their limits.

German is the default speech language. You can choose another language with `--language`, as shown [below](#useful-options).

## Get started

### 1. Install the app's dependencies

Open a terminal in this project folder and run:

```bash
sudo pacman -S --needed python python-pip base-devel linux-api-headers portaudio wl-clipboard quickshell
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The first command installs system packages; it may ask for your password. The next two create a separate Python environment for this project and install its Python packages. Python 3.11 or newer is required. You don't need to activate the environment manually: the `run` launcher uses it for you.

`requirements.txt` contains the three direct Python dependencies: `evdev` for keyboard events, `sounddevice` for microphone capture, and `websockets` for the Deepgram connection. Their own Python dependencies are installed automatically. PortAudio, `wl-clipboard`, and Quickshell are system packages, not pip packages. Quickshell provides the recording indicator and is already included in Omarchy. The OpenRouter client uses Python's standard library; no separate model SDK is needed.

### 2. Add your Deepgram key and start

In the same Bash terminal, run:

```bash
read -rsp 'Deepgram API key: ' DEEPGRAM_API_KEY; echo
export DEEPGRAM_API_KEY
./run
```

Paste your key at the prompt and press Enter. It won't be displayed or saved in your shell history. Keep the key private; don't commit it to GitHub.

Wait until the terminal shows **READY**. The microphone and speech-recognition connection are prepared at that point. Keep the app running in this terminal; **Ctrl+C** stops it. Please run only one instance at a time.

### 3. Try your first dictation

1. Click into an editable text field in the application you want to use.
2. Hold **right Alt/AltGr** and say a short sentence.
3. Release the key, keeping the intended text field focused while the app finishes.

The complete transcription is pasted at your current cursor position. To find it again in Omarchy's clipboard history, press **Super+Ctrl+V**.

### Optional: enable voice editing

If you'd like to use F4, stop the app with **Ctrl+C**, then add your OpenRouter key in the same terminal and start again:

```bash
read -rsp 'OpenRouter API key: ' OPENROUTER_API_KEY; echo
export OPENROUTER_API_KEY
./run
```

Your Deepgram key must still be available in that terminal. For maximum privacy, also check the OpenRouter account settings described [below](#openrouter-account-settings).

<details>
<summary>Using API keys in later sessions</summary>

The commands above set keys for the current terminal session. For later sessions or autostart, export `DEEPGRAM_API_KEY` and, if needed, `OPENROUTER_API_KEY` from your Bash configuration (`~/.bashrc`) or make them available in the environment.

If either key is missing from the environment, `./run` loads an interactive Bash with `~/.bashrc` before starting the app. A missing OpenRouter key disables F4, not AltGr dictation. A `.env` file is not loaded.

</details>

## Editing selected text with F4

1. **Make a fresh selection** in the text field you want to edit.
2. **Hold F4** and speak an instruction—for example, “Schreibe diesen Text bitte freundlicher” (“Please make this text friendlier”).
3. **Release F4** and leave the window, cursor, and selection unchanged until the answer arrives.

The app sends the selected text and your spoken instruction together, then inserts only the complete result, without an extra introduction. Each request is independent; there is no chat history. F4 uses [DeepSeek V4.1 Flash through OpenRouter](https://openrouter.ai/deepseek/deepseek-v4.1-flash), exactly `deepseek/deepseek-v4.1-flash`. Both recording modes use Deepgram Flux Multilingual for speech recognition.

A few limits are worth knowing:

- The target application needs to share its text selection through Wayland's **PRIMARY** selection (`wl-paste --primary`). A native Chromium text field has been checked. This reads the selection without a copy shortcut or changes to the regular clipboard. PRIMARY is shared across the desktop and can contain an old selection from another window, so making a fresh selection in the intended field matters. Apps without PRIMARY support aren't suitable for this F4 workflow.
- An empty or unreadable selection, silence, an API error, or an incomplete model answer results in no paste. No model request is made without a spoken instruction, although connection preparation may already have taken place.
- If the app detects that you've switched windows, it leaves the completed answer in the clipboard instead of pasting it. Moving the cursor or changing the selection within the same window is not detected. The focus check also cannot prevent a later focus change between checking and pasting.
- In a terminal, an answer is pasted at the input cursor; it does not rewrite selected terminal output. Newlines can execute commands there, depending on the terminal's configuration. Please don't generate executable content without reviewing it.

## The recording indicator

While a recording key is held, a small charcoal capsule appears at the bottom center of Quickshell's default display. Its five ivory bars respond smoothly to microphone volume, alongside a warm recording dot and a keycap:

- **Listening / Release to paste** for AltGr dictation.
- **Voice edit / Release to apply** for F4 editing.

It disappears when you release the matching key, not when the network response arrives. It is visual feedback, not confirmation that the target application accepted the text. The surface is click-through, does not accept keyboard focus, and reserves no desktop space.

Quiet input leaves the bars at rest; louder input makes them taller. This is a sampled volume indicator, not speech detection: typing, music, and other sufficiently loud sounds can move it too. A fixed -42 dBFS noise floor suppresses quiet background input. The display settles back to rest when samples stop arriving, and has no continuously looping animation.

If you'd rather keep the screen clear, start with `./run --no-overlay`. If Quickshell cannot initialize, the app prints a startup warning and dictation remains available.

## Useful options

```bash
./run --language en             # English speech hints instead of the default German
./run --once                    # One AltGr or F4 recording, then exit
./run --no-overlay              # Run without the recording indicator
./run --help                    # All options, including language and log path
.venv/bin/python -m sounddevice  # List available audio devices
```

### Working with other applications

The app pastes once using `Ctrl+V`, or `Shift+Insert` in windows with Omarchy's `terminal` tag. It doesn't press Enter or switch focus. Applications with different paste shortcuts, locked surfaces, and non-editable areas aren't universally supported; a surface that cannot accept text isn't an input field.

AltGr and F4 are still visible to other applications, so existing shortcuts may react. AltGr key combinations also start recording; left Alt does not. During a recording, only releasing its own recording key ends it. The app itself does not set up keyboard bindings, autostarts, or services.

## Privacy and your data

The microphone stays open while the app runs, but audio outside a held recording key is discarded locally. Audio recorded while AltGr or F4 is held is sent to Deepgram; the app does not save it as an audio file. F4 additionally sends the text selection and the complete instruction transcript to OpenRouter and its model provider. Please don't select confidential text that must not go to those services.

A successful paste replaces the clipboard, and the text remains in the existing local Omarchy clipboard history. The app does not create its own history or save transcripts, selections, or answers to files. Remote retention settings do not disable your desktop's clipboard history. The model prompt is not a guarantee of protection against manipulative content in a selection.

### Service-side retention controls

- **Deepgram: EU-only processing and zero content retention.** Every Flux WebSocket uses `api.eu.deepgram.com` with `mip_opt_out=true`. There is no US/global endpoint option or automatic geographic fallback. According to [Deepgram's data policy](https://developers.deepgram.com/trust-security/your-data), this combination keeps processing in the EU, excludes model improvement, and retains audio/transcripts only for the duration needed to process the request. Request metadata and usage logs still remain; this does not mean zero retained records.
- **OpenRouter: Zero Data Retention (ZDR) and no provider data collection, with global routing.** Every F4 request sets `provider.zdr=true`, `provider.data_collection="deny"`, and `provider.require_parameters=true`. Latency-first routing and disabled reasoning are retained. Failover can only choose endpoints eligible under those privacy constraints; a rejected request is not retried with weaker settings or a different model. **EU residency is not enforced for OpenRouter.**
- [OpenRouter's ZDR policy](https://openrouter.ai/docs/guides/features/zdr) allows implicit in-memory prompt caching. There is no documented DeepSeek request parameter to disable that cache. ZDR does not mean that temporary processing or memory use is avoided.

### OpenRouter account settings

For the strongest privacy available with this setup, keep prompt/completion logging and data-sharing opt-ins disabled in your OpenRouter account or workspace, and remove Broadcast/observability destinations.

Request parameters do not override [input/output logging](https://openrouter.ai/docs/guides/features/input-output-logging) or [Broadcast destinations](https://openrouter.ai/docs/guides/features/broadcast). This app does not change or verify those account settings. OpenRouter's own ZDR policy excludes prompts only when you have not opted into logging; operational and billing metadata are separate.

Further references: [Deepgram MIP opt-out](https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program), [OpenRouter provider controls](https://openrouter.ai/docs/guides/routing/provider-selection), and [OpenRouter regional routing boundaries](https://openrouter.ai/docs/guides/features/in-region-routing).

## How the app keeps the wait short

The main idea is to do useful work before you release the key: prepare the microphone and connection, send audio while you're speaking, then finish decoding and paste the complete text once.

<details>
<summary>Technical performance details</summary>

- The microphone and Deepgram WebSocket are open before **READY**. Audio streams while the recording key is held, not only afterward.
- `CloseStream` processes the remaining audio and the final word. There is no `ForceEndTurn`, artificial response limit, or insertion of unfinished partial results.
- During F4 recording, the app reads the selection and establishes DNS/TCP/TLS to OpenRouter. Exactly one model request follows the complete transcript; there is no warm-up HTTP request.
- [Reasoning is disabled](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens), and [provider routing prioritizes latency](https://openrouter.ai/docs/guides/routing/provider-selection#provider-sorting), not the lowest price. Long answers still need their full generation time.
- AltGr makes no OpenRouter request and reads no text selection. The two paths remain separate.
- There is exactly one paste: no artificial sleeps, character-by-character typing, or focus changes. Clipboard preparation and window classification run concurrently. Log writes and terminal output happen only after paste acknowledgment.
- The optional overlay runs in separate observer/render processes, prepared before **READY**, and reads key edges independently. While recording, the main process makes at most 20 nonblocking sends per second of short PCM snapshots from the existing microphone stream. A bounded private local datagram socket drops visual updates if its observer is stalled; transcription audio is unchanged. Only the observer computes volume, and only scalar levels reach QML. No VAD, second microphone stream, new dependency, additional network request, or audio file is involved. Neither visual process receives API keys, and both exit with the app.
- The main process arms the overlay before each **READY** and never waits for the renderer during recording or finalization. It stops offering snapshots once it processes the matching release. The observer hides the surface independently on key-up; decoder finalization and paste never wait for a visual acknowledgment or animation. Additional key presses during finalization are ignored by the indicator until the app is ready again.
- An overlay still uses memory and compositor resources. Process isolation does not prove literally zero overhead or freedom from latency regressions.

</details>

### What the latency log measures

For each successful, nonempty **AltGr dictation**, one value in milliseconds is written to:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/sound/latency.log
```

The measurement is **Alt released → paste command acknowledged by Hyprland**. It includes the remaining audio, complete decoder finalization with `CloseStream`, and clipboard handoff. It does not confirm when the target application processes or visibly renders the text; later clipboard-history storage is also outside the measurement.

The log contains no audio, transcripts, or API keys. Silence and failed handoffs produce no successful value. A log error can still occur after text has already been pasted. F4 values are not mixed into this AltGr log: generating the complete model answer is part of F4's actual waiting time and is not hidden by moving the measurement boundary.

## Optional autostart

If you'd like the app to start when you sign in, and your checkout is at `~/Work/LinuxWhisper`, add this to `~/.config/hypr/autostart.lua`:

```lua
o.launch_on_start(os.getenv("HOME") .. "/Work/LinuxWhisper/run")
```

Adjust the path if your project is elsewhere. The API keys need to be available in the environment or through `~/.bashrc`. The app starts in the background at the next Hyprland session start, not when the configuration is reloaded. This is optional; the app does not make the change for you.

## Verification status

<details>
<summary>Installation checks, desktop checks, and latency measurements</summary>

These notes distinguish what has been checked from what still needs a real-world comparison. Development rules are in [AGENTS.md](AGENTS.md).

### Setup and dependency check

The documented Python installation was checked in a fresh, isolated virtual environment on Python 3.14.7. Installing only `requirements.txt` brought in all three direct dependencies, plus the automatically resolved `cffi` and `pycparser` dependencies. `pip check` reported no broken requirements.

All application modules imported successfully in that environment. The CLI help, the documented audio-device listing, and `bash -n run` also passed. The required system packages and desktop commands were confirmed present; the `pacman` installation was not rerun. This documentation-only update did not change the app's behavior or repeat the dictation/latency checks below.


### Volume-reactive recording indicator

- Visually checked the actual Hyprland/Quickshell AltGr and F4 surfaces with quiet, soft, and loud PCM snapshots through the production observer. Bar height followed volume and returned to rest after updates stopped. Synthetic FIFO key events checked unrelated-key release, matching release, finalization lockout, and unchanged focus.
- Stopped the real observer and filled its datagram channel. The recording path still delivered the exact sample-clipped PCM, including both fractional key boundaries, and completed `CloseStream`; the visual queue did not block or truncate the recording.
- Confirmed complete transcriptions in a native Chromium text field through the production paste path. Existing text was preserved and every inserted text ended with the final spoken words. With the caret placed between a prefix and a suffix, one replay inserted the transcription at exactly that caret (`PREFIX ` + text + ` SUFFIX`).
- Restarted the real `./run` instance afterwards with the real microphone and a real EU Deepgram WebSocket. It reached **READY** with the volume-reactive observer and its renderer running.
- `.venv/bin/python -m unittest -v test_flow`: eight passing regression tests, including silence/background-noise suppression, increasing volume, and both signed PCM extremes. `./run --help` and `bash -n run` passed.

Five real-time replays per group used the same public English speech sample, 80 ms packets, real EU Deepgram with MIP opt-out, full `CloseStream` finalization, Hyprland paste acknowledgment, and the same replay harness in both groups:

| Alt released → paste acknowledged | Static bars | Volume-reactive bars |
| --- | ---: | ---: |
| Median | 193.9 ms | 221.9 ms |
| p95 (nearest rank, n=5) | 904.2 ms | 647.1 ms |

The groups differ in both directions and overlap heavily; the spread reflects network and desktop variability, not the indicator. Five samples establish neither a speedup nor freedom from regressions. The added work during a recording is at most 20 nonblocking datagram sends per second on a local socket, and none after the matching release.

- These desktop checks used injected PCM/key events, not physical speech or physical AltGr/F4 presses. A controlled real-microphone before/after comparison remains outstanding; process isolation and bounded visual updates are not proof of zero latency overhead.

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

<details>
<summary>Earlier F4 checks</summary>

- Started through `./run --once` with a real microphone and real Deepgram WebSocket through **READY**; checked `./run --help` and `bash -n run`.
- Streamed a German test speech recording in real time to the actual Deepgram EU endpoint, followed by a real request to the OpenRouter model named above. The recording contained “Schreibe diesen Text bitte freundlicher.”
- Visibly replaced a real keyboard selection in a native Chromium text field, including “Grüße, Jörg”, unchanged text before/after the selection, and a complete sentence ending. Also executed the main loop's F4 branch with injected key/audio events; its AltGr latency log remained empty. The GUI fixture focused the test window; production code does not change focus.
- Read the actual model answer into a Foot terminal classified with Omarchy's `terminal` tag using `Shift+Insert` and compared it exactly. Confirmed capture in the existing Omarchy history through read-only inspection.
- Checked silence and missing PRIMARY selection with real Deepgram: no model request, no paste, clipboard unchanged. A real OpenRouter HTTP 401 was cleanly rejected. A detected window change prevented pasting; the answer remained in the clipboard.
- Ran three Deepgram speech replays before and three after the change, each with the complete final word; executed AltGr finalization and paste acknowledgment. These are not physical dictations or reliable evidence of a speedup or freedom from regressions. A controlled before/after microphone comparison with median/p95 is still missing.
- `.venv/bin/python -m unittest -v test_flow`: four passing regression tests covering sample-accurate AltGr/F4 boundaries despite releasing the other key, Unicode/formatting, interrupted/empty answers, and confidential error responses.

Physical AltGr/F4 key presses and a fresh session start were not checked automatically. In the existing environment, `pip check` reported an unrelated missing `systemd-python` dependency for `proton-vpn-daemon`; the F4 update introduced no new dependency.

Previously documented: the autostart launch path through `uwsm-app` through **READY**, including without an inherited API key; `hyprctl reload` and `hyprctl configerrors` without errors. No Hyprland bindings, autostarts, or services were configured, and no configuration files were changed for F4.

</details>

</details>

## License

[MIT](LICENSE).
