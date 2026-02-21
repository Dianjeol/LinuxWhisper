"""
Mutable application state and settings persistence.
"""
from __future__ import annotations

import json
import queue
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import sounddevice as sd

from linuxwhisper.config import CFG

import gi
gi.require_version('AyatanaAppIndicator3', '0.1')
gi.require_version('Gtk', '3.0')
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import Gtk


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------
class SettingsManager:
    """Handles persistence of user settings."""

    @staticmethod
    def load() -> Dict[str, Any]:
        """Load settings from JSON file."""
        if not CFG.SETTINGS_FILE.exists():
            return {}
        try:
            with open(CFG.SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load settings: {e}")
            return {}

    @staticmethod
    def save(state: "AppState") -> None:
        """Save current relevant state to JSON file."""
        try:
            CFG.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "color_scheme": state.color_scheme,
                "tts_voice": state.tts_voice,
                "tts_enabled": state.tts_enabled,
                "chat_pinned": state.chat_pinned,
                "chat_enabled": state.chat_enabled,
            }
            with open(CFG.SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"⚠️ Failed to save settings: {e}")


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------
@dataclass
class AppState:
    """
    Mutable application state.

    All runtime state is centralized here for clarity and debugging.
    Reset by creating a new instance: STATE = AppState()
    """
    # --- Recording State ---
    recording: bool = False
    current_mode: Optional[str] = None
    audio_buffer: List[np.ndarray] = field(default_factory=list)
    stream: Optional[sd.InputStream] = None
    viz_queue: queue.Queue = field(default_factory=queue.Queue)

    # --- UI Windows ---
    overlay_window: Optional[Any] = None   # GtkOverlay instance
    chat_overlay_window: Optional[Any] = None  # ChatOverlay instance

    # --- Chat State ---
    chat_messages: List[Dict[str, str]] = field(default_factory=list)
    chat_pinned: bool = False
    chat_enabled: bool = True
    chat_hide_timer: Optional[int] = None

    # --- History ---
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    answer_history: List[Dict[str, str]] = field(default_factory=list)

    # --- TTS ---
    tts_enabled: bool = False  # Disabled by default
    tts_voice: str = CFG.TTS_DEFAULT_VOICE

    # --- UI Theme ---
    color_scheme: str = CFG.DEFAULT_SCHEME

    # --- System Tray ---
    indicator: Optional[AppIndicator.Indicator] = None
    gtk_menu: Optional[Gtk.Menu] = None

    # --- UI Persistence ---
    last_chat_position: Optional[Tuple[int, int]] = None

    def __post_init__(self):
        """Load persistent settings after initialization."""
        saved = SettingsManager.load()
        if "color_scheme" in saved:
            self.color_scheme = saved["color_scheme"]
        if "tts_voice" in saved:
            self.tts_voice = saved["tts_voice"]
        if "tts_enabled" in saved:
            self.tts_enabled = saved["tts_enabled"]
        if "chat_pinned" in saved:
            self.chat_pinned = saved["chat_pinned"]
        if "chat_enabled" in saved:
            self.chat_enabled = saved["chat_enabled"]


# Global state instance
STATE = AppState()
