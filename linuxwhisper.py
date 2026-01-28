#!/usr/bin/env python3
"""
LinuxWhisper - Voice Assistant for Linux
=========================================

A voice-to-text and AI assistant tool that integrates with Groq APIs
for transcription, chat completion, vision analysis, and text-to-speech.

ARCHITECTURE OVERVIEW
---------------------
Section 1: Imports
Section 2: Configuration (Config dataclass - all constants)
Section 3: State Management (AppState dataclass - all mutable state)
Section 4: Services (AudioService, AIService, TTSService, ClipboardService)
Section 5: Managers (HistoryManager, ChatManager)
Section 6: UI Components (GtkOverlay, ChatOverlay)
Section 7: System Tray (TrayManager)
Section 8: Keyboard Handler (KeyboardHandler)
Section 9: Main Entry Point

ADDING A NEW MODE
-----------------
1. Add mode config to Config.MODES dict
2. Add key mapping to KeyboardHandler.KEY_MAPPINGS
3. Create handler method in ModeHandler._handle_<mode>
4. Register in ModeHandler.HANDLERS dispatch dict

HOTKEYS
-------
F3:  Dictation (speech-to-text, types at cursor)
F4:  AI Chat (voice question → AI response)
F7:  AI Rewrite (select text + voice instruction → rewritten text)
F8:  Vision (screenshot + voice question → AI analysis)
F9:  Toggle chat overlay pin mode
F10: Toggle TTS (text-to-speech for AI responses)
"""

# ============================================================================
# SECTION 1: IMPORTS
# ============================================================================
from __future__ import annotations

import base64
import io
import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import warnings
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore", category=DeprecationWarning)

import cairo
import gi
import numpy as np
import pyperclip
import sounddevice as sd
from groq import Groq
from pynput import keyboard
from scipy.io.wavfile import write as wav_write

gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
gi.require_version('WebKit2', '4.1')
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import Gdk, GLib, Gtk, WebKit2


# ============================================================================
# SECTION 2: CONFIGURATION
# ============================================================================
@dataclass(frozen=True)
class Config:
    """
    Immutable application configuration.
    
    All constants are centralized here for easy modification.
    To change a setting, edit the default value below.
    """
    # --- Audio Settings ---
    SAMPLE_RATE: int = 44100
    
    # --- History Limits ---
    MAX_TOKENS: int = 32000
    ANSWER_HISTORY_LIMIT: int = 15
    CHAT_MESSAGE_LIMIT: int = 20
    CHAT_AUTO_HIDE_SEC: int = 5
    
    # --- AI Models ---
    MODEL_CHAT: str = "moonshotai/kimi-k2-instruct"
    MODEL_VISION: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    MODEL_WHISPER: str = "whisper-large-v3"
    MODEL_TTS: str = "canopylabs/orpheus-v1-english"
    
    # --- TTS Voices ---
    TTS_VOICES: Tuple[str, ...] = ("diana", "hannah", "autumn", "austin", "daniel", "troy")
    TTS_DEFAULT_VOICE: str = "diana"
    TTS_MAX_CHARS: int = 4000
    
    # --- Temp File Paths ---
    TEMP_SCREEN_PATH: str = "/tmp/temp_screen.png"
    TEMP_TTS_PATH: str = "/tmp/linuxwhisper_tts.wav"
    
    CONFIG_PATH: str = os.path.expanduser("~/.config/linuxwhisper/config.json")
    
    # --- System Prompt ---
    SYSTEM_PROMPT: str = (
        "Act as a compassionate assistant. Base your reasoning on the principles of "
        "Nonviolent Communication and A Course in Miracles. Apply these frameworks as "
        "your underlying logic without explicitly naming them or forcing them. Let your "
        "output be grounded, clear, and highly concise. Return ONLY the direct response."
    )
    
    # --- Mode Definitions (icon, overlay text, colors) ---
    MODES: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "dictation":  {"icon": "🎙️", "text": "Listening...",    "bg": "#1a1a2e", "fg": "#00d4ff"},
        "ai":         {"icon": "🤖", "text": "AI Listening...", "bg": "#1a1a2e", "fg": "#a855f7"},
        "ai_rewrite": {"icon": "✍️", "text": "Rewrite Mode...", "bg": "#1a1a2e", "fg": "#22c55e"},
        "vision":     {"icon": "📸", "text": "Vision Mode...",  "bg": "#1a1a2e", "fg": "#f59e0b"},
    })

    def load(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not os.path.exists(self.CONFIG_PATH):
            return {}
        try:
            with open(self.CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading config: {e}")
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        """Save configuration to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
            with open(self.CONFIG_PATH, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"⚠️ Error saving config: {e}")


# Global config instance
CFG = Config()


# ============================================================================
# SECTION 3: STATE MANAGEMENT
# ============================================================================
@dataclass
class AppState:
    """
    Mutable application state.
    
    All runtime state is centralized here for clarity and debugging.
    Reset by creating a new instance: STATE = AppState()
    """
    def __post_init__(self):
        """Load configuration on init."""
        data = CFG.load()
        if "voice" in data:
            self.tts_voice = data["voice"]
        if "hotkeys" in data:
            self.custom_hotkeys = data["hotkeys"]
    
    # --- Recording State ---
    recording: bool = False
    current_mode: Optional[str] = None
    audio_buffer: List[np.ndarray] = field(default_factory=list)
    stream: Optional[sd.InputStream] = None
    viz_queue: queue.Queue = field(default_factory=queue.Queue)
    
    # --- UI Windows ---
    overlay_window: Optional[Any] = None  # GtkOverlay instance
    chat_overlay_window: Optional[Any] = None  # ChatOverlay instance
    
    # --- Chat State ---
    chat_messages: List[Dict[str, str]] = field(default_factory=list)
    chat_pinned: bool = False
    chat_hide_timer: Optional[int] = None
    
    # --- History ---
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    answer_history: List[Dict[str, str]] = field(default_factory=list)
    
    # --- TTS ---
    tts_enabled: bool = True  # Enabled by default
    tts_voice: str = CFG.TTS_DEFAULT_VOICE
    
    # --- System Tray ---
    indicator: Optional[AppIndicator.Indicator] = None
    gtk_menu: Optional[Gtk.Menu] = None
    
    # --- Configuration ---
    custom_hotkeys: Dict[str, str] = field(default_factory=dict)


# Global state instance
STATE = AppState()


# ============================================================================
# SECTION 4: API CLIENT INITIALIZATION
# ============================================================================
def _init_groq_client() -> Groq:
    """Initialize Groq API client with environment key."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("❌ Error: GROQ_API_KEY missing. Please check your environment variables!")
        sys.exit(1)
    return Groq(api_key=api_key)


GROQ_CLIENT = _init_groq_client()


# ============================================================================
# SECTION 5: UTILITY DECORATORS
# ============================================================================
def safe_execute(operation: str) -> Callable:
    """
    Decorator for consistent error handling.
    
    Usage:
        @safe_execute("Transcription")
        def transcribe_audio(data):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"❌ {operation} Error: {e}")
                return None
        return wrapper
    return decorator


def run_on_main_thread(func: Callable) -> Callable:
    """Decorator to schedule function execution on GTK main thread."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        GLib.idle_add(lambda: func(*args, **kwargs))
    return wrapper


# ============================================================================
# SECTION 6: SERVICES
# ============================================================================

# --- Audio Service ---
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


# --- AI Service ---
class AIService:
    """AI chat and vision completion service."""
    
    @staticmethod
    def build_messages(user_content: str) -> List[Dict[str, Any]]:
        """Build API messages with system prompt and conversation history."""
        messages = [{"role": "system", "content": CFG.SYSTEM_PROMPT}]
        messages.extend(STATE.conversation_history)
        messages.append({"role": "user", "content": user_content})
        return messages
    
    @staticmethod
    @safe_execute("AI Chat")
    def chat(prompt: str) -> Optional[str]:
        """Send chat completion request."""
        messages = AIService.build_messages(prompt)
        response = GROQ_CLIENT.chat.completions.create(
            model=CFG.MODEL_CHAT,
            messages=messages
        )
        return response.choices[0].message.content
    
    @staticmethod
    @safe_execute("AI Vision")
    def vision(prompt: str, image_base64: str) -> Optional[str]:
        """Send vision completion request with image."""
        messages = AIService.build_messages(prompt)
        # Replace last user message with multimodal content
        messages[-1] = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            ]
        }
        response = GROQ_CLIENT.chat.completions.create(
            model=CFG.MODEL_VISION,
            messages=messages
        )
        return response.choices[0].message.content


