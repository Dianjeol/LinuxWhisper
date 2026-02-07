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
*   **Linux** (Ubuntu/Debian recommended)
*   **Groq API Key**: [Get your free key here](https://console.groq.com)

### 2. Installation
```bash
git clone https://github.com/Dianjeol/LinuxWhisper.git && cd LinuxWhisper
./setup.sh
```

### 3. Launch
```bash
# Set your API Key once
export GROQ_API_KEY="your_key"

# Start the whisperer
./venv/bin/python linuxwhisper.py
```

> [!TIP]
> Use the **System Tray** icon or the ⚙️ icon in the chat overlay to adjust TTS voices and preferences.

---


