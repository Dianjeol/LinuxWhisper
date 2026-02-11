"""
Text-to-speech service using Groq Orpheus.
"""
from __future__ import annotations

import subprocess
import threading

from linuxwhisper.api import GROQ_CLIENT
from linuxwhisper.config import CFG
from linuxwhisper.state import STATE


class TTSService:
    """Text-to-speech service using Groq Orpheus."""

    @staticmethod
    def speak(text: str) -> None:
        """Convert text to speech and play (async)."""
        if not STATE.tts_enabled or not text:
            return

        def _speak_thread():
            try:
                response = GROQ_CLIENT.audio.speech.create(
                    model=CFG.MODEL_TTS,
                    voice=STATE.tts_voice,
                    input=text[:CFG.TTS_MAX_CHARS],
                    response_format="wav"
                )
                response.write_to_file(CFG.TEMP_TTS_PATH)
                subprocess.run(["aplay", "-q", CFG.TEMP_TTS_PATH], capture_output=True)
            except Exception as e:
                print(f"❌ TTS Error: {e}")

        threading.Thread(target=_speak_thread, daemon=True).start()

    @staticmethod
    def toggle() -> None:
        """Toggle TTS enabled state."""
        STATE.tts_enabled = not STATE.tts_enabled
        # Late import to avoid circular dependency
        from linuxwhisper.managers.chat import ChatManager
        ChatManager.refresh_overlay()