# --- TTS Service ---
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
        ChatManager.refresh_overlay()


# --- Clipboard Service ---
class ClipboardService:
    """Clipboard operations for typing and pasting text."""
    
    @staticmethod
    def type_text(text: str) -> None:
        """Paste text at cursor via clipboard (fast)."""
        if not text:
            return
        
        # Save original clipboard
        try:
            original = pyperclip.paste()
        except Exception:
            original = None
        
        # Add leading space to prevent word merging
        clean_text = f" {text.strip()}" if not text.startswith(" ") else text
        
        # Paste via clipboard
        pyperclip.copy(clean_text)
        subprocess.run(["xdotool", "key", "ctrl+v"])
        
        # Restore original clipboard after short delay
        time.sleep(0.1)
        if original is not None:
            try:
                pyperclip.copy(original)
            except Exception:
                pass
    
    @staticmethod
    def copy_selected() -> str:
        """Copy currently selected text and return it."""
        subprocess.run(["xdotool", "key", "ctrl+c"])
        time.sleep(0.1)
        return pyperclip.paste().strip()
    
    @staticmethod
    def paste_text(text: str) -> None:
        """Paste text directly via clipboard."""
        pyperclip.copy(text)
        subprocess.run(["xdotool", "key", "ctrl+v"])


# --- Image Service ---
class ImageService:
    """Screenshot and image encoding service."""
    
    @staticmethod
    @safe_execute("Screenshot")
    def take_screenshot() -> Optional[str]:
        """Take screenshot and return base64 encoded string."""
        subprocess.run(["gnome-screenshot", "-f", CFG.TEMP_SCREEN_PATH])
        with open(CFG.TEMP_SCREEN_PATH, "rb") as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
        os.remove(CFG.TEMP_SCREEN_PATH)
        return encoded


# ============================================================================
# SECTION 7: MANAGERS
# ============================================================================

