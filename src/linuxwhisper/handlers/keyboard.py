"""
Global keyboard listener using evdev.

Reads key events directly from /dev/input/ devices, which works on both
X11 and Wayland without any display server integration. Requires the
user to be in the 'input' group.
"""
from __future__ import annotations

import logging
import selectors
from typing import Dict, List, Optional

import evdev
from evdev import InputDevice, categorize, ecodes

from linuxwhisper.config import CFG
from linuxwhisper.handlers.mode import ModeHandler
from linuxwhisper.managers.chat import ChatManager
from linuxwhisper.managers.overlay import OverlayManager
from linuxwhisper.services.audio import AudioService
from linuxwhisper.services.clipboard import ClipboardService
from linuxwhisper.services.tts import TTSService
from linuxwhisper.state import STATE

logger = logging.getLogger(__name__)


class KeyboardHandler:
    """Global keyboard listener using evdev (works on X11 + Wayland)."""

    # Build a flat lookup: keycode -> mode_id
    # for all recording modes + toggle actions
    _KEY_TO_MODE: Dict[int, str] = {}
    for mode_id, (_, primary, extras) in CFG.HOTKEY_DEFS.items():
        _KEY_TO_MODE[primary] = mode_id
        for extra in extras:
            _KEY_TO_MODE[extra] = mode_id

    @classmethod
    def _find_keyboards(cls) -> List[InputDevice]:
        """Discover all keyboard input devices."""
        keyboards = []
        for path in evdev.list_devices():
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                # A device with EV_KEY that has typical keyboard keys
                if ecodes.EV_KEY in caps:
                    key_caps = caps[ecodes.EV_KEY]
                    # Check for at least some function keys to filter out mice etc.
                    if ecodes.KEY_F1 in key_caps or ecodes.KEY_A in key_caps:
                        keyboards.append(dev)
                        logger.debug("Found keyboard: %s (%s)", dev.name, dev.path)
            except Exception:
                continue

        if not keyboards:
            logger.warning(
                "No keyboard devices found! "
                "Make sure you are in the 'input' group: "
                "sudo usermod -aG input $USER"
            )
        return keyboards

    @classmethod
    def _get_mode_for_keycode(cls, keycode: int) -> Optional[str]:
        """Get mode name for a keycode, if any."""
        return cls._KEY_TO_MODE.get(keycode)

    @classmethod
    def _is_recording_mode(cls, mode: str) -> bool:
        """Check if a mode triggers audio recording."""
        return mode in CFG.MODES

    @classmethod
    def _handle_key_event(cls, event: evdev.InputEvent) -> None:
        """Process a single key event."""
        key_event = categorize(event)
        keycode = event.code

        mode = cls._get_mode_for_keycode(keycode)
        if mode is None:
            return

        # Key DOWN
        if key_event.keystate == key_event.key_down:
            cls._on_press(mode)

        # Key UP
        elif key_event.keystate == key_event.key_up:
            cls._on_release(mode)

    @classmethod
    def _on_press(cls, mode: str) -> None:
        """Handle key press for a recognized mode."""
        # Pin toggle (non-recording action)
        if mode == "pin":
            if not STATE.recording:
                ChatManager.toggle_pin()
            return

        # TTS toggle (non-recording action)
        if mode == "tts":
            if not STATE.recording:
                TTSService.toggle()
            return

        # Toggle mode: pressing same key again stops recording
        if STATE.recording and STATE.toggle_mode:
            if mode == STATE.current_mode:
                cls._stop_and_process()
            return

        if STATE.recording:
            return

        # Start recording for this mode
        if cls._is_recording_mode(mode):
            STATE.current_mode = mode

            # For rewrite mode, copy selected text first
            if mode == "ai_rewrite":
                ClipboardService.copy_selected()

            OverlayManager.show(mode)
            AudioService.start_recording()

    @classmethod
    def _on_release(cls, mode: str) -> None:
        """Handle key release for a recognized mode."""
        if not STATE.recording:
            return

        # In toggle mode, release does nothing
        if STATE.toggle_mode:
            return

        # Hold mode: release key stops recording
        if mode == STATE.current_mode:
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
        """
        Start the evdev keyboard listener (blocking).

        Monitors all keyboard devices using a selector for efficient I/O.
        Runs in a background thread — started from app.py.
        """
        keyboards = cls._find_keyboards()
        if not keyboards:
            print(
                "❌ No keyboard devices accessible.\n"
                "   Run: sudo usermod -aG input $USER\n"
                "   Then log out and back in."
            )
            return

        print(f"⌨️  Listening on {len(keyboards)} keyboard device(s)")

        sel = selectors.DefaultSelector()
        for dev in keyboards:
            sel.register(dev, selectors.EVENT_READ)

        try:
            # Loop exits automatically once all devices are gone
            while sel.get_map():
                for key, _ in sel.select():
                    device = key.fileobj
                    try:
                        for event in device.read():
                            if event.type == ecodes.EV_KEY:
                                cls._handle_key_event(event)
                    except OSError:
                        # Device disconnected — unregister and continue
                        logger.warning("Device disconnected: %s", device.path)
                        sel.unregister(device)
            logger.error("All keyboard devices disconnected!")
        except Exception as e:
            logger.error("Keyboard listener error: %s", e)
        finally:
            sel.close()
