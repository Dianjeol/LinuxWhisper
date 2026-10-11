"""
Deepgram live (streaming) transcription.

Push-to-talk audio is streamed to Deepgram's WebSocket endpoint
(``wss://api.deepgram.com/v1/listen``) while it is captured. While the key is
held the running transcript is published through an optional callback (the
recording overlay shows it); :meth:`DeepgramLiveSession.finish` returns the
complete transcript once the key is released.

Requires DEEPGRAM_API_KEY in the environment.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any, Callable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Time allowed for the connection to come up before queued audio is dropped.
CONNECT_WAIT = 4.0
# Time allowed for the queued audio to reach Deepgram before Finalize.
DRAIN_TIMEOUT = 5.0
# Time allowed for the final transcript after Finalize.
FINALIZE_TIMEOUT = 4.0
# Shorter budget when no result arrived while recording (most likely silence).
FINALIZE_EMPTY_TIMEOUT = 2.0
# Quiet time after the first final result, to catch trailing segments.
FINALIZE_GRACE = 0.35
# Time allowed for the socket to close.
CLOSE_TIMEOUT = 2.0


def _to_linear16(chunk: np.ndarray) -> bytes:
    """Convert float32 mono samples in [-1, 1] to little-endian 16-bit PCM."""
    samples = np.asarray(chunk, dtype=np.float32).reshape(-1)
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


class DeepgramLiveSession:
    """One dictation recording, streamed to Deepgram while it is captured."""

    def __init__(
        self,
        *,
        model: str,
        language: str,
        sample_rate: int,
        on_partial: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._model = model
        self._language = language
        self._sample_rate = sample_rate
        # Called with the transcript so far (finalized segments plus the current
        # unfinished one) while the hotkey is held — the overlay shows it live.
        self._on_partial = on_partial

        self._audio: "queue.Queue[Optional[np.ndarray]]" = queue.Queue()
        self._lock = threading.Lock()
        self._segments: List[str] = []
        self._interim = ""
        self._last_partial = ""
        self._live = True
        self._flushed = threading.Event()
        self._last_result_at = 0.0
        self._failed = False
        self._closed = False

        self._ctx: Optional[Any] = None
        self._socket: Optional[Any] = None
        self._connect_thread: Optional[threading.Thread] = None
        self._sender_thread: Optional[threading.Thread] = None
        self._listen_thread: Optional[threading.Thread] = None

    # -- recording ---------------------------------------------------------
    def send(self, chunk: np.ndarray) -> None:
        """Queue captured audio for transmission."""
        self._audio.put(chunk)

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        """Open the stream in the background; audio queues up until it is ready."""
        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            print("❌ Deepgram: DEEPGRAM_API_KEY fehlt – Diktat nicht möglich")
            self._failed = True
            return False

        self._connect_thread = threading.Thread(
            target=self._connect, args=(api_key,), name="deepgram-connect", daemon=True
        )
        self._connect_thread.start()
        self._sender_thread = threading.Thread(target=self._send_loop, name="deepgram-send", daemon=True)
        self._sender_thread.start()
        return True

    def finish(self) -> Optional[str]:
        """Flush the stream and return the complete transcript."""
        self._audio.put(None)
        if self._sender_thread is not None:
            self._sender_thread.join(timeout=DRAIN_TIMEOUT)

        # The recording is over: no more live updates for the overlay, and the
        # trailing audio flushed below belongs to the returned transcript.
        self._live = False

        socket = self._socket
        if socket is not None and not self._failed:
            try:
                socket.send_finalize()
            except Exception as exc:
                print(f"❌ Deepgram: Finalize fehlgeschlagen ({exc})")

            # Finalize makes the server process the buffered audio; results
            # flagged from_finalize mark that flush (docs: /docs/finalize).
            with self._lock:
                has_text = bool(self._segments)
            deadline = time.time() + (FINALIZE_TIMEOUT if has_text else FINALIZE_EMPTY_TIMEOUT)
            while time.time() < deadline:
                with self._lock:
                    quiet_since = self._last_result_at
                if self._flushed.is_set() and time.time() - quiet_since >= FINALIZE_GRACE:
                    break
                time.sleep(0.03)

        self._close()

        with self._lock:
            segments = list(self._segments)
        return " ".join(segments).strip() or None

    # -- connection --------------------------------------------------------
    def _connect(self, api_key: str) -> None:
        try:
            from deepgram import DeepgramClient
            from deepgram.core.events import EventType

            client = DeepgramClient(api_key=api_key)
            ctx = client.listen.v1.connect(
                model=self._model,
                language=self._language,
                encoding="linear16",
                sample_rate=str(self._sample_rate),
                channels="1",
                smart_format="true",
                interim_results="true",
                mip_opt_out="true",
            )
            socket = ctx.__enter__()
            if self._closed:
                ctx.__exit__(None, None, None)
                return

            socket.on(EventType.MESSAGE, self._on_message)
            socket.on(EventType.ERROR, self._on_error)
        except Exception as exc:
            print(f"❌ Deepgram: Verbindung fehlgeschlagen ({exc})")
            self._failed = True
            return

        self._ctx, self._socket = ctx, socket
        self._listen_thread = threading.Thread(
            target=socket.start_listening, name="deepgram-listen", daemon=True
        )
        self._listen_thread.start()

    def _send_loop(self) -> None:
        """Send queued audio in order, starting as soon as the socket is up."""
        while True:
            chunk = self._audio.get()
            if chunk is None:
                return

            deadline = time.time() + CONNECT_WAIT
            while self._socket is None and not self._failed and not self._closed and time.time() < deadline:
                time.sleep(0.01)

            socket = self._socket
            if socket is None:
                continue
            try:
                socket.send_media(_to_linear16(chunk))
            except Exception as exc:
                print(f"❌ Deepgram: Senden fehlgeschlagen ({exc})")
                self._failed = True

    def _close(self) -> None:
        self._closed = True
        socket, ctx = self._socket, self._ctx
        self._socket, self._ctx = None, None

        if socket is not None:
            try:
                socket.send_close_stream()
            except Exception:
                pass
        if ctx is not None:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass
        if self._listen_thread is not None:
            self._listen_thread.join(timeout=CLOSE_TIMEOUT)

    # -- events ------------------------------------------------------------
    def _on_message(self, message: Any) -> None:
        if getattr(message, "type", None) != "Results":
            return

        alternatives = getattr(getattr(message, "channel", None), "alternatives", None)
        if not alternatives:
            return

        transcript = (alternatives[0].transcript or "").strip()
        if not transcript:
            return

        now = time.time()
        with self._lock:
            self._last_result_at = now
            if getattr(message, "is_final", False):
                self._segments.append(transcript)
                self._interim = ""
            else:
                self._interim = transcript
            partial = " ".join(self._segments + ([self._interim] if self._interim else []))
            publish = self._live and partial != self._last_partial
            if publish:
                self._last_partial = partial

        if getattr(message, "from_finalize", False):
            self._flushed.set()

        if publish and self._on_partial is not None:
            self._on_partial(partial)

    def _on_error(self, error: Any) -> None:
        print(f"❌ Deepgram: {error}")
        self._failed = True