# --- History Manager ---
class HistoryManager:
    """Manages conversation and answer history."""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate (~4 chars per token)."""
        return len(text) // 4
    
    @staticmethod
    def get_history_tokens() -> int:
        """Calculate total tokens in conversation history."""
        return sum(
            HistoryManager.estimate_tokens(msg["content"])
            for msg in STATE.conversation_history
        )
    
    @staticmethod
    def trim_history() -> None:
        """Remove oldest messages until under token limit."""
        while (HistoryManager.get_history_tokens() > CFG.MAX_TOKENS 
               and STATE.conversation_history):
            STATE.conversation_history.pop(0)
    
    @staticmethod
    def add_message(role: str, content: str) -> None:
        """Add message to conversation history and trim if needed."""
        STATE.conversation_history.append({"role": role, "content": content})
        HistoryManager.trim_history()
    
    @staticmethod
    def add_answer(text: str) -> None:
        """Add answer to tray history."""
        timestamp = time.strftime("%H:%M")
        STATE.answer_history.insert(0, {"text": text, "timestamp": timestamp})
        
        # Trim to limit
        if len(STATE.answer_history) > CFG.ANSWER_HISTORY_LIMIT:
            STATE.answer_history = STATE.answer_history[:CFG.ANSWER_HISTORY_LIMIT]
        
        TrayManager.update_menu()
    
    @staticmethod
    def clear_all() -> None:
        """Clear all history."""
        STATE.answer_history = []
        STATE.conversation_history = []
        STATE.chat_messages = []
        TrayManager.update_menu()
        ChatManager.refresh_overlay()


# --- Chat Manager ---
class ChatManager:
    """Manages chat overlay state and messages."""
    
    @staticmethod
    def add_message(role: str, text: str) -> None:
        """Add message to chat overlay."""
        STATE.chat_messages.append({"role": role, "text": text})
        
        # Trim to limit
        if len(STATE.chat_messages) > CFG.CHAT_MESSAGE_LIMIT:
            STATE.chat_messages = STATE.chat_messages[-CFG.CHAT_MESSAGE_LIMIT:]
        
        ChatManager.refresh_overlay()
    
    @staticmethod
    def toggle_pin() -> None:
        """Toggle chat overlay pin mode."""
        STATE.chat_pinned = not STATE.chat_pinned
        
        if not STATE.chat_pinned and STATE.chat_overlay_window:
            ChatManager._cancel_timer()
            STATE.chat_overlay_window.start_fade_out(callback=ChatManager._destroy)
        else:
            ChatManager.refresh_overlay()
    
    @staticmethod
    @run_on_main_thread
    def refresh_overlay(status_text: Optional[str] = None) -> None:
        """Refresh chat overlay on main thread."""
        ChatManager._show_overlay(status_text)
    
    @staticmethod
    def _show_overlay(status_text: Optional[str] = None) -> None:
        """Show or update chat overlay."""
        ChatManager._cancel_timer()
        
        if not STATE.chat_overlay_window:
            STATE.chat_overlay_window = ChatOverlay()
        elif STATE.chat_overlay_window.fade_out_active:
            STATE.chat_overlay_window.start_fade_in()
        
        STATE.chat_overlay_window.update_content(
            STATE.chat_messages,
            status_text,
            is_pinned=STATE.chat_pinned,
            is_tts=STATE.tts_enabled
        )
        
        if not STATE.chat_pinned:
            STATE.chat_hide_timer = GLib.timeout_add_seconds(
                CFG.CHAT_AUTO_HIDE_SEC,
                ChatManager._auto_hide
            )
    
    @staticmethod
    def _auto_hide() -> bool:
        """Auto-hide callback."""
        STATE.chat_hide_timer = None
        if not STATE.chat_pinned and STATE.chat_overlay_window:
            STATE.chat_overlay_window.start_fade_out(callback=ChatManager._destroy)
        return False
    
    @staticmethod
    def _cancel_timer() -> None:
        """Cancel auto-hide timer if active."""
        if STATE.chat_hide_timer:
            GLib.source_remove(STATE.chat_hide_timer)
            STATE.chat_hide_timer = None
    
    @staticmethod
    def _destroy() -> None:
        """Destroy chat overlay window."""
        if STATE.chat_overlay_window:
            STATE.chat_overlay_window.close()
            STATE.chat_overlay_window = None


# ============================================================================
# SECTION 8: UI COMPONENTS
# ============================================================================

# --- Recording Overlay ---
class GtkOverlay(Gtk.Window):
    """Floating recording overlay with waveform visualization."""
    
    def __init__(self, mode: str):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.mode = mode
        self.config = CFG.MODES.get(mode, CFG.MODES["dictation"])
        self._setup_window()
        self._setup_ui()
        self.show_all()
    
    def _setup_window(self) -> None:
        """Configure window properties."""
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_keep_above(True)
        
        # Enable transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        
        # Position at bottom center
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geometry = monitor.get_geometry()
        w, h = 220, 60
        x = (geometry.width - w) // 2
        y = geometry.height - h - 80
        self.move(x, y)
        self.set_default_size(w, h)
    
    def _setup_ui(self) -> None:
        """Setup drawing area and animation."""
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self._on_draw)
        self.add(self.drawing_area)
        self.timeout_id = GLib.timeout_add(40, self._animate)
    
    def _on_draw(self, widget: Gtk.DrawingArea, cr: cairo.Context) -> None:
        """Draw overlay content."""
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        bg_rgb = self._hex_to_rgb(self.config["bg"])
        fg_rgb = self._hex_to_rgb(self.config["fg"])
        
        # Background rounded rect
        self._draw_rounded_rect(cr, w, h, 15)
        cr.set_source_rgba(*bg_rgb, 0.92)
        cr.fill()
        
        # Icon
        cr.set_source_rgb(*fg_rgb)
        cr.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(20)
        ext = cr.text_extents(self.config["icon"])
        cr.move_to(30 - ext.width / 2, h / 2 + ext.height / 2)
        cr.show_text(self.config["icon"])
        
        # Text
        cr.set_font_size(10)
        cr.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ext = cr.text_extents(self.config["text"])
        cr.move_to(110 - ext.width / 2, 20)
        cr.show_text(self.config["text"])
        
        # Waveform
        self._draw_waveform(cr, 60, 210, 45, fg_rgb)
    
    def _draw_rounded_rect(self, cr: cairo.Context, w: int, h: int, r: int) -> None:
        """Draw rounded rectangle path."""
        cr.new_sub_path()
        cr.arc(w - r, r, r, -math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
    
    def _draw_waveform(self, cr: cairo.Context, x1: int, x2: int, cy: int, color: Tuple[float, ...]) -> None:
        """Draw audio waveform bars."""
        # Get latest audio data
        data = None
        while not STATE.viz_queue.empty():
            try:
                data = STATE.viz_queue.get_nowait()
            except queue.Empty:
                break
        
        cr.set_source_rgb(*color)
        cr.set_line_width(3)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        
        if data is not None and len(data) > 0:
            width = x2 - x1
            num_bars = 30
            step = max(1, len(data) // num_bars)
            bar_width = width / num_bars
            max_height = 15
            
            for i in range(num_bars):
                idx = i * step
                if idx >= len(data):
                    break
                chunk = data[idx:idx + step]
                amp = np.max(np.abs(chunk)) if len(chunk) > 0 else 0
                bar_h = max(1, min(max_height, amp * 40 * max_height))
                
                x = x1 + i * bar_width
                cr.move_to(x, cy - bar_h)
                cr.line_to(x, cy + bar_h)
                cr.stroke()
        else:
            # Idle line
            cr.set_line_width(2)
            cr.set_source_rgb(0.33, 0.33, 0.33)
            cr.move_to(x1, cy)
            cr.line_to(x2, cy)
            cr.stroke()
    
    def _animate(self) -> bool:
        """Animation tick."""
        self.drawing_area.queue_draw()
        return True
    
    @staticmethod
    def _hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
        """Convert hex color to RGB tuple (0-1 range)."""
        h = hex_str.lstrip('#')
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    
    def close(self) -> None:
        """Clean up and destroy."""
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None
        self.destroy()


class OverlayManager:
    """Manages recording overlay visibility."""
    
    @staticmethod
    @run_on_main_thread
    def show(mode: str) -> None:
        """Show overlay for given mode."""
        OverlayManager._show_impl(mode)
    
    @staticmethod
    def _show_impl(mode: str) -> None:
        if STATE.overlay_window:
            try:
                STATE.overlay_window.close()
            except Exception:
                pass
        STATE.overlay_window = GtkOverlay(mode)
    
    @staticmethod
    @run_on_main_thread
    def hide() -> None:
        """Hide overlay."""
        OverlayManager._hide_impl()
    
    @staticmethod
    def _hide_impl() -> None:
        if STATE.overlay_window:
            STATE.overlay_window.close()
            STATE.overlay_window = None


# --- Chat Overlay HTML Template ---
CHAT_CSS = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  height: 100%;
  background: #ECE5DD;
  font-family: -apple-system, Helvetica, Arial, sans-serif;
  font-size: 14px;
  overflow-x: hidden;
  background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4cfc4' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
}
.pin-hint {
  position: sticky; top: 0;
  background: #D1D9E6;
  color: #111b21; text-align: center;
  padding: 8px 12px; font-size: 12px; font-weight: 500;
  z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  border-radius: 0 0 12px 12px; margin: 0 20px 10px 20px;
}
.pin-hint kbd { background: rgba(0,0,0,0.1); padding: 2px 6px; border-radius: 4px; font-family: inherit; font-weight: 600; }
.voice-btn { background: rgba(0,0,0,0.1); border: none; color: #111b21; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; }
.voice-btn:hover { background: rgba(0,0,0,0.15); }
.dropdown { position: relative; display: inline-block; }
.dropdown-content { display: none; position: absolute; top: 100%; left: 50%; transform: translateX(-50%); background: white; min-width: 100px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); border-radius: 8px; z-index: 1000; margin-top: 6px; padding: 4px 0; }
.dropdown-content.show { display: block; animation: slideDown 0.2s ease; }
@keyframes slideDown { from { opacity: 0; transform: translate(-50%, -10px); } to { opacity: 1; transform: translate(-50%, 0); } }
.dropdown-item { color: #4a5568; padding: 6px 12px; display: block; font-size: 13px; cursor: pointer; transition: background 0.1s; }
.dropdown-item:hover { background: #f7fafc; color: #667eea; }
.dropdown-item.selected { background: #ebf4ff; color: #5a67d8; font-weight: 600; }
.settings-link { text-decoration: none; font-size: 14px; cursor: pointer; }
.chat-container { display: flex; flex-direction: column; padding: 12px 10px 10px 10px; min-height: 100%; }
.message-wrapper { display: flex; align-items: flex-start; margin-bottom: 4px; animation: fadeIn 0.3s ease-out; }
.message-wrapper.user { justify-content: flex-end; }
.message-wrapper.assistant { justify-content: flex-start; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.message { max-width: 80%; padding: 6px 10px 8px; border-radius: 7.5px; position: relative; word-wrap: break-word; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); }
.user .message { background: #DCF8C6; border-top-right-radius: 0; margin-right: 8px; }
.user .message::after { content: ''; position: absolute; right: -8px; top: 0; border-width: 0 0 10px 8px; border-style: solid; border-color: transparent transparent transparent #DCF8C6; }
.assistant .message { background: #FFFFFF; border-top-left-radius: 0; margin-left: 8px; }
.assistant .message::before { content: ''; position: absolute; left: -8px; top: 0; border-width: 0 8px 10px 0; border-style: solid; border-color: transparent #FFFFFF transparent transparent; }
.copy-btn { background: none; border: none; cursor: pointer; padding: 4px 6px; opacity: 0.35; transition: opacity 0.2s, transform 0.1s; align-self: flex-start; margin-top: 4px; display: flex; align-items: center; justify-content: center; }
.copy-btn svg { width: 16px; height: 16px; fill: #54656f; }
.copy-btn:hover { opacity: 1; transform: scale(1.1); }
.copy-btn.copied { opacity: 1; }
.copy-btn.copied svg { fill: #25D366; }
.user .copy-btn { order: -1; }
.status { align-self: center; background: rgba(255,255,255,0.9); color: #667781; font-size: 12px; padding: 4px 12px; border-radius: 7px; margin: 8px 0; box-shadow: 0 1px 0.5px rgba(0,0,0,0.1); }
.text { color: #111b21; line-height: 1.45; }
.text code { background: rgba(0,0,0,0.06); padding: 1px 5px; border-radius: 4px; font-family: 'SF Mono', Monaco, 'Courier New', monospace; font-size: 13px; color: #c7254e; }
.text pre { background: #1e1e1e; color: #d4d4d4; padding: 10px 12px; border-radius: 8px; overflow-x: auto; margin: 6px 0; font-family: 'SF Mono', Monaco, 'Courier New', monospace; font-size: 12px; line-height: 1.4; }
.text pre code { background: none; padding: 0; color: inherit; font-size: inherit; }
.text strong { font-weight: 600; }
.text em { font-style: italic; }
'''

CHAT_JS = '''
const copyIcon = '<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>';
const checkIcon = '<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';

function copyText(btn, id) {
  const el = document.getElementById(id);
  if (!el) return;
  const text = el.innerText;
  const copyPromise = navigator.clipboard ?
    navigator.clipboard.writeText(text) :
    new Promise((resolve, reject) => {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy') ? resolve() : reject(); }
      catch(e) { reject(e); }
      document.body.removeChild(ta);
    });
  copyPromise.then(() => {
    btn.innerHTML = checkIcon; btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = copyIcon; btn.classList.remove('copied'); }, 1500);
  }).catch(() => {});
}

setTimeout(() => {
  const chat = document.getElementById('chat');
  const assistantMessages = document.querySelectorAll('.message-wrapper.assistant');
  // Only scroll if there are 2+ assistant responses
  if (assistantMessages.length >= 2 && document.body.scrollHeight > window.innerHeight) {
    if (chat) chat.scrollIntoView({ behavior: 'smooth', block: 'end' });
    window.scrollTo(0, document.body.scrollHeight);
  }
}, 50);

function toggleVoiceMenu() {
  const el = document.getElementById("voiceDropdown");
  if(el) el.classList.toggle("show");
}

window.onclick = function(event) {
  if (!event.target.matches('.voice-btn')) {
    const dropdowns = document.getElementsByClassName("dropdown-content");
    for (let i = 0; i < dropdowns.length; i++) {
      if (dropdowns[i].classList.contains('show')) dropdowns[i].classList.remove('show');
    }
  }
}
'''

CHAT_HTML_TEMPLATE = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{CHAT_CSS}</style></head>
<body>
{{pin_hint}}
<div id="chat" class="chat-container">{{messages}}</div>
<script>{CHAT_JS}</script>
</body>
</html>'''


class ChatOverlay(Gtk.Window):
    """Chat overlay using WebKit2."""
    
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self._setup_window()
        self._setup_webview()
        self._init_animation()
        self.show_all()
    
    def _setup_window(self) -> None:
        """Configure window properties."""
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        
        # Transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        
        # Position at right edge
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geometry = monitor.get_geometry()
        w, h = 340, 450
        x = geometry.x + geometry.width - w - 20
        y = geometry.y + (geometry.height - h) // 2
        self.move(x, y)
        self.set_default_size(w, h)
    
    def _setup_webview(self) -> None:
        """Setup WebKit2 webview."""
        self.webview = WebKit2.WebView()
        self.webview.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)
        self.webview.connect("decide-policy", self._on_policy_decision)
        self.add(self.webview)
    
    def _init_animation(self) -> None:
        """Initialize fade animation state."""
        self.opacity_value = 0.0
        self.fade_in_active = False
        self.fade_out_active = False
        self.fade_timer = None
        self.fade_callback = None
        self.start_fade_in()
    
    def start_fade_in(self) -> None:
        """Start fade-in animation."""
        self.fade_out_active = False
        self.fade_in_active = True
        self.opacity_value = 0.0
        self._cancel_fade_timer()
        self.fade_timer = GLib.timeout_add(16, self._fade_in_step)
    
    def _fade_in_step(self) -> bool:
        """Fade-in animation step."""
        self.opacity_value = min(1.0, self.opacity_value + 0.1)
        try:
            self.set_opacity(self.opacity_value)
        except Exception:
            pass
        if self.opacity_value >= 1.0:
            self.fade_in_active = False
            self.fade_timer = None
            return False
        return True
    
    def start_fade_out(self, callback: Optional[Callable] = None) -> None:
        """Start fade-out animation."""
        self.fade_in_active = False
        self.fade_out_active = True
        self.fade_callback = callback
        self._cancel_fade_timer()
        self.fade_timer = GLib.timeout_add(16, self._fade_out_step)
    
    def _fade_out_step(self) -> bool:
        """Fade-out animation step."""
        self.opacity_value = max(0.0, self.opacity_value - 0.1)
        try:
            self.set_opacity(self.opacity_value)
        except Exception:
            pass
        if self.opacity_value <= 0.0:
            self.fade_out_active = False
            self.fade_timer = None
            if self.fade_callback:
                self.fade_callback()
            return False
        return True
    
    def _cancel_fade_timer(self) -> None:
        """Cancel active fade timer."""
        if self.fade_timer:
            GLib.source_remove(self.fade_timer)
            self.fade_timer = None
    
    def update_content(self, messages: List[Dict[str, str]], status_text: Optional[str] = None,
                       is_pinned: bool = False, is_tts: bool = False) -> None:
        """Update chat content with markdown rendering."""
        html_messages = []
        svg_icon = '<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>'
        
        for idx, msg in enumerate(messages):
            role = msg["role"]
            rendered = self._render_markdown(msg["text"])
            msg_id = f"msg_{idx}"
            copy_btn = f'<button class="copy-btn" onclick="copyText(this, \'{msg_id}\')">{svg_icon}</button>'
            html_messages.append(
                f'<div class="message-wrapper {role}">'
                f'<div class="message"><div class="text" id="{msg_id}">{rendered}</div></div>'
                f'{copy_btn}'
                f'</div>'
            )
        
        if status_text:
            html_messages.append(f'<div class="message status">{status_text}</div>')
        
        # Build pin hint - simple text with gear icon
        pin_status = "F9: Unpin Chat" if is_pinned else "F9: Pin Chat"
        voice_status = "F10: Mute" if is_tts else "F10: Voice"
        pin_hint = f'<div class="pin-hint">{pin_status} | {voice_status} | <a href="settings://open" class="settings-link">⚙️</a></div>'
        
        html = CHAT_HTML_TEMPLATE.replace("{messages}", "\n".join(html_messages))
        html = html.replace("{pin_hint}", pin_hint)
        self.webview.load_html(html, None)
    
    def _on_policy_decision(self, webview, decision, decision_type) -> bool:
        """Handle settings:// URI navigation."""
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            nav = decision.get_navigation_action()
            uri = nav.get_request().get_uri()
            if uri and uri.startswith("settings://"):
                GLib.idle_add(SettingsDialog.show)
                decision.ignore()
                return True
        return False
    
    @staticmethod
    def _render_markdown(text: str) -> str:
        """Convert simple markdown to HTML."""
        import html as html_lib
        text = html_lib.escape(text)
        
        # Code blocks
        text = re.sub(r'```(?:\w+)?\n?(.*?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
        # Inline code
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        # Italic
        text = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'<em>\1</em>', text)
        text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<em>\1</em>', text)
        # Line breaks
        text = text.replace('\n', '<br>')
        
        return text
    
    def close(self) -> None:
        """Clean up and destroy."""
        self._cancel_fade_timer()
        self.destroy()


