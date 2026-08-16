"""
Wayland platform backends.

Uses: wtype, wl-copy, wl-paste, grim
Compositor-specific: niri msg (optional, for terminal detection)
"""
from __future__ import annotations

import json
import subprocess
from typing import Tuple

from linuxwhisper.platform.base import ClipboardBackend, InputBackend, ScreenshotBackend

# Terminal app-ids matched against focused window info (lowercase).
_TERMINAL_KEYWORDS: Tuple[str, ...] = (
    "terminal", "terminator", "tilix", "alacritty", "kitty",
    "konsole", "xterm", "urxvt", "sakura", "terminology",
    "guake", "tilda", "yakuake", "wezterm", "foot",
    "cool-retro-term", "hyper", "tabby", "rio", "ghostty",
)


class WaylandClipboard(ClipboardBackend):
    """Clipboard via wl-copy / wl-paste (Wayland)."""

    def copy(self, text: str) -> None:
        try:
            proc = subprocess.Popen(
                ["wl-copy"],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=text.encode("utf-8"))
        except Exception as e:
            print(f"⚠️ Wayland clipboard copy error: {e}")

    def paste(self) -> str:
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout
        except Exception:
            return ""


class WaylandInput(InputBackend):
    """Input simulation via wtype (Wayland)."""

    def simulate_paste(self, is_terminal: bool = False) -> None:
        if is_terminal:
            # Ctrl+Shift+V: wtype needs modifiers spelled out
            subprocess.run(
                ["wtype", "-M", "ctrl", "-M", "shift", "-P", "v", "-p", "v", "-m", "shift", "-m", "ctrl"],
                timeout=2,
            )
        else:
            subprocess.run(
                ["wtype", "-M", "ctrl", "-P", "v", "-p", "v", "-m", "ctrl"],
                timeout=2,
            )

    def simulate_copy(self, is_terminal: bool = False) -> None:
        if is_terminal:
            subprocess.run(
                ["wtype", "-M", "ctrl", "-M", "shift", "-P", "c", "-p", "c", "-m", "shift", "-m", "ctrl"],
                timeout=2,
            )
        else:
            subprocess.run(
                ["wtype", "-M", "ctrl", "-P", "c", "-p", "c", "-m", "ctrl"],
                timeout=2,
            )

    def is_terminal_focused(self) -> bool:
        """
        Detect focused terminal via compositor IPC.

        Currently supports niri (via `niri msg focused-window`).
        Returns False for unsupported compositors (safe default → Ctrl+V).
        """
        # Try niri IPC
        try:
            result = subprocess.run(
                ["niri", "msg", "-j", "focused-window"],
                capture_output=True, text=True, timeout=1,
            )
            if result.returncode == 0 and result.stdout.strip():
                info = json.loads(result.stdout)
                app_id = (info.get("app_id") or "").lower()
                title = (info.get("title") or "").lower()
                combined = f"{app_id} {title}"
                return any(kw in combined for kw in _TERMINAL_KEYWORDS)
        except Exception:
            pass

        # Fallback: cannot detect → safe default (Ctrl+V)
        return False


class WaylandScreenshot(ScreenshotBackend):
    """Screenshot via grim (Wayland)."""

    def take_screenshot(self, output_path: str) -> bool:
        try:
            result = subprocess.run(
                ["grim", output_path],
                capture_output=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False
