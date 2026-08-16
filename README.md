<div align="center">

<img src="assets/logo.png" alt="LinuxWhisper Logo" width="180" height="auto" />

# LinuxWhisper

**A Voice-Assistant & AI Companion for Linux**

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-emerald?style=for-the-badge)](LICENSE)
[![Groq Powered](https://img.shields.io/badge/AI-Groq%20Cloud-orange?style=for-the-badge)](https://groq.com)

---

**LinuxWhisper** is a simple voice assistant designed to help you with daily tasks. It uses global hotkeys to provide AI-powered tools without switching windows.

<br />

![LinuxWhisper Demo](assets/demo.gif)

</div>

## Features

- 🎙️ **Dictation**: Voice-to-text at your cursor using **Whisper-v3**.
- 💬 **AI Chat**: Helpful Q&A and conversation.
- ✍️ **Smart Rewrite**: Modify selected text using your voice.
- 👁️ **Vision**: Understand screenshots using **Llama 4**.
- 🔊 **Voice Feedback**: Optional text-to-speech for AI responses.

---

## 🖥️ Supported Platforms

| Distribution | Display Server | Status |
|:---|:---|:---|
| **Debian / Ubuntu** | X11 | ✅ Fully supported |
| **Debian / Ubuntu** | Wayland | ✅ Supported |
| **Fedora / RHEL** | X11 | ✅ Supported |
| **Fedora / RHEL** | Wayland | ✅ Supported |
| **Arch Linux** | X11 | ✅ Supported |
| **Arch Linux** | Wayland / **Niri** | ✅ Fully supported |

The app auto-detects your session type (X11 or Wayland) and uses the appropriate backends:

| Feature | X11 | Wayland |
|:---|:---|:---|
| Clipboard | `xclip` | `wl-clipboard` |
| Key Simulation | `xdotool` | `wtype` |
| Screenshots | `gnome-screenshot` | `grim` |
| Overlays | GTK Window Hints | `gtk-layer-shell` |
| Global Hotkeys | `evdev` | `evdev` |

---

## ⌨️ Command Center

| Key | Action | Purpose |
|:---:|:---|:---|
| `F3` | **Dictate** | Transcribe voice to text at cursor |
| `F4` | **Chat** | Open/Focus AI conversation |
| `F7` | **Rewrite** | Highlight text → Speak to modify |
| `F8` | **Vision** | Screenshot + Intelligent Analysis |
| `F9` | **Pin** | Toggle "Always on Top" for chat |
| `F10` | **TTS** | Toggle AI voice feedback |

---

## 🛠️ Quick Start

### 1. Requirements
*   **Linux** (Debian/Ubuntu, Fedora/RHEL or Arch Linux)
*   **Groq API Key**: [Get your free key here](https://console.groq.com)
*   **User in `input` group** (for global hotkeys):
    ```bash
    sudo usermod -aG input $USER
    # Log out and back in after this
    ```

### 2. Installation
```bash
git clone https://github.com/Dianjeol/LinuxWhisper.git && cd LinuxWhisper
./setup.sh
```

The setup script automatically detects your distribution and session type, then installs the correct packages.

### 3. Launch
```bash
# Set your API Key once
export GROQ_API_KEY="your_key"

# Start the whisperer
linuxwhisper

# Or alternatively:
python -m linuxwhisper
```

> [!TIP]
> Use the **System Tray** icon or the ⚙️ icon in the chat overlay to adjust TTS voices and preferences.

---

### Niri Users

For best overlay behaviour, add these rules to `~/.config/niri/config.kdl`:

```kdl
layer-rule {
    match namespace="linuxwhisper-recording"
    shadow { on false }
}

layer-rule {
    match namespace="linuxwhisper-chat"
    shadow { on false }
}
```

---

## 📂 Project Structure

```
src/linuxwhisper/
├── __init__.py          # Package version
├── __main__.py          # python -m linuxwhisper
├── app.py               # main() entry point
├── config.py            # Config dataclass + CFG singleton
├── state.py             # AppState + SettingsManager + STATE
├── api.py               # Groq client initialization
├── decorators.py        # safe_execute, run_on_main_thread
├── platform/
│   ├── __init__.py      # Session detection + backend factory
│   ├── base.py          # Abstract base classes (ABCs)
│   ├── x11.py           # X11 backends (xdotool, xclip, gnome-screenshot)
│   └── wayland.py       # Wayland backends (wtype, wl-clipboard, grim)
├── services/
│   ├── audio.py         # AudioService (recording + transcription)
│   ├── ai.py            # AIService (chat + vision)
│   ├── tts.py           # TTSService (Orpheus voice)
│   ├── clipboard.py     # ClipboardService (uses platform backends)
│   └── image.py         # ImageService (uses platform backends)
├── managers/
│   ├── history.py       # HistoryManager (conversation + tray history)
│   ├── chat.py          # ChatManager (overlay state + auto-hide)
│   └── overlay.py       # OverlayManager (recording indicator)
├── ui/
│   ├── recording_overlay.py  # GtkOverlay (waveform + gtk-layer-shell)
│   ├── chat_overlay.py       # ChatOverlay (WebKit2 + gtk-layer-shell)
│   ├── settings_dialog.py    # SettingsDialog (voice, schemes, hotkeys)
│   └── tray.py               # TrayManager (AppIndicator)
└── handlers/
    ├── mode.py           # ModeHandler (dictation/AI/rewrite/vision)
    └── keyboard.py       # KeyboardHandler (evdev listener)
```