# ============================================================================
# SECTION 9: SETTINGS DIALOG
# ============================================================================
class SettingsDialog:
    """GTK Settings dialog for voice and hotkey configuration."""
    
    _instance: Optional[Gtk.Window] = None
    
    @classmethod
    def show(cls) -> None:
        """Show settings dialog (singleton)."""
        if cls._instance and cls._instance.get_visible():
            cls._instance.present()
            return
        
        cls._instance = cls._create_dialog()
        cls._instance.show_all()
    
    @classmethod
    def _create_dialog(cls) -> Gtk.Window:
        """Create the settings dialog window."""
        dialog = Gtk.Window(title="LinuxWhisper Settings")
        dialog.set_default_size(350, 300)
        dialog.set_resizable(False)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_keep_above(True)
        
        # Main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        
        # --- Voice Section ---
        voice_label = Gtk.Label(label="TTS Voice")
        voice_label.set_halign(Gtk.Align.START)
        voice_label.set_markup("<b>TTS Voice</b>")
        vbox.pack_start(voice_label, False, False, 0)
        
        voice_combo = Gtk.ComboBoxText()
        for voice in CFG.TTS_VOICES:
            voice_combo.append_text(voice.title())
        voice_combo.set_active(CFG.TTS_VOICES.index(STATE.tts_voice) if STATE.tts_voice in CFG.TTS_VOICES else 0)
        voice_combo.connect("changed", cls._on_voice_changed)
        vbox.pack_start(voice_combo, False, False, 0)
        
        # --- Hotkeys Section ---
        hotkey_label = Gtk.Label()
        hotkey_label.set_halign(Gtk.Align.START)
        hotkey_label.set_markup("<b>Hotkeys (Click to change)</b>")
        vbox.pack_start(hotkey_label, False, False, 10)
        
        hotkey_grid = Gtk.Grid()
        hotkey_grid.set_column_spacing(15)
        hotkey_grid.set_row_spacing(8)
        
        hotkeys = [
            ("Dictation:", "dictation"),
            ("AI Chat:", "ai"),
            ("Rewrite:", "ai_rewrite"),
            ("Vision:", "vision"),
            ("Pin Chat:", "pin"),
            ("TTS Toggle:", "tts"),
        ]
        
        cls.key_buttons = {}
        
        for i, (name, action) in enumerate(hotkeys):
            name_label = Gtk.Label(label=name)
            name_label.set_halign(Gtk.Align.START)
            
            # Button showing current key
            current_key = KeyboardHandler.get_key_string(action)
            btn = Gtk.Button(label=current_key)
            btn.connect("clicked", cls._on_key_click, action)
            cls.key_buttons[action] = btn
            
            hotkey_grid.attach(name_label, 0, i, 1, 1)
            hotkey_grid.attach(btn, 1, i, 1, 1)
        
        vbox.pack_start(hotkey_grid, False, False, 0)
        
        # Info label
        info_label = Gtk.Label()
        info_label.set_markup("<small><i>Click a button then press any key to rebind.</i></small>")
        info_label.set_halign(Gtk.Align.START)
        vbox.pack_start(info_label, False, False, 10)
        
        # --- Close Button ---
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda w: dialog.destroy())
        vbox.pack_end(close_btn, False, False, 0)
        
        dialog.add(vbox)
        dialog.connect("destroy", lambda w: setattr(cls, '_instance', None))
        
        return dialog
    
    @staticmethod
    def _on_voice_changed(combo: Gtk.ComboBoxText) -> None:
        """Handle voice selection change."""
        active = combo.get_active()
        if 0 <= active < len(CFG.TTS_VOICES):
            voice = CFG.TTS_VOICES[active]
            STATE.tts_voice = voice
            ChatManager.refresh_overlay()
            
            # Save config
            config = CFG.load()
            config["voice"] = voice
            CFG.save(config)

    @classmethod
    def _on_key_click(cls, btn: Gtk.Button, action: str) -> None:
        """Handle key binding button click."""
        btn.set_label("Press any key...")
        btn.set_sensitive(False)
        
        # Start capture thread
        threading.Thread(target=cls._capture_key, args=(btn, action), daemon=True).start()

    @classmethod
    def _capture_key(cls, btn: Gtk.Button, action: str) -> None:
        """Capture next key press for binding."""
        captured_key = None
        
        def on_press(key):
            nonlocal captured_key
            captured_key = key
            return False  # Stop listener
            
        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
            
        if captured_key:
            key_str = KeyboardHandler.serialize_key(captured_key)
            
            # Update state
            STATE.custom_hotkeys[action] = key_str
            
            # Update UI on main thread
            GLib.idle_add(lambda: cls._update_btn(btn, key_str))
            
            # Save config
            config = CFG.load()
            config["hotkeys"] = STATE.custom_hotkeys
            CFG.save(config)

    @staticmethod
    def _update_btn(btn: Gtk.Button, text: str) -> None:
        """Update button text and sensitivity safely."""
        btn.set_label(text)
        btn.set_sensitive(True)


