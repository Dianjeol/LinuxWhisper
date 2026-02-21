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

        # Unified Aria Handler
        if mode == "aria":
            ModeHandler._handle_aria(transcribed_text)
        
    @staticmethod
    def _handle_aria(text: str) -> None:
        """
        Handle Aria mode with Intellectual Router:
        1. Get Context (Clipboard from Ctrl+C)
        2. Route (Dictation vs Agent vs Vision)
        3. Execute & Output
        """
        # 1. Get Context
        try:
            # We assume keyboard handler triggered Ctrl+C
            context = pyperclip.paste().strip()
        except Exception:
            context = ""

        # 2. Router & Process
        # This returns (Action_Type, Result_Text)
        result = AIService.route_and_process(text, context)
        
        if not result:
            return

        action_type, response = result

        # 3. Output Logic
        
        if action_type == "DICTATION":
            # Pure Dictation: Just type it. No history, no TTS (usually).
            ClipboardService.type_text(response)
            
            # Optional: Add to chat overlay just for visibility? 
            # User request implied they want it to *be* dictation, not a chat.
            # So we probably do NOT add to history or speak.
            print(f"✍️ Dictated: {response}")
            
        else:
            # AGENT or VISION
            # Standard Assistant Behavior
            
            # Log to History
            msg_type = " [Vision]" if action_type == "VISION" else ""
            HistoryManager.add_message("user", f"{text}{msg_type}")
            HistoryManager.add_message("assistant", response)
            HistoryManager.add_answer(response)
    
            # Update Chat Overlay
            icon = "📸" if action_type == "VISION" else "✨"
            ChatManager.add_message("user", f"{icon} {text}")
            ChatManager.add_message("assistant", response)
    
            # Type text (replaces selection if it existed, or types at cursor)
            # For Agent, we might NOT always want to type? 
            # Current behavior is: Always type response.
            ClipboardService.type_text(response)
            
            # Speak response
            TTSService.speak(response)
