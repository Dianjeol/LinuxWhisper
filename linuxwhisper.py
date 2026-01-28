#!/usr/bin/env python3
"""
LinuxWhisper - Voice Assistant for Linux
=========================================

A voice-to-text and AI assistant tool that integrates with Groq APIs
for transcription, chat completion, vision analysis, and text-to-speech.

ARCHITECTURE OVERVIEW
---------------------
Section 1: Imports
Section 2: Configuration (Config dataclass & SettingsManager)
Section 3: State Management (AppState dataclass)
Section 4: Services (AudioService, AIService, TTSService, ClipboardService)
Section 5: Managers (HistoryManager, ChatManager)
Section 6: UI Components (GtkOverlay, ChatOverlay)
Section 7: Settings Dialog (SettingsDialog)
Section 8: System Tray (TrayManager)
Section 9: Keyboard Handler (KeyboardHandler)
Section 10: Main Entry Point

CONFIGURATION
-------------
Persistent settings are stored in ~/.config/linuxwhisper/settings.json.
If missing, defaults (F3-F10) are used.

HOTKEYS (Default)
-----------------
F3:  Dictation (Speech-to-Text)
F4:  AI Chat (Voice Question -> Answer)
F7:  Rewrite (Select Text -> Speak Instructions)
F8:  Vision (Screenshot -> Analysis)
F9:  Pin/Unpin Chat
F10: Toggle TTS
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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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
# SECTION 2: CONFIGURATION & SETTINGS
# ============================================================================
@dataclass(frozen=True)
class Config:
    """Immutable application constants."""
    SAMPLE_RATE: int = 44100
    MAX_TOKENS: int = 32000
    ANSWER_HISTORY_LIMIT: int = 15
    CHAT_MESSAGE_LIMIT: int = 20
    CHAT_AUTO_HIDE_SEC: int = 5
    
    MODEL_CHAT: str = "moonshotai/kimi-k2-instruct"
    MODEL_VISION: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    MODEL_WHISPER: str = "whisper-large-v3"
    MODEL_TTS: str = "canopylabs/orpheus-v1-english"
    
    TTS_VOICES: Tuple[str, ...] = ("diana", "hannah", "autumn", "austin", "daniel", "troy")
    TTS_DEFAULT_VOICE: str = "diana"
    TTS_MAX_CHARS: int = 4000
    
    TEMP_SCREEN_PATH: str = "/tmp/temp_screen.png"
    TEMP_TTS_PATH: str = "/tmp/linuxwhisper_tts.wav"
    
    SYSTEM_PROMPT: str = (
        "Act as a compassionate assistant. Base your reasoning on the principles of "
        "Nonviolent Communication and A Course in Miracles. Apply these frameworks as "
        "your underlying logic without explicitly naming them or forcing them. Let your "
        "output be grounded, clear, and highly concise. Return ONLY the direct response."
    )
    
    MODES: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "dictation":  {"icon": "🎙️", "text": "Listening...",    "bg": "#1a1a2e", "fg": "#00d4ff"},
        "ai":         {"icon": "🤖", "text": "AI Listening...", "bg": "#1a1a2e", "fg": "#a855f7"},
        "ai_rewrite": {"icon": "✍️", "text": "Rewrite Mode...", "bg": "#1a1a2e", "fg": "#22c55e"},
        "vision":     {"icon": "📸", "text": "Vision Mode...",  "bg": "#1a1a2e", "fg": "#f59e0b"},
    })

CFG = Config()

class SettingsManager:
    """Manages loading/saving of persistent user settings."""
    
    CONFIG_DIR = Path.home() / ".config" / "linuxwhisper"
    CONFIG_FILE = CONFIG_DIR / "settings.json"
    
    DEFAULT_SETTINGS = {
        "dictation_key": "Key.f3",
        "ai_chat_key": "Key.f4",
        "rewrite_key": "Key.f7",
        "vision_key": "Key.f8",
        "pin_chat_key": "Key.f9",
        "tts_key": "Key.f10",
        "tts_voice": "diana"
    }
    
    _settings: Dict[str, str] = {}
    
    @classmethod
    def load(cls) -> None:
        """Load settings from JSON, falling back to defaults."""
        cls._settings = cls.DEFAULT_SETTINGS.copy()
        
        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE, "r") as f:
                    loaded = json.load(f)
                    cls._settings.update(loaded)
            except Exception as e:
                print(f"⚠️ Failed to load settings: {e}")
        else:
            cls.save()  # Create default file
            
    @classmethod
    def save(cls) -> None:
        """Save current settings to JSON."""
        try:
            cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(cls.CONFIG_FILE, "w") as f:
                json.dump(cls._settings, f, indent=4)
        except Exception as e:
            print(f"❌ Failed to save settings: {e}")
            
    @classmethod
    def get(cls, key: str) -> str:
        """Get a setting value."""
        return cls._settings.get(key, cls.DEFAULT_SETTINGS.get(key, ""))
    
    @classmethod
    def set(cls, key: str, value: str) -> None:
        """Set a setting value and save."""
        cls._settings[key] = value
        cls.save()

    @classmethod
    def get_voice(cls) -> str:
        return cls.get("tts_voice")

    @classmethod
    def get_key(cls, name: str) -> Any:
        """Parse key string (e.g., 'Key.f3' or 'a') into pynput Key object."""
        val = cls.get(name)
        if val.startswith("Key."):
            try:
                attr = val.split(".")[1]
                return getattr(keyboard.Key, attr)
            except AttributeError:
                return keyboard.Key.f1 # Fallback
        
        # Single char
        if len(val) == 1:
            return keyboard.KeyCode.from_char(val)
        
        # Try to find special key by name if mismatch
        try:
             return getattr(keyboard.Key, val.lower())
        except AttributeError:
            pass
            
        return None

# Load settings immediately
SettingsManager.load()


# ============================================================================
# SECTION 3: STATE MANAGEMENT
# ============================================================================
@dataclass
class AppState:
    """Mutable application state."""
    # Recording
    recording: bool = False
    current_mode: Optional[str] = None
    audio_buffer: List[np.ndarray] = field(default_factory=list)
    stream: Optional[sd.InputStream] = None
    viz_queue: queue.Queue = field(default_factory=queue.Queue)
    
    # UI Windows
    overlay_window: Optional[Any] = None
    chat_overlay_window: Optional[Any] = None
    
    # Chat State
    chat_messages: List[Dict[str, str]] = field(default_factory=list)
    chat_pinned: bool = False
    chat_hide_timer: Optional[int] = None
    
    # History
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    answer_history: List[Dict[str, str]] = field(default_factory=list)
    
    # TTS
    tts_enabled: bool = True
    
    # System Tray
    indicator: Optional[AppIndicator.Indicator] = None
    gtk_menu: Optional[Gtk.Menu] = None
    
    @property
    def tts_voice(self) -> str:
        return SettingsManager.get_voice()
    
    @tts_voice.setter
    def tts_voice(self, v: str) -> None:
        SettingsManager.set("tts_voice", v)

STATE = AppState()


# ============================================================================
# SECTION 4: API & UTILS
# ============================================================================
def _init_groq_client() -> Groq:
    """Initialize Groq API client."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("❌ Error: GROQ_API_KEY missing.")
        sys.exit(1)
    return Groq(api_key=api_key)

