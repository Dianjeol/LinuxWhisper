"""
Platform abstraction layer.

Detects the display session type (X11 or Wayland) at import time
and provides factory functions for platform-specific backends.

Usage:
    from linuxwhisper.platform import get_clipboard, get_input, get_screenshot
    clipboard = get_clipboard()
    clipboard.copy("Hello")
"""
from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from linuxwhisper.platform.base import ClipboardBackend, InputBackend, ScreenshotBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session detection
# ---------------------------------------------------------------------------

def detect_session_type() -> str:
    """
    Detect the display session type from the environment.

    Returns:
        'wayland' or 'x11'
    """
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland":
        return "wayland"
    if session == "x11":
        return "x11"
    # Fallback heuristics
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    # Conservative default
    return "x11"


SESSION_TYPE: str = detect_session_type()

logger.info("Detected session type: %s", SESSION_TYPE)


# ---------------------------------------------------------------------------
# Wayland layer-shell support
# ---------------------------------------------------------------------------

def layer_shell_supported() -> bool:
    """
    Check whether the running compositor actually supports the
    wlr-layer-shell protocol (i.e. not GNOME/Mutter on Wayland).

    Must only return True when both the library is importable and the
    compositor exposes zwlr_layer_shell_v1. Falls back to XDG shell
    otherwise to avoid aborting in gtk-layer-shell.
    """
    if SESSION_TYPE != "wayland":
        return False
    try:
        import gi
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
        return bool(GtkLayerShell.is_supported())
    except (ValueError, ImportError):
        return False


# ---------------------------------------------------------------------------
# Singleton backend instances (lazy-initialized)
# ---------------------------------------------------------------------------

_clipboard: Optional["ClipboardBackend"] = None
_input: Optional["InputBackend"] = None
_screenshot: Optional["ScreenshotBackend"] = None


def get_clipboard() -> "ClipboardBackend":
    """Get the platform-specific clipboard backend (singleton)."""
    global _clipboard
    if _clipboard is None:
        if SESSION_TYPE == "wayland":
            from linuxwhisper.platform.wayland import WaylandClipboard
            _clipboard = WaylandClipboard()
        else:
            from linuxwhisper.platform.x11 import X11Clipboard
            _clipboard = X11Clipboard()
    return _clipboard


def get_input() -> "InputBackend":
    """Get the platform-specific input simulation backend (singleton)."""
    global _input
    if _input is None:
        if SESSION_TYPE == "wayland":
            from linuxwhisper.platform.wayland import WaylandInput
            _input = WaylandInput()
        else:
            from linuxwhisper.platform.x11 import X11Input
            _input = X11Input()
    return _input


def get_screenshot() -> "ScreenshotBackend":
    """Get the platform-specific screenshot backend (singleton)."""
    global _screenshot
    if _screenshot is None:
        if SESSION_TYPE == "wayland":
            from linuxwhisper.platform.wayland import WaylandScreenshot
            _screenshot = WaylandScreenshot()
        else:
            from linuxwhisper.platform.x11 import X11Screenshot
            _screenshot = X11Screenshot()
    return _screenshot
