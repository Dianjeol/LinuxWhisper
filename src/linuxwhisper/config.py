"""
Immutable application configuration.

All constants are centralized here for easy modification.
To change a setting, edit the default value below.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from evdev import ecodes


@dataclass(frozen=True)
class Config:
    """
    Immutable application configuration.

    All constants are centralized here for easy modification.
    To change a setting, edit the default value below.
    """
    # --- Global Design System (Curated Color Schemes) ---
    COLOR_SCHEMES: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "Arctic Twilight": {
            "bg":        "#003049",
            "surface":   "#335c67",
            "accent":    "#669bbc",
            "text":      "#f1faee",
            "desc":      "Infinite polar blues echoing the cosmos and the soft light of evening snow."
        },
        "Volcanic Dawn": {
            "bg":        "#003049",
            "surface":   "#669bbc",
            "accent":    "#780000",
            "text":      "#fdf0d5",
            "desc":      "Intense, blazing crimson radiates energy; a bold and dramatic command of attention."
        },
        "Spring Blossom": {
            "bg":        "#a2d2ff",
            "surface":   "#cdb4db",
            "accent":    "#ffafcc",
            "text":      "#322659",
            "desc":      "Delicate pastel petals and whimsical sky blues, bringing a soft, elegant charm."
        },
        "Deep Sea Myth": {
            "bg":        "#0B0C10",
            "surface":   "#1F2833",
            "accent":    "#66FCF1",
            "text":      "#C5C6C7",
            "desc":      "Mysterious abyssal depths where cyan phosphorescence meets resilient silent strength."
        },
        "Boreal Silence": {
            "bg":        "#041C06",
            "surface":   "#064E3B",
            "accent":    "#10B981",
            "text":      "#ECFDF5",
            "desc":      "Lush, dark greens of ancient forests whispering beneath the mint-bright aurora."
        },
        "Oceanic Zen": {
            "bg":        "#002b36",
            "surface":   "#073642",
            "accent":    "#2aa198",
            "text":      "#eee8d5",
            "desc":      "Mathematically balanced depths of solarized teal, a classic of modern interface harmony."
        },
        "Amber Harvest": {
            "bg":        "#282828",
            "surface":   "#3c3836",
            "accent":    "#d65d0e",
            "text":      "#fbf1c7",
            "desc":      "Warm engineered earth tones of copper and cream, evoking a retro-industrial rustic elegance."
        },
        "Neon Nightshade": {
            "bg":        "#282a36",
            "surface":   "#44475a",
            "accent":    "#bd93f9",
            "text":      "#f8f8f2",
            "desc":      "Vibrant high-contrast purple and deep ink-blue, capturing the electric glow of a bioluminescent forest."
        },
        "Mediterranean Shore": {
            "bg":        "#264653",
            "surface":   "#2a9d8f",
            "accent":    "#f4a261",
            "text":      "#fdf1d3",
            "desc":      "Sun-drenched golden sands meet the smoky blue of midnight tides and crystalline waters."
        },
    })
    DEFAULT_SCHEME: str = "Oceanic Zen"
    SETTINGS_FILE: Path = Path.home() / ".config" / "linuxwhisper" / "settings.json"

    # --- Audio Settings ---
    SAMPLE_RATE: int = 44100

    # --- History Limits ---
    MAX_TOKENS: int = 32000
    ANSWER_HISTORY_LIMIT: int = 15
    CHAT_MESSAGE_LIMIT: int = 20
    CHAT_AUTO_HIDE_SEC: int = 3

    # --- AI Models ---
    MODEL_CHAT: str = "openai/gpt-oss-120b"
    MODEL_VISION: str = "qwen/qwen3.6-27b"
    MODEL_WHISPER: str = "whisper-large-v3"
    MODEL_TTS: str = "canopylabs/orpheus-v1-english"

    # --- TTS Voices ---
    TTS_VOICES: Tuple[str, ...] = ("diana", "hannah", "autumn", "austin", "daniel", "troy")
    TTS_DEFAULT_VOICE: str = "diana"
    TTS_MAX_CHARS: int = 4000

    # --- Temp File Paths ---
    TEMP_SCREEN_PATH: str = f"/tmp/temp_screen_{os.getuid()}.png"
    TEMP_TTS_PATH: str = f"/tmp/linuxwhisper_tts_{os.getuid()}.wav"

    # --- System Prompt ---
    SYSTEM_PROMPT: str = (
        "Act as a compassionate assistant. Base your reasoning on the principles of "
        "Nonviolent Communication and A Course in Miracles. Apply these frameworks as "
        "your underlying logic without explicitly naming them or forcing them. Let your "
        "output be grounded, clear, and highly concise. Return ONLY the direct response."
    )

    # --- Mode Definitions (icon, overlay text, colors) ---
    MODES: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "dictation":  {"icon": "🎙️", "text": "Listening...",    "bg": "bg", "fg": "accent"},
        "ai":         {"icon": "🤖", "text": "AI Listening...", "bg": "bg", "fg": "accent"},
        "ai_rewrite": {"icon": "✍️", "text": "Rewrite Mode...", "bg": "bg", "fg": "accent"},
        "vision":     {"icon": "📸", "text": "Vision Mode...",  "bg": "bg", "fg": "accent"},
    })

    # --- Hotkey Definitions ---
    # format: "id": (Label, PrimaryKeycode, [ExtraKeycodes])
    # Uses evdev ecodes — works on both X11 and Wayland.
    HOTKEY_DEFS: Dict[str, Tuple[str, int, List[int]]] = field(default_factory=lambda: {
        "dictation":  ("R-Alt / F3",  ecodes.KEY_RIGHTALT,  [ecodes.KEY_F3, ecodes.KEY_F13]),
        "ai":         ("F4",  ecodes.KEY_F4,  [ecodes.KEY_F14]),
        "ai_rewrite": ("F7",  ecodes.KEY_F7,  [ecodes.KEY_PREVIOUSSONG]),
        "vision":     ("F8",  ecodes.KEY_F8,  [ecodes.KEY_PLAYPAUSE]),
        "pin":        ("F9",  ecodes.KEY_F9,  [ecodes.KEY_NEXTSONG]),
        "tts":        ("F10", ecodes.KEY_F10, [ecodes.KEY_MUTE]),
    })


# Global config instance
CFG = Config()
