LinuxWhisper
============

Voice-to-text and AI assistant for Linux desktops.
Integrates Groq APIs for transcription, chat, rewriting, and vision.

Features
--------

- **Wake Word**: Say "Hey Luna" to trigger AI Chat hands-free.
- **Dictation (F3)**: Speech-to-text using Whisper V3.
- **AI Chat (F4)**: Context-aware Q&A using Moonshot Kimi.
- **Smart Rewrite (F7)**: Highlight text, speak to rewrite.
- **Vision (F8)**: Screenshot analysis using Llama 4.
- **Pin Chat (F9)**: Toggle chat overlay pin mode.
- **TTS (F10)**: Toggle text-to-speech for AI responses.

Prerequisites
-------------

Debian/Ubuntu-based Linux system.

Installation
------------

1. Clone:

       git clone https://github.com/Dianjeol/LinuxWhisper.git
       cd LinuxWhisper

2. Run setup:

       ./setup.sh

Configuration
-------------

    export GROQ_API_KEY="your_key"

Get free key: https://console.groq.com

Usage
-----

    ./venv/bin/python linuxwhisper.py


**Wake Word:**
Simply say **"Hey Luna"** to start the AI Chat. The recording will stop automatically after 1.5s of silence.
*(Model (~5MB) is downloaded automatically on first run)*

Hotkeys:

| Key | Action |
|-----|--------|
| F3 | Dictation (text at cursor) |
| F4 | AI Chat (response at cursor) |
| F7 | Rewrite (select → hold → speak → release) |
| F8 | Vision (screenshot + AI) |
| F9 | Pin/Unpin chat overlay |
| F10 | Toggle TTS / Mute |

**Settings:**
Click the ⚙️ icon in the chat or use "Settings" in the System Tray to change:
- TTS Voice (Diana, Hannah, etc.)
- View Hotkeys

System tray icon for history and settings.