# ============================================================================
# SECTION 10: SYSTEM TRAY
# ============================================================================
class TrayManager:
    """System tray (AppIndicator) management."""
    
    @staticmethod
    def start() -> None:
        """Initialize and start system tray."""
        STATE.indicator = AppIndicator.Indicator.new(
            "linuxwhisper",
            "emblem-favorite",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        STATE.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        STATE.indicator.set_title("LinuxWhisper")
        TrayManager.update_menu()
        Gtk.main()
    
    @staticmethod
    def update_menu() -> None:
        """Rebuild and update tray menu."""
        if not STATE.indicator:
            return
        STATE.gtk_menu = TrayManager._build_menu()
        STATE.indicator.set_menu(STATE.gtk_menu)
    
    @staticmethod
    def _build_menu() -> Gtk.Menu:
        """Build GTK menu for tray."""
        menu = Gtk.Menu()
        
        # History items
        if STATE.answer_history:
            for item in STATE.answer_history[:CFG.ANSWER_HISTORY_LIMIT]:
                preview = item["text"][:50].replace("\n", " ")
                if len(item["text"]) > 50:
                    preview += "..."
                label = f"[{item['timestamp']}] {preview}"
                menu_item = Gtk.MenuItem(label=label)
                menu_item.connect("activate", TrayManager._make_history_callback(item))
                menu.append(menu_item)
            menu.append(Gtk.SeparatorMenuItem())
        else:
            empty = Gtk.MenuItem(label="(No History)")
            empty.set_sensitive(False)
            menu.append(empty)
            menu.append(Gtk.SeparatorMenuItem())
        
        # Clear history
        clear = Gtk.MenuItem(label="Clear History")
        clear.connect("activate", lambda w: HistoryManager.clear_all())
        menu.append(clear)
        
        # Settings
        settings_item = Gtk.MenuItem(label="Settings")
        settings_item.connect("activate", lambda w: SettingsDialog.show())
        menu.append(settings_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", TrayManager._quit)
        menu.append(quit_item)
        
        menu.show_all()
        return menu
    
    @staticmethod
    def _make_history_callback(item: Dict[str, str]) -> Callable:
        """Create callback for history item click."""
        def callback(widget):
            # Remove prefix labels like [Dictation]
            clean = re.sub(r"^\[.*?\]\s*", "", item["text"])
            ClipboardService.paste_text(clean)
        return callback
    
    @staticmethod
    def _quit(widget) -> None:
        """Quit application."""
        Gtk.main_quit()
        os._exit(0)


# ============================================================================
# SECTION 10: MODE HANDLER
# ============================================================================
class ModeHandler:
    """Unified handler for all recording modes."""
    
    @staticmethod
    def process(mode: str, transcribed_text: str) -> None:
        """Route to appropriate handler based on mode."""
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


# ============================================================================
# SECTION 11: KEYBOARD HANDLER
# ============================================================================
class KeyboardHandler:
    """Global keyboard listener with dynamic key mappings."""
    
    # Default mappings as fallback
    DEFAULTS: Dict[str, str] = {
        "dictation": "Key.f3",
        "ai": "Key.f4",
        "ai_rewrite": "Key.f7",
        "vision": "Key.f8",
        "pin": "Key.f9",
        "tts": "Key.f10",
    }
    
    @classmethod
    def get_key_string(cls, action: str) -> str:
        """Get configured key string for action."""
        return STATE.custom_hotkeys.get(action, cls.DEFAULTS[action])

    @staticmethod
    def serialize_key(key: Any) -> str:
        """Convert pynput Key object to string storage format."""
        if hasattr(key, 'name'):
            return f"Key.{key.name}"
        if hasattr(key, 'char') and key.char:
            return key.char
        return str(key)
        
    @classmethod
    def check_key(cls, key: Any, action: str) -> bool:
        """Check if pressed key matches configured action."""
        target_str = cls.get_key_string(action)
        pressed_str = cls.serialize_key(key)
        
        # match precise string
        if pressed_str == target_str:
            return True
            
        # fallback for media keys if they match default F-keys
        # (Only applies if user hasn't rebound them)
        if target_str == cls.DEFAULTS.get(action):
             # Backup hardcoded checks for Apple/Media keys
             if action == "dictation" and getattr(key, 'vk', None) == 269025098: return True
             if action == "ai" and getattr(key, 'vk', None) == 269025099: return True
             if action == "ai_rewrite" and key == keyboard.Key.media_previous: return True
             if action == "vision" and key == keyboard.Key.media_play_pause: return True
             if action == "pin" and (key == keyboard.Key.media_next or getattr(key, 'vk', None) == 269025047): return True
             if action == "tts" and key == keyboard.Key.media_volume_mute: return True
             
        return False
    
    @classmethod
    def get_mode_for_key(cls, key: Any) -> Optional[str]:
        """Get mode name for a pressed key, if any."""
        for mode in ["dictation", "ai", "ai_rewrite", "vision"]:
            if cls.check_key(key, mode):
                return mode
        return None
    
    @classmethod
    def on_press(cls, key) -> None:
        """Handle key press events."""
        if STATE.recording:
            return
        
        # F9: Toggle pin (non-recording action)
        if cls.check_key(key, "pin"):
            ChatManager.toggle_pin()
            return
        
        # F10: Toggle TTS (non-recording action)
        if cls.check_key(key, "tts"):
            TTSService.toggle()
            return
        
        # Check for recording mode keys
        mode = cls.get_mode_for_key(key)
        if mode:
            STATE.current_mode = mode
            
            # For rewrite mode, copy selected text first
            if mode == "ai_rewrite":
                subprocess.run(["xdotool", "key", "ctrl+c"])
                time.sleep(0.1)
            
            OverlayManager.show(mode)
            AudioService.start_recording()
    
    @classmethod
    def on_release(cls, key) -> None:
        """Handle key release events."""
        if not STATE.recording:
            return
        
        # Check if released key matches current mode
        mode = cls.get_mode_for_key(key)
        if mode and mode == STATE.current_mode:
            OverlayManager.hide()
            audio_data = AudioService.stop_recording()
            
            if audio_data is not None:
                transcribed = AudioService.transcribe(audio_data)
                if transcribed:
                    ModeHandler.process(mode, transcribed)
    
    @classmethod
    def run(cls) -> None:
        """Start keyboard listener in current thread."""
        with keyboard.Listener(on_press=cls.on_press, on_release=cls.on_release) as listener:
            listener.join()


# ============================================================================
# SECTION 12: MAIN ENTRY POINT
# ============================================================================
def main() -> None:
    """Application entry point."""
    print("🚀 LinuxWhisper is running.")
    print(" 1. F3            : Live dictation at cursor position (Whisper V3)")
    print(" 2. F4            : Empathic AI question (Groq Moonshot)")
    print(" 3. F7 (Previous) : Smart Rewrite - Highlight text & speak to edit")
    print(" 4. F8 (Play)     : Empathic Vision / Screenshot (Groq Llama 4)")
    print(" 5. F9 (Next)     : Toggle Chat Overlay Pin Mode")
    print(" 6. F10           : Toggle TTS (Read AI responses aloud)")
    print("\n📌 System tray icon active")
    
    # Start keyboard listener in background thread
    keyboard_thread = threading.Thread(target=KeyboardHandler.run, daemon=True)
    keyboard_thread.start()
    
    # Run GTK main loop (blocks)
    TrayManager.start()


if __name__ == "__main__":
    main()