GROQ_CLIENT = _init_groq_client()

def safe_execute(operation: str) -> Callable:
    """Decorator for error handling."""
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
    """Schedule execution on GTK main thread."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        GLib.idle_add(lambda: func(*args, **kwargs))
    return wrapper


# ============================================================================
# SECTION 4: SERVICES
# ============================================================================
class AudioService:
    @staticmethod
    def audio_callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if not STATE.recording: return
        data_copy = indata.copy()
        STATE.audio_buffer.append(data_copy)
        try:
            if STATE.viz_queue.qsize() < 5:
                STATE.viz_queue.put_nowait(data_copy[:, 0][::10])
        except Exception: pass
    
    @staticmethod
    def start_recording() -> None:
        STATE.audio_buffer = []
        while not STATE.viz_queue.empty():
            try: STATE.viz_queue.get_nowait()
            except queue.Empty: break
        STATE.stream = sd.InputStream(samplerate=CFG.SAMPLE_RATE, channels=1, dtype='float32', callback=AudioService.audio_callback)
        STATE.stream.start()
        STATE.recording = True
    
    @staticmethod
    def stop_recording() -> Optional[np.ndarray]:
        STATE.recording = False
        if STATE.stream:
            STATE.stream.stop()
            STATE.stream.close()
            STATE.stream = None
        return np.concatenate(STATE.audio_buffer, axis=0) if STATE.audio_buffer else None
    
    @staticmethod
    @safe_execute("Transcription")
    def transcribe(audio_data: np.ndarray) -> Optional[str]:
        wav_buffer = io.BytesIO()
        wav_buffer.name = "audio.wav"
        wav_write(wav_buffer, CFG.SAMPLE_RATE, audio_data)
        wav_buffer.seek(0)
        return GROQ_CLIENT.audio.transcriptions.create(model=CFG.MODEL_WHISPER, file=wav_buffer).text.strip()

class AIService:
    @staticmethod
    def build_messages(user_content: str) -> List[Dict[str, Any]]:
        messages = [{"role": "system", "content": CFG.SYSTEM_PROMPT}]
        messages.extend(STATE.conversation_history)
        messages.append({"role": "user", "content": user_content})
        return messages
    
    @staticmethod
    @safe_execute("AI Chat")
    def chat(prompt: str) -> Optional[str]:
        return GROQ_CLIENT.chat.completions.create(model=CFG.MODEL_CHAT, messages=AIService.build_messages(prompt)).choices[0].message.content

    @staticmethod
    @safe_execute("AI Vision")
    def vision(prompt: str, image_base64: str) -> Optional[str]:
        messages = AIService.build_messages(prompt)
        messages[-1] = {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}]}
        return GROQ_CLIENT.chat.completions.create(model=CFG.MODEL_VISION, messages=messages).choices[0].message.content

class TTSService:
    @staticmethod
    def speak(text: str) -> None:
        if not STATE.tts_enabled or not text: return
        def _speak():
            try:
                resp = GROQ_CLIENT.audio.speech.create(model=CFG.MODEL_TTS, voice=STATE.tts_voice, input=text[:CFG.TTS_MAX_CHARS], response_format="wav")
                resp.write_to_file(CFG.TEMP_TTS_PATH)
                subprocess.run(["aplay", "-q", CFG.TEMP_TTS_PATH], capture_output=True)
            except Exception as e: print(f"❌ TTS Error: {e}")
        threading.Thread(target=_speak, daemon=True).start()
    
    @staticmethod
    def toggle() -> None:
        STATE.tts_enabled = not STATE.tts_enabled
        ChatManager.refresh_overlay()

class ClipboardService:
    @staticmethod
    def type_text(text: str) -> None:
        if not text: return
        try: original = pyperclip.paste()
        except: original = None
        clean = f" {text.strip()}" if not text.startswith(" ") else text
        pyperclip.copy(clean)
        subprocess.run(["xdotool", "key", "ctrl+v"])
        time.sleep(0.1)
        if original:
            try: pyperclip.copy(original)
            except: pass

    @staticmethod
    def copy_selected() -> str:
        subprocess.run(["xdotool", "key", "ctrl+c"])
        time.sleep(0.1)
        return pyperclip.paste().strip()
    
    @staticmethod
    def paste_text(text: str) -> None:
        pyperclip.copy(text)
        subprocess.run(["xdotool", "key", "ctrl+v"])

class ImageService:
    @staticmethod
    @safe_execute("Screenshot")
    def take_screenshot() -> Optional[str]:
        subprocess.run(["gnome-screenshot", "-f", CFG.TEMP_SCREEN_PATH])
        with open(CFG.TEMP_SCREEN_PATH, "rb") as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
        os.remove(CFG.TEMP_SCREEN_PATH)
        return encoded


# ============================================================================
# SECTION 5: MANAGERS
# ============================================================================
class HistoryManager:
    @staticmethod
    def add_message(role: str, content: str) -> None:
        STATE.conversation_history.append({"role": role, "content": content})
        while sum(len(m["content"])//4 for m in STATE.conversation_history) > CFG.MAX_TOKENS and STATE.conversation_history:
            STATE.conversation_history.pop(0)

    @staticmethod
    def add_answer(text: str) -> None:
        STATE.answer_history.insert(0, {"text": text, "timestamp": time.strftime("%H:%M")})
        if len(STATE.answer_history) > CFG.ANSWER_HISTORY_LIMIT:
            STATE.answer_history = STATE.answer_history[:CFG.ANSWER_HISTORY_LIMIT]
        TrayManager.update_menu()
    
    @staticmethod
    def clear_all() -> None:
        STATE.answer_history = []
        STATE.conversation_history = []
        STATE.chat_messages = []
        TrayManager.update_menu()
        ChatManager.refresh_overlay()

class ChatManager:
    @staticmethod
    def add_message(role: str, text: str) -> None:
        STATE.chat_messages.append({"role": role, "text": text})
        if len(STATE.chat_messages) > CFG.CHAT_MESSAGE_LIMIT:
            STATE.chat_messages = STATE.chat_messages[-CFG.CHAT_MESSAGE_LIMIT:]
        ChatManager.refresh_overlay()
    
    @staticmethod
    def toggle_pin() -> None:
        STATE.chat_pinned = not STATE.chat_pinned
        if not STATE.chat_pinned and STATE.chat_overlay_window:
            ChatManager._cancel_timer()
            STATE.chat_overlay_window.start_fade_out(callback=ChatManager._destroy)
        else:
            ChatManager.refresh_overlay()
    
    @staticmethod
    @run_on_main_thread
    def refresh_overlay(status_text: Optional[str] = None) -> None:
        ChatManager._cancel_timer()
        if not STATE.chat_overlay_window:
            STATE.chat_overlay_window = ChatOverlay()
        elif STATE.chat_overlay_window.fade_out_active:
            STATE.chat_overlay_window.start_fade_in()
        
        STATE.chat_overlay_window.update_content(STATE.chat_messages, status_text, is_pinned=STATE.chat_pinned, is_tts=STATE.tts_enabled)
        if not STATE.chat_pinned:
            STATE.chat_hide_timer = GLib.timeout_add_seconds(CFG.CHAT_AUTO_HIDE_SEC, ChatManager._auto_hide)
    
    @staticmethod
    def _auto_hide() -> bool:
        STATE.chat_hide_timer = None
        if not STATE.chat_pinned and STATE.chat_overlay_window:
            STATE.chat_overlay_window.start_fade_out(callback=ChatManager._destroy)
        return False
    
    @staticmethod
    def _cancel_timer() -> None:
        if STATE.chat_hide_timer:
            GLib.source_remove(STATE.chat_hide_timer)
            STATE.chat_hide_timer = None
    
    @staticmethod
    def _destroy() -> None:
        if STATE.chat_overlay_window:
            STATE.chat_overlay_window.close()
            STATE.chat_overlay_window = None


# ============================================================================
# SECTION 6: UI COMPONENTS
# ============================================================================
class GtkOverlay(Gtk.Window):
    def __init__(self, mode: str):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.mode = mode
        self.config = CFG.MODES.get(mode, CFG.MODES["dictation"])
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_keep_above(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited(): self.set_visual(visual)
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        self.move((geo.width - 220) // 2, geo.height - 140)
        self.set_default_size(220, 60)
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self._on_draw)
        self.add(self.drawing_area)
        self.timeout_id = GLib.timeout_add(40, lambda: (self.drawing_area.queue_draw(), True)[1])
        self.show_all()
    
    def _on_draw(self, widget, cr):
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        bg = self._hex(self.config["bg"])
        fg = self._hex(self.config["fg"])
        
        # Draw BG
        cr.new_sub_path()
        cr.arc(w-15, 15, 15, -math.pi/2, 0); cr.arc(w-15, h-15, 15, 0, math.pi/2)
        cr.arc(15, h-15, 15, math.pi/2, math.pi); cr.arc(15, 15, 15, math.pi, 3*math.pi/2)
        cr.close_path()
        cr.set_source_rgba(*bg, 0.92); cr.fill()
        
        # Icon & Text
        cr.set_source_rgb(*fg); cr.select_font_face("Ubuntu", 0, 0); cr.set_font_size(20)
        ext = cr.text_extents(self.config["icon"])
        cr.move_to(30 - ext.width/2, h/2 + ext.height/2); cr.show_text(self.config["icon"])
        
        cr.set_font_size(10); cr.select_font_face("Ubuntu", 0, 1)
        ext = cr.text_extents(self.config["text"])
        cr.move_to(110 - ext.width/2, 20); cr.show_text(self.config["text"])
        
        # Waveform
        self._waveform(cr, 60, 210, 45, fg)

    def _waveform(self, cr, x1, x2, cy, color):
        data = None
        while not STATE.viz_queue.empty():
            try: data = STATE.viz_queue.get_nowait()
            except: break
        cr.set_source_rgb(*color); cr.set_line_width(3); cr.set_line_cap(1)
        if data is not None and len(data) > 0:
            width = x2 - x1; num = 30; step = max(1, len(data)//num)
            for i in range(num):
                idx = i * step
                if idx >= len(data): break
                h = max(1, min(15, abs(data[idx:idx+step]).max() * 60))
                x = x1 + i * (width/num)
                cr.move_to(x, cy-h); cr.line_to(x, cy+h); cr.stroke()
        else:
            cr.set_source_rgb(0.33, 0.33, 0.33); cr.set_line_width(2)
            cr.move_to(x1, cy); cr.line_to(x2, cy); cr.stroke()

    def _hex(self, s): return tuple(int(s.lstrip('#')[i:i+2], 16)/255.0 for i in (0,2,4))
    def close(self):
        if self.timeout_id: GLib.source_remove(self.timeout_id)
        self.destroy()

class OverlayManager:
    @staticmethod
    @run_on_main_thread
    def show(mode: str):
        if STATE.overlay_window: STATE.overlay_window.close()
        STATE.overlay_window = GtkOverlay(mode)
    @staticmethod
    @run_on_main_thread
    def hide():
        if STATE.overlay_window: STATE.overlay_window.close(); STATE.overlay_window = None

CHAT_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  height: 100%; background: #ECE5DD;
  font-family: system-ui, -apple-system, sans-serif; font-size: 14px; overflow-x: hidden;
  background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4cfc4' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
}
.pin-hint {
  position: sticky; top: 0; background: #D1D9E6; color: #111b21;
  text-align: center; padding: 8px 12px; font-size: 12px; font-weight: 500;
  z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  border-radius: 0 0 12px 12px; margin: 0 20px 10px 20px;
}
.settings-link { text-decoration: none; font-size: 14px; cursor: pointer; }
.chat-container { display: flex; flex-direction: column; padding: 12px 10px; min-height: 100%; }
.message-wrapper { display: flex; margin-bottom: 4px; animation: fadeIn 0.3s ease-out; }
.message-wrapper.user { justify-content: flex-end; }
.message-wrapper.assistant { justify-content: flex-start; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.message { max-width: 80%; padding: 6px 10px 8px; border-radius: 7.5px; position: relative; word-wrap: break-word; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); }
.user .message { background: #DCF8C6; border-top-right-radius: 0; margin-right: 8px; }
.user .message::after { content: ''; position: absolute; right: -8px; top: 0; border-width: 0 0 10px 8px; border-style: solid; border-color: transparent transparent transparent #DCF8C6; }
.assistant .message { background: #FFFFFF; border-top-left-radius: 0; margin-left: 8px; }
.assistant .message::before { content: ''; position: absolute; left: -8px; top: 0; border-width: 0 8px 10px 0; border-style: solid; border-color: transparent #FFFFFF transparent transparent; }
.text { color: #111b21; line-height: 1.45; }
.text code { background: rgba(0,0,0,0.06); padding: 1px 5px; border-radius: 4px; font-family: monospace; color: #c7254e; }
.text pre { background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 8px; overflow-x: auto; margin: 6px 0; font-family: monospace; }
"""
CHAT_HTML = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CHAT_CSS}</style></head><body>{{pin_hint}}<div id='chat' class='chat-container'>{{messages}}</div><script>setTimeout(() => {{ const chat = document.getElementById('chat'); const am = document.querySelectorAll('.message-wrapper.assistant'); if (am.length >= 2 && document.body.scrollHeight > window.innerHeight) {{ chat.scrollIntoView({{behavior:'smooth', block:'end'}}); window.scrollTo(0, document.body.scrollHeight); }} }}, 50);</script></body></html>"

