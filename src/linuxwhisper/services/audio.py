"""
Audio recording and transcription service.
"""
from __future__ import annotations

import io
import queue
from typing import Any, Optional

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as wav_write

from linuxwhisper.api import GROQ_CLIENT
from linuxwhisper.config import CFG
from linuxwhisper.decorators import safe_execute
from linuxwhisper.state import STATE


class AudioService:
    """Audio recording and transcription service."""

    @staticmethod
    def audio_callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        """Capture audio chunks into buffer while recording."""
        if not STATE.recording:
            return

        data_copy = indata.copy()

        STATE.audio_buffer.append(data_copy)

        # Send downsampled data to visualization queue (skip if full)
        try:
            if STATE.viz_queue.qsize() < 5:
                flat_data = data_copy[:, 0][::10]  # Downsample
                STATE.viz_queue.put_nowait(flat_data)
        except Exception:
            pass

    @staticmethod
    def start_recording() -> None:
        """Start audio recording stream."""
        STATE.audio_buffer = []
        AudioService._clear_viz_queue()
        STATE.stream = sd.InputStream(
            samplerate=CFG.SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=AudioService.audio_callback
        )
        STATE.stream.start()
        STATE.recording = True

    @staticmethod
    def stop_recording() -> Optional[np.ndarray]:
        """Stop recording and return audio data."""
        STATE.recording = False
        if STATE.stream:
            STATE.stream.stop()
            STATE.stream.close()
            STATE.stream = None

        if STATE.audio_buffer:
            return np.concatenate(STATE.audio_buffer, axis=0)
        return None

    @staticmethod
    def _clear_viz_queue() -> None:
        """Clear the visualization queue."""
        while not STATE.viz_queue.empty():
            try:
                STATE.viz_queue.get_nowait()
            except queue.Empty:
                break

    @staticmethod
    @safe_execute("Transcription")
    def transcribe(audio_data: np.ndarray) -> Optional[str]:
        """Transcribe audio using Groq Whisper."""
        wav_buffer = io.BytesIO()
        wav_buffer.name = "audio.wav"
        wav_write(wav_buffer, CFG.SAMPLE_RATE, audio_data)
        wav_buffer.seek(0)

        transcript = GROQ_CLIENT.audio.transcriptions.create(
            model=CFG.MODEL_WHISPER,
            file=wav_buffer
        )
        return transcript.text.strip()
