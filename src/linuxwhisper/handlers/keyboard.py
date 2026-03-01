"""
Global keyboard listener with data-driven key mappings.
"""
from __future__ import annotations


from typing import Any, Dict, List, Optional

from pynput import keyboard

from linuxwhisper.config import CFG
from linuxwhisper.handlers.mode import ModeHandler
from linuxwhisper.managers.chat import ChatManager
from linuxwhisper.managers.overlay import OverlayManager
from linuxwhisper.services.audio import AudioService
from linuxwhisper.services.clipboard import ClipboardService
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

    @classmethod
    def check_key(cls, key, target_mode: str) -> bool:
        """Check if pressed key matches target mode."""
        valid_keys = cls.KEY_MAPPINGS.get(target_mode, [])
        if key in valid_keys:
            return True
        if hasattr(key, 'vk') and key.vk in valid_keys:
            return True
        return False

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
        # Pin toggle (non-recording action)
        if cls.check_key(key, "pin"):
            if not STATE.recording:
                ChatManager.toggle_pin()
            return

        # TTS toggle (non-recording action)
        if cls.check_key(key, "tts"):
            if not STATE.recording:
                TTSService.toggle()
            return

        # Toggle mode: pressing same key again stops recording
        if STATE.recording and STATE.toggle_mode:
            if cls.check_key(key, STATE.current_mode):
                cls._stop_and_process()
            return

        if STATE.recording:
            return

        # Check for recording mode keys
        mode = cls.get_mode_for_key(key)
        if mode:
            STATE.current_mode = mode

            # For rewrite mode, copy selected text first
            if mode == "ai_rewrite":
                ClipboardService.copy_selected()

            OverlayManager.show(mode)
            AudioService.start_recording()

    @classmethod
    def on_release(cls, key) -> None:
        """Handle key release events."""
        if not STATE.recording:
            return

        # In toggle mode, release does nothing (stop is handled in on_press)
        if STATE.toggle_mode:
            return

        # Hold mode: release key stops recording
        if cls.check_key(key, STATE.current_mode):
            cls._stop_and_process()

    @classmethod
    def _stop_and_process(cls) -> None:
        """Stop recording, transcribe, and process result."""
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
