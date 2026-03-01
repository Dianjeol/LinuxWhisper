"""
Clipboard operations for typing and pasting text.

Detects terminal emulators and uses the correct keyboard shortcuts
(Ctrl+Shift+V/C instead of Ctrl+V/C).
"""
from __future__ import annotations

import subprocess
import time

import pyperclip

# Substrings to match against WM_CLASS (lowercase).
# Covers namespaced names like "com.mitchellh.ghostty".
_TERMINAL_KEYWORDS = (
    "terminal", "terminator", "tilix", "alacritty", "kitty",
    "konsole", "xterm", "urxvt", "sakura", "terminology",
    "guake", "tilda", "yakuake", "wezterm", "foot",
    "cool-retro-term", "hyper", "tabby", "rio", "ghostty",
)


def _is_terminal_focused() -> bool:
    """Check if the currently focused window is a terminal emulator."""
    try:
        # Get active window ID
        win_id = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1,
        ).stdout.strip()
        if not win_id:
            return False

        # Get WM_CLASS via xprop (works on all X11 systems)
        result = subprocess.run(
            ["xprop", "-id", win_id, "WM_CLASS"],
            capture_output=True, text=True, timeout=1,
        )
        wm_class = result.stdout.strip().lower()
        return any(kw in wm_class for kw in _TERMINAL_KEYWORDS)
    except Exception:
        return False


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

        # Paste via clipboard – use correct shortcut for terminals
        pyperclip.copy(clean_text)
        paste_key = "ctrl+shift+v" if _is_terminal_focused() else "ctrl+v"
        subprocess.run(["xdotool", "key", paste_key])

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
        copy_key = "ctrl+shift+c" if _is_terminal_focused() else "ctrl+c"
        subprocess.run(["xdotool", "key", copy_key])
        time.sleep(0.1)
        return pyperclip.paste().strip()

    @staticmethod
    def paste_text(text: str) -> None:
        """Paste text directly via clipboard."""
        pyperclip.copy(text)
        paste_key = "ctrl+shift+v" if _is_terminal_focused() else "ctrl+v"
        subprocess.run(["xdotool", "key", paste_key])
