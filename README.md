LinuxWhisper
============

A lightweight, compassionate AI assistant for Linux desktops.
Integrates Groq (Whisper/Llama/Moonshot) for instant voice interaction,
rewriting, and vision capabilities.

Features
--------

- **Dictation (F3)**: Real-time speech-to-text using Groq Whisper V3.
- **AI Assistant (F4)**: Context-aware Q&A using Groq (Moonshot Kimi).
- **Smart Rewrite (F7)**: Highlight text and speak to rewrite it in-place.
- **Vision (F8)**: Screenshot analysis and Q&A using Llama 4 Vision.

Prerequisites
-------------

Requires a Debian/Ubuntu-based Linux system.

Installation
------------

1.  Clone the repository:
    
        git clone https://github.com/Dianjeol/LinuxWhisper.git
        cd LinuxWhisper

2.  Run the setup script:

        ./setup.sh

    This will install system dependencies (requires sudo), create a virtual environment,
    and install Python libraries.

Configuration
-------------

Export your API key as environment variable:

    export GROQ_API_KEY="your_groq_key"

Get free key here:
- **Groq**: https://console.groq.com

Usage
-----

Run the script:

    python3 linuxwhisper.py

Hotkeys:
- **F3**: Start/Stop Dictation (Text typed at cursor).
- **F4**: Start/Stop AI Query (Response typed at cursor).
- **F7**: Smart Rewrite (Highlight text -> Hold F7 -> Speak -> Release).
- **F8**: Vision Mode (Screenshot -> AI Analysis).

Note: The application runs in the background. Use the System Tray icon to view history or quit.
