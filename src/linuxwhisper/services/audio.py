"""
Audio recording and streaming transcription service.

Captured audio goes straight to Deepgram while the hotkey is held, so the
transcript only depends on the trailing audio when the hotkey is released.
"""
from __future__ import annotations

import queue
from typing import Any, Optional

import numpy as np
import sounddevice as sd

from linuxwhisper.config import CFG
from linuxwhisper.decorators import safe_execute
from linuxwhisper.managers.overlay import OverlayManager
from linuxwhisper.services.deepgram import DeepgramLiveSession
from linuxwhisper.state import STATE


class AudioService:
    """Audio recording and transcription service."""

    @staticmethod
    def audio_callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        """Stream captured audio to Deepgram and the overlay visualizer."""
        if not STATE.recording:
            return

        session = STATE.deepgram
        if session is not None:
            # PortAudio reuses this buffer, so hand over a copy.
            session.send(indata.copy())

        # Send downsampled data to visualization queue (skip if full)
        try:
            if STATE.viz_queue.qsize() < 5:
                STATE.viz_queue.put_nowait(indata[:, 0][::10])
        except Exception:
            pass

    @staticmethod
    def start_recording() -> None:
        """Open the transcription stream and start capturing audio."""
        AudioService._clear_viz_queue()

        session = DeepgramLiveSession(
            model=CFG.DEEPGRAM_MODEL,
            language=CFG.DEEPGRAM_LANGUAGE,
            sample_rate=CFG.SAMPLE_RATE,
            on_partial=OverlayManager.set_text,
        )
        STATE.deepgram = session if session.start() else None

        STATE.stream = sd.InputStream(
            samplerate=CFG.SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=AudioService.audio_callback
        )
        STATE.stream.start()
        STATE.recording = True

    @staticmethod
    def stop_recording() -> bool:
        """Stop capturing audio; True if a transcript is still pending."""
        STATE.recording = False
        if STATE.stream:
            STATE.stream.stop()
            STATE.stream.close()
            STATE.stream = None

        return STATE.deepgram is not None

    @staticmethod
    @safe_execute("Transcription")
    def transcribe() -> Optional[str]:
        """Finish the Deepgram stream and return the final transcript."""
        session = STATE.deepgram
        STATE.deepgram = None
        if session is None:
            return None

        return session.finish()

    @staticmethod
    def _clear_viz_queue() -> None:
        """Clear the visualization queue."""
        while not STATE.viz_queue.empty():
            try:
                STATE.viz_queue.get_nowait()
            except queue.Empty:
                break
