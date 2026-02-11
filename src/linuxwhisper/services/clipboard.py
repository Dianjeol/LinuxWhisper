"""
Clipboard operations for typing and pasting text.
"""
from __future__ import annotations

import subprocess
import time

import pyperclip


class ClipboardService:
    """Clipboard operations for typing and pasting text."""

    @staticmethod
    def type_text(text: str) -> None:
        """Paste text at cursor via clipboard (fast)."""
        if not text:
            return

        # Save original clipboard
        try:
            original = pyperclip.paste()
        except Exception:
            original = None

        # Add leading space to prevent word merging
        clean_text = f" {text.strip()}" if not text.startswith(" ") else text

        # Paste via clipboard
        pyperclip.copy(clean_text)
        subprocess.run(["xdotool", "key", "ctrl+v"])

        # Restore original clipboard after short delay
        time.sleep(0.1)
        if original is not None:
            try:
                pyperclip.copy(original)
            except Exception:
                pass

    @staticmethod
    def copy_selected() -> str:
        """Copy currently selected text and return it."""
        subprocess.run(["xdotool", "key", "ctrl+c"])
        time.sleep(0.1)
        return pyperclip.paste().strip()

    @staticmethod
    def paste_text(text: str) -> None:
        """Paste text directly via clipboard."""
        pyperclip.copy(text)
        subprocess.run(["xdotool", "key", "ctrl+v"])
