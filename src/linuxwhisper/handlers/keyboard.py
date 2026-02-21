"""
Global keyboard listener with data-driven key mappings.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any, Dict, List, Optional

from pynput import keyboard

from linuxwhisper.config import CFG
from linuxwhisper.handlers.mode import ModeHandler
from linuxwhisper.managers.chat import ChatManager
from linuxwhisper.managers.overlay import OverlayManager
from linuxwhisper.services.audio import AudioService
from linuxwhisper.services.tts import TTSService
from linuxwhisper.state import STATE


class KeyboardHandler:
    """Global keyboard listener with data-driven key mappings."""

    # Generate mappings dynamically from CFG.HOTKEY_DEFS
    # Format: mode_id -> list of all valid keys (primary + extras)
    KEY_MAPPINGS: Dict[str, List[Any]] = {
        mode_id: [data[1]] + data[2]
        for mode_id, data in CFG.HOTKEY_DEFS.items()
    }

    # Track currently pressed keys for modifier detection
    current_keys: set = set()

    @classmethod
    def check_key(cls, key, target_mode: str) -> bool:
        """Check if pressed key matches target mode AND required modifiers."""
        # 1. Check Primary Key
        valid_keys = cls.KEY_MAPPINGS.get(target_mode, [])
        is_key_match = False
        
        if key in valid_keys:
            is_key_match = True
        elif hasattr(key, 'vk') and key.vk in valid_keys:
            is_key_match = True
            
        if not is_key_match:
            return False

        # 2. Check Modifiers (if defined)
        required_modifiers = CFG.HOTKEY_MODIFIERS.get(target_mode, [])
        if not required_modifiers:
            return True

        # Check if ANY of the required modifiers are currently pressed
        match = any(mod in cls.current_keys for mod in required_modifiers)
        
        return match

    @classmethod
    def get_mode_for_key(cls, key) -> Optional[str]:
        """Get mode name for a pressed key, if any."""
        for mode in CFG.MODES:
            if cls.check_key(key, mode):
                return mode
        return None

    @classmethod
    def on_press(cls, key) -> None:
        """Handle key press events."""
        cls.current_keys.add(key)

        if STATE.recording:
            return

        # Pin toggle (non-recording action)
        if cls.check_key(key, "pin"):
            ChatManager.toggle_pin()
            return

        # TTS toggle (non-recording action)
        if cls.check_key(key, "tts"):
            TTSService.toggle()
            return

        # Check for recording mode keys
        mode = cls.get_mode_for_key(key)
        if mode:
            STATE.current_mode = mode

            # For Aria mode, copy selected text first (Context Awareness)
            if mode == "aria":
                subprocess.run(["xdotool", "key", "ctrl+c"])
                time.sleep(0.1)

            OverlayManager.show(mode)
            AudioService.start_recording()

    @classmethod
    def on_release(cls, key) -> None:
        """Handle key release events."""
        if key in cls.current_keys:
            cls.current_keys.remove(key)

        if not STATE.recording:
            return

        # Check if released key matches current mode (either the main key OR the modifier)
        # If user releases Super OR Space, we stop.
        
        # We stop if the main trigger key is released OR if the functionality implies a hold.
        # For Super+Space as a *toggle* or *hold*? 
        # Dictation usually implies holding the key.
        # If we want "Hold Super+Space to talk", we stop when Space is released.
        
        should_stop = False
        
        # Did we release the primary Trigger Key?
        valid_keys = cls.KEY_MAPPINGS.get(STATE.current_mode, [])
        if key in valid_keys:
             should_stop = True
        elif hasattr(key, 'vk') and key.vk in valid_keys:
             should_stop = True

        if should_stop:
            OverlayManager.hide()
            audio_data = AudioService.stop_recording()

            if audio_data is not None:
                transcribed = AudioService.transcribe(audio_data)
                if transcribed:
                    ModeHandler.process(STATE.current_mode, transcribed)

    @classmethod
    def run(cls) -> None:
        """Start keyboard listener in current thread."""
        with keyboard.Listener(on_press=cls.on_press, on_release=cls.on_release) as listener:
            listener.join()
