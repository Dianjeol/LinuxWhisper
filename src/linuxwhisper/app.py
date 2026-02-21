"""
LinuxWhisper — Application entry point.
"""
from __future__ import annotations

import os
import threading
import warnings

# Suppress libEGL warnings by forcing software rendering for GTK/WebKit
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
os.environ["WEBKIT_DISABLE_COMPOSITING_MODE"] = "1"

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*Specified provider 'CUDAExecutionProvider'.*")

from linuxwhisper.config import CFG
from linuxwhisper.handlers.keyboard import KeyboardHandler
from linuxwhisper.ui.tray import TrayManager


def main() -> None:
    """Application entry point."""
    print("🚀 LinuxWhisper is running.")

    descriptions = {
        "dictation": "Live dictation at cursor position (Whisper V3)",
        "ai": "Empathic AI question (Groq Moonshot)",
        "ai_rewrite": "Smart Rewrite - Highlight text & speak to edit",
        "vision": "Empathic Vision / Screenshot (Groq Llama 4)",
        "pin": "Toggle Chat Overlay Pin Mode",
        "tts": "Toggle TTS (Read AI responses aloud)"
    }

    i = 1
    for mode_id, (label, _, _) in CFG.HOTKEY_DEFS.items():
        desc = descriptions.get(mode_id, "Unknown Mode")
        print(f" {i}. {label:<13}: {desc}")
        i += 1
    print("\n📌 System tray icon active")

    # Start keyboard listener in background thread
    keyboard_thread = threading.Thread(target=KeyboardHandler.run, daemon=True)
    keyboard_thread.start()

    # Run GTK main loop (blocks)
    TrayManager.start()


if __name__ == "__main__":
    main()