class ChatOverlay(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False); self.set_keep_above(True)
        self.set_skip_taskbar_hint(True); self.set_skip_pager_hint(True)
        self.set_app_paintable(True); self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        
        screen = self.get_screen(); visual = screen.get_rgba_visual()
        if visual and screen.is_composited(): self.set_visual(visual)
        
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        self.move(geo.x + geo.width - 360, geo.y + (geo.height - 450) // 2)
        self.set_default_size(340, 450)
        
        self.webview = WebKit2.WebView()
        self.webview.set_background_color(Gdk.RGBA(0,0,0,0))
        self.webview.connect("decide-policy", self._on_policy)
        self.add(self.webview)
        
        self.opacity = 0.0; self.fade_timer = None; self.on_fade_end = None
        self.start_fade_in()
        self.show_all()

    def start_fade_in(self):
        self._stop_fade(); self.fade_in = True
        self.fade_timer = GLib.timeout_add(16, self._step_fade)

    def start_fade_out(self, callback=None):
        self._stop_fade(); self.fade_in = False; self.on_fade_end = callback
        self.fade_timer = GLib.timeout_add(16, self._step_fade)

    def _step_fade(self):
        self.opacity += 0.1 if self.fade_in else -0.1
        self.set_opacity(max(0.0, min(1.0, self.opacity)))
        if (self.fade_in and self.opacity >= 1) or (not self.fade_in and self.opacity <= 0):
            if not self.fade_in and self.on_fade_end: self.on_fade_end()
            self.fade_timer = None; return False
        return True

    def _stop_fade(self):
        if self.fade_timer: GLib.source_remove(self.fade_timer); self.fade_timer = None

    def update_content(self, messages, status, is_pinned, is_tts):
        html_msgs = []
        for m in messages:
            html_msgs.append(f"<div class='message-wrapper {m['role']}'><div class='message'><div class='text'>{self._md(m['text'])}</div></div></div>")
        if status: html_msgs.append(f"<div class='message status'>{status}</div>")
        
        pin_key = SettingsManager.get("pin_chat_key").replace("Key.", "").upper()
        tts_key = SettingsManager.get("tts_key").replace("Key.", "").upper()
        
        pin_lbl = f"{pin_key}: Unpin Chat" if is_pinned else f"{pin_key}: Pin Chat"
        voice_lbl = f"{tts_key}: Mute" if is_tts else f"{tts_key}: Voice"
        
        hint = f"<div class='pin-hint'>{pin_lbl} | {voice_lbl} | <a href='settings://open' class='settings-link'>⚙️</a></div>"
        self.webview.load_html(CHAT_HTML.replace("{messages}", "".join(html_msgs)).replace("{pin_hint}", hint), None)

    def _on_policy(self, wv, dec, type):
        if type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = dec.get_navigation_action().get_request().get_uri()
            if uri and uri.startswith("settings://"):
                GLib.idle_add(SettingsDialog.show); dec.ignore(); return True
        return False

    def _md(self, t):
        import html
        t = html.escape(t).replace("\n", "<br>")
        t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
        t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
        return t

    def close(self): self._stop_fade(); self.destroy()

# ============================================================================
# SECTION 7: SETTINGS DIALOG (DYNAMIC)
# ============================================================================
class SettingsDialog:
    _instance: Optional[Gtk.Window] = None
    
    @classmethod
    def show(cls):
        if cls._instance and cls._instance.get_visible():
            cls._instance.present(); return
        cls._instance = cls._create()
        cls._instance.show_all()
    
    @classmethod
    def _create(cls):
        win = Gtk.Window(title="LinuxWhisper Settings")
        win.set_default_size(400, 450); win.set_resizable(False)
        win.set_position(Gtk.WindowPosition.CENTER); win.set_keep_above(True)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_top(20); vbox.set_margin_bottom(20)
        vbox.set_margin_start(20); vbox.set_margin_end(20)
        
        # Voice Config
        lbl = Gtk.Label(); lbl.set_markup("<b>TTS Voice</b>"); lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl, False, False, 0)
        
        combo = Gtk.ComboBoxText()
        for v in CFG.TTS_VOICES: combo.append_text(v.title())
        curr = STATE.tts_voice
        combo.set_active(CFG.TTS_VOICES.index(curr) if curr in CFG.TTS_VOICES else 0)
        combo.connect("changed", lambda c: setattr(STATE, 'tts_voice', CFG.TTS_VOICES[c.get_active()]))
        vbox.pack_start(combo, False, False, 0)
        
        # Hotkeys Config
        lbl = Gtk.Label(); lbl.set_markup("<b>Hotkeys (Requires Restart)</b>"); lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl, False, False, 10)
        
        grid = Gtk.Grid(); grid.set_column_spacing(10); grid.set_row_spacing(8)
        
        # Helper to create row
        cls.entries = {}
        fields = [
            ("Dictation", "dictation_key"), ("AI Chat", "ai_chat_key"),
            ("Rewrite", "rewrite_key"), ("Vision", "vision_key"),
            ("Pin Chat", "pin_chat_key"), ("TTS Toggle", "tts_key")
        ]
        
        for i, (name, key_id) in enumerate(fields):
            grid.attach(Gtk.Label(label=name, xalign=0), 0, i, 1, 1)
            ent = Gtk.Entry()
            ent.set_text(SettingsManager.get(key_id))
            ent.set_width_chars(15)
            # Simple validation/formatting hint could go here
            cls.entries[key_id] = ent
            grid.attach(ent, 1, i, 1, 1)
            
        vbox.pack_start(grid, False, False, 0)
        
        # Save Button
        btn = Gtk.Button(label="Save & Apply")
        btn.get_style_context().add_class("suggested-action")
        btn.connect("clicked", lambda b: cls._save_and_reload(win))
        vbox.pack_end(btn, False, False, 0)
        
        win.add(vbox)
        win.connect("destroy", lambda w: setattr(cls, '_instance', None))
        return win
    
    @classmethod
    def _save_and_reload(cls, win):
        # Save values
        for key_id, entry in cls.entries.items():
            val = entry.get_text().strip()
            # Basic normalization (e.g. F3 -> Key.f3)
            if val.upper() in [f"F{i}" for i in range(1, 13)] and not val.startswith("Key."):
                val = f"Key.{val.lower()}"
            SettingsManager.set(key_id, val)
        
        # Re-initialize keyboard handler
        KeyboardHandler.refresh_mappings()
        ChatManager.refresh_overlay() # Update hints
        win.destroy()
        print("✅ Settings saved and mappings refreshed.")

