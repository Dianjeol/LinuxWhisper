"""
Unified handler for all recording modes.
"""
from __future__ import annotations

import threading

import numpy as np
import pyperclip

from linuxwhisper.decorators import run_on_main_thread
from linuxwhisper.managers.chat import ChatManager
from linuxwhisper.managers.history import HistoryManager
from linuxwhisper.managers.overlay import OverlayManager
from linuxwhisper.services.ai import AIService
from linuxwhisper.services.audio import AudioService
from linuxwhisper.services.clipboard import ClipboardService
from linuxwhisper.services.image import ImageService
from linuxwhisper.services.tts import TTSService
from linuxwhisper.state import STATE

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib


class ModeHandler:
    """Unified handler for all recording modes."""

    @staticmethod
    @run_on_main_thread
    def stop_recording_safe() -> None:
        """Safely stop recording and process (callable from any thread)."""
        if not STATE.recording:
            return

        print("🛑 Voice Stop Triggered (Silence)")
        OverlayManager.hide()
        audio_data = AudioService.stop_recording()

        if audio_data is not None:
            # Process in background
            threading.Thread(
                target=ModeHandler._process_worker,
                args=(STATE.current_mode, audio_data),
                daemon=True
            ).start()

    @staticmethod
    def _process_worker(mode: str, audio_data: np.ndarray) -> None:
        """Worker thread for processing audio."""
        transcribed = None
        try:
            transcribed = AudioService.transcribe(audio_data)
        except Exception:
            pass

        if transcribed:
            # Run processing (API calls etc)
            GLib.idle_add(lambda: ModeHandler.process(mode, transcribed))

    @staticmethod
    def process(mode: str, transcribed_text: str) -> None:
        """Route to appropriate handler based on mode."""
        # --- Hallucination Guard ---
        # Whisper often outputs "Thank you", "You're welcome", or "Subtitle" on silence.
        # We filter these out to prevent weird loops.
        clean = transcribed_text.strip().lower().replace(".", "").replace("!", "")
        hallucinations = {"thank you", "you're welcome", "thanks", "subtitle", "untertitel", "you"}
        if clean in hallucinations or len(clean) < 2:
            print(f"⚠️ Ignored Hallucination: '{transcribed_text}'")
            return

        handlers = {
            "dictation": ModeHandler._handle_dictation,
            "ai": ModeHandler._handle_ai,
            "ai_rewrite": ModeHandler._handle_ai_rewrite,
            "vision": ModeHandler._handle_vision,
        }
        handler = handlers.get(mode)
        if handler and transcribed_text:
            handler(transcribed_text)

    @staticmethod
    def _handle_dictation(text: str) -> None:
        """Handle dictation mode: transcribe and type."""
        HistoryManager.add_answer(f"[Dictation] {text}")
        ChatManager.add_message("user", f"🎤 {text}")
        ClipboardService.type_text(text)

    @staticmethod
    def _handle_ai(text: str) -> None:
        """Handle AI chat mode: get response and type."""
        response = AIService.chat(text)
        if not response:
            return

        # Update histories
        HistoryManager.add_message("user", text)
        HistoryManager.add_message("assistant", response)
        HistoryManager.add_answer(response)

        # Update chat overlay
        ChatManager.add_message("user", text)
        ChatManager.add_message("assistant", response)

        ClipboardService.type_text(response)
        TTSService.speak(response)

    @staticmethod
    def _handle_ai_rewrite(text: str) -> None:
        """Handle AI rewrite mode: rewrite selected text based on instruction."""
        original = pyperclip.paste().strip()
        prompt = (
            f"INSTRUCTION:\n{text}\n\n"
            f"ORIGINAL TEXT:\n{original}\n\n"
            "Rewrite the original text based on the instruction. "
            "Output ONLY the finished text, without introduction or formatting."
        )

        response = AIService.chat(prompt)
        if not response:
            return

        # Update histories
        HistoryManager.add_message("user", f"[Rewrite] {text}\nOriginal: {original[:200]}...")
        HistoryManager.add_message("assistant", response)
        HistoryManager.add_answer(response)

        # Update chat overlay
        ChatManager.add_message("user", f"✍️ {text}")
        ChatManager.add_message("assistant", response)

        ClipboardService.paste_text(response)
        TTSService.speak(response)

    @staticmethod
    def _handle_vision(text: str) -> None:
        """Handle vision mode: screenshot + AI analysis."""
        image_b64 = ImageService.take_screenshot()
        if not image_b64:
            return

        response = AIService.vision(text, image_b64)
        if not response:
            return

        # Update histories
        HistoryManager.add_message("user", f"[Screenshot] {text}")
        HistoryManager.add_message("assistant", response)
        HistoryManager.add_answer(response)

        # Update chat overlay
        ChatManager.add_message("user", f"📸 {text}")
        ChatManager.add_message("assistant", response)

        ClipboardService.type_text(response)
        TTSService.speak(response)