# ============================================================================
# SECTION 8: SYSTEM TRAY
# ============================================================================
class TrayManager:
    @staticmethod
    def start():
        STATE.indicator = AppIndicator.Indicator.new("lw", "emblem-favorite", AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        STATE.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        STATE.indicator.set_title("LinuxWhisper")
        TrayManager.update_menu()
        Gtk.main()
    
    @staticmethod
    def update_menu():
        if not STATE.indicator: return
        m = Gtk.Menu()
        
        if STATE.answer_history:
            for item in STATE.answer_history[:CFG.ANSWER_HISTORY_LIMIT]:
                lbl = f"[{item['timestamp']}] {item['text'][:40]}..."
                mi = Gtk.MenuItem(label=lbl)
                mi.connect("activate", lambda w, t=item['text']: ClipboardService.paste_text(re.sub(r"^\[.*?\]\s*", "", t)))
                m.append(mi)
            m.append(Gtk.SeparatorMenuItem())
        
        m.append(Gtk.MenuItem(label="Clear History")); m.get_children()[-1].connect("activate", lambda w: HistoryManager.clear_all())
        m.append(Gtk.MenuItem(label="Settings")); m.get_children()[-1].connect("activate", lambda w: SettingsDialog.show())
        m.append(Gtk.SeparatorMenuItem())
        m.append(Gtk.MenuItem(label="Quit")); m.get_children()[-1].connect("activate", lambda w: (Gtk.main_quit(), os._exit(0)))
        m.show_all()
        STATE.indicator.set_menu(m)

# ============================================================================
# SECTION 9: KEYBOARD HANDLER
# ============================================================================
class KeyboardHandler:
    KEY_MAPPINGS = {}
    MODE_KEYS = {}
    
    @classmethod
    def refresh_mappings(cls):
        """Rebuild key mappings from settings."""
        # Load keys
        k_dictation = SettingsManager.get_key("dictation_key")
        k_ai = SettingsManager.get_key("ai_chat_key")
        k_rewrite = SettingsManager.get_key("rewrite_key")
        k_vision = SettingsManager.get_key("vision_key")
        k_pin = SettingsManager.get_key("pin_chat_key")
        k_tts = SettingsManager.get_key("tts_key")
        
        # Helper list
        cls.KEY_MAPPINGS = {
            "dictation": [k for k in [k_dictation] if k],
            "ai": [k for k in [k_ai] if k],
            "ai_rewrite": [k for k in [k_rewrite] if k],
            "vision": [k for k in [k_vision] if k],
            "pin": [k for k in [k_pin] if k],
            "tts": [k for k in [k_tts] if k],
        }
        
        # Reverse mapping
        cls.MODE_KEYS = {
            "dictation": "dictation",
            "ai": "ai",
            "ai_rewrite": "ai_rewrite",
            "vision": "vision"
        }
    
    @classmethod
    def on_press(cls, key):
        if STATE.recording: return
        
        # Check handlers
        if key in cls.KEY_MAPPINGS["pin"]:
            ChatManager.toggle_pin(); return
        if key in cls.KEY_MAPPINGS["tts"]:
            TTSService.toggle(); return
            
        # Modes
        for mode, id in cls.MODE_KEYS.items():
            if key in cls.KEY_MAPPINGS[id]:
                STATE.current_mode = mode
                if mode == "ai_rewrite":
                    subprocess.run(["xdotool", "key", "ctrl+c"])
                    time.sleep(0.1)
                OverlayManager.show(mode)
                AudioService.start_recording()
                return

    @classmethod
    def on_release(cls, key):
        if not STATE.recording: return
        for mode, id in cls.MODE_KEYS.items():
            if key in cls.KEY_MAPPINGS[id]:
                if mode == STATE.current_mode:
                    OverlayManager.hide()
                    data = AudioService.stop_recording()
                    if data is not None and (txt := AudioService.transcribe(data)):
                        ModeHandler.process(mode, txt)

class ModeHandler:
    @staticmethod
    def process(mode, text):
        if mode == "dictation":
            HistoryManager.add_answer(f"[Dictation] {text}"); ChatManager.add_message("user", f"🎤 {text}"); ClipboardService.type_text(text)
        elif mode == "ai":
            resp = AIService.chat(text)
            if resp:
                HistoryManager.add_message("user", text); HistoryManager.add_message("assistant", resp); HistoryManager.add_answer(resp)
                ChatManager.add_message("user", text); ChatManager.add_message("assistant", resp)
                ClipboardService.type_text(resp); TTSService.speak(resp)
        elif mode == "ai_rewrite":
            orig = pyperclip.paste().strip()
            resp = AIService.chat(f"INSTRUCTION:\n{text}\n\nORIGINAL:\n{orig}\n\nRewrite original based on instruction. Output ONLY result.")
            if resp:
                HistoryManager.add_message("user", f"[Rewrite] {text}"); HistoryManager.add_message("assistant", resp); HistoryManager.add_answer(resp)
                ChatManager.add_message("user", f"✍️ {text}"); ChatManager.add_message("assistant", resp)
                ClipboardService.paste_text(resp); TTSService.speak(resp)
        elif mode == "vision":
            img = ImageService.take_screenshot()
            if img and (resp := AIService.vision(text, img)):
                HistoryManager.add_message("user", f"[Vision] {text}"); HistoryManager.add_message("assistant", resp); HistoryManager.add_answer(resp)
                ChatManager.add_message("user", f"📸 {text}"); ChatManager.add_message("assistant", resp)
                ClipboardService.type_text(resp); TTSService.speak(resp)

# ============================================================================
# SECTION 10: MAIN
# ============================================================================
def main():
    print("🚀 LinuxWhisper Running.")
    print(f"Settings: {SettingsManager.CONFIG_FILE}")
    KeyboardHandler.refresh_mappings()
    # Start keyboard listener in background thread
    def _run_listener():
        with keyboard.Listener(on_press=KeyboardHandler.on_press, on_release=KeyboardHandler.on_release) as listener:
            listener.join()
    
    threading.Thread(target=_run_listener, daemon=True).start()
    TrayManager.start()

if __name__ == "__main__":
    main()
