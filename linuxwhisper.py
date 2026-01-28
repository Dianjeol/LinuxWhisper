import os
import sys
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import pathlib
import subprocess
import sounddevice as sd
import numpy as np
import io
import time
import base64
import pyperclip
import threading
import gi
import queue
import math
import re
import cairo
from scipy.io.wavfile import write
from groq import Groq
from pynput import keyboard

# GTK imports for system tray
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, GLib, Gdk, AyatanaAppIndicator3 as AppIndicator, WebKit2

# ==========================================
# 1. SETUP & KEYS
# ==========================================
GROQ_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_KEY:
    print("❌ Error: GROQ_API_KEY missing. Please check your environment variables!")
    exit(1)

client_g = Groq(api_key=GROQ_KEY)

# ==========================================
# 2. GLOBAL STATE
# ==========================================
FS = 44100  # Audio sample rate
recording = False
current_mode = None  # dictation, ai, ai_rewrite, vision
audio_buffer = []    
stream = None
overlay_window = None
overlay_thread = None
viz_queue = queue.Queue()

# Chat Overlay State (WhatsApp-style)
chat_overlay_window = None
chat_messages = []          # List of {"role": "user/assistant", "text": "..."}
chat_pinned = False         # Pin mode (False = Auto-Hide, True = Pinned)
chat_hide_timer = None      # GLib timeout ID for auto-hide
CHAT_AUTO_HIDE_SEC = 5      # Seconds before auto-hide

# TTS (Text-to-Speech) State
tts_enabled = False         # Toggle with F10
tts_voice = "diana"         # Selected voice
TTS_VOICES = ["diana", "hannah", "autumn", "austin", "daniel", "troy"]


# The compassionate System Prompt (NVC & ACIM)
SYSTEM_PROMPT = (
    "Act as a compassionate assistant. Base your reasoning on the principles of "
    "Nonviolent Communication and A Course in Miracles. Apply these frameworks as "
    "your underlying logic without explicitly naming them or forcing them. Let your "
    "output be grounded, clear, and highly concise. Return ONLY the direct response."
)

# Mode-specific overlay configurations
OVERLAY_CONFIG = {
    "dictation": {"icon": "🎙️", "text": "Listening...", "bg": "#1a1a2e", "fg": "#00d4ff"},
    "ai": {"icon": "🤖", "text": "AI Listening...", "bg": "#1a1a2e", "fg": "#a855f7"},
    "ai_rewrite": {"icon": "✍️", "text": "Rewrite Mode...", "bg": "#1a1a2e", "fg": "#22c55e"},
    "vision": {"icon": "📸", "text": "Vision Mode...", "bg": "#1a1a2e", "fg": "#f59e0b"},
}

# Conversation history for context (32k token limit)
MAX_TOKENS = 32000
conversation_history = []  # List of {"role": "user/assistant", "content": "..."}

# Answer history for system tray (separate from conversation_history)
answer_history = []  # List of {"text": "...", "timestamp": "..."}


def add_to_answer_history(text):
    """Add an answer to the tray history."""
    global answer_history
    timestamp = time.strftime("%H:%M")
    answer_history.insert(0, {"text": text, "timestamp": timestamp})
    
    # Trim to configured limit
    limit = 15
    if limit > 0 and len(answer_history) > limit:
        answer_history = answer_history[:limit]
    
    # Update tray menu
    update_tray_menu()


def estimate_tokens(text):
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4


def get_history_tokens():
    """Calculate total tokens in conversation history."""
    return sum(estimate_tokens(msg["content"]) for msg in conversation_history)


def trim_history():
    """Remove oldest messages until under MAX_TOKENS."""
    while get_history_tokens() > MAX_TOKENS and len(conversation_history) > 0:
        conversation_history.pop(0)


def add_to_history(role, content):
    """Add a message to history and trim if needed."""
    conversation_history.append({"role": role, "content": content})
    trim_history()


def build_messages_with_history(user_content):
    """Build messages array with system prompt, history, and new user message."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_content})
    return messages

# ==========================================
# 4. SYSTEM TRAY (GTK AppIndicator)
# ==========================================
indicator = None
gtk_menu = None


def on_history_item_click(item):
    """Create a callback for history item click."""
    def callback(widget):
        text = item["text"]
        # Remove prefixes like [Dictation], [Rewrite], etc. and leading whitespace
        clean_text = re.sub(r"^\[.*?\]\s*", "", text)
        pyperclip.copy(clean_text)
        subprocess.run(["xdotool", "key", "ctrl+v"])
    return callback





def clear_history_gtk(widget):
    """Clear both answer history and conversation context."""
    global answer_history, conversation_history, chat_messages
    answer_history = []
    conversation_history = []
    chat_messages = []  # Also clear chat overlay
    update_tray_menu()
    # Update chat overlay if visible
    GLib.idle_add(_show_chat_overlay_main_thread, None)


def quit_app_gtk(widget):
    """Quit the application."""
    Gtk.main_quit()
    os._exit(0)


def build_gtk_menu():
    """Build GTK menu for the indicator."""
    menu = Gtk.Menu()
    
    # History items
    if answer_history:
        # Fixed limit of 15 items
        items_to_show = answer_history[:15]
        
        for item in items_to_show:
            preview = item["text"][:50].replace("\n", " ") + ("..." if len(item["text"]) > 50 else "")
            label = f"[{item['timestamp']}] {preview}"
            menu_item = Gtk.MenuItem(label=label)
            menu_item.connect("activate", on_history_item_click(item))
            menu.append(menu_item)
        
        menu.append(Gtk.SeparatorMenuItem())
    else:
        empty_item = Gtk.MenuItem(label="(No History)")
        empty_item.set_sensitive(False)
        menu.append(empty_item)
        menu.append(Gtk.SeparatorMenuItem())
    
    # Clear history (clears everything)
    clear_history_item = Gtk.MenuItem(label="Clear History")
    clear_history_item.connect("activate", clear_history_gtk)
    menu.append(clear_history_item)
    
    menu.append(Gtk.SeparatorMenuItem())
    

    
    # Quit
    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", quit_app_gtk)
    menu.append(quit_item)
    
    menu.show_all()
    return menu


def update_tray_menu():
    """Update the tray menu with current history."""
    global indicator, gtk_menu
    if indicator:
        gtk_menu = build_gtk_menu()
        indicator.set_menu(gtk_menu)


def start_tray():
    """Start the GTK AppIndicator system tray."""
    global indicator, gtk_menu
    
    # Create the indicator with system icon 'emblem-favorite' (star)
    indicator = AppIndicator.Indicator.new(
        "linuxwhisper",
        "emblem-favorite",
        AppIndicator.IndicatorCategory.APPLICATION_STATUS
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    indicator.set_title("LinuxWhisper")
    
    # Build and set menu
    gtk_menu = build_gtk_menu()
    indicator.set_menu(gtk_menu)
    
    # Run GTK main loop
    Gtk.main()


# ==========================================
# 5. GTK FLOATING OVERLAY
# ==========================================
class GtkOverlay(Gtk.Window):
    """A sleek, floating overlay using native GTK + Cairo."""
    
    def __init__(self, mode):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.mode = mode
        self.config = OVERLAY_CONFIG.get(mode, OVERLAY_CONFIG["dictation"])
        
        # Window setup
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_keep_above(True)
        
        # Transparent background
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
            
        # Position
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geometry = monitor.get_geometry()
        screen_w = geometry.width
        screen_h = geometry.height
        w, h = 220, 60
        x = (screen_w - w) // 2
        y = screen_h - h - 80
        self.move(x, y)
        self.set_default_size(w, h)
        
        # UI Components
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self.on_draw)
        self.add(self.drawing_area)
        
        # Animation loop
        self.timeout_id = GLib.timeout_add(40, self.animate_waveform)
        
        self.show_all()

    def on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        
        # 1. Background (Rounded Rect)
        # Parse hex color manually since we're using raw cairo or Gdk
        # Simple rounded rect path
        r = 15 # radius
        cr.new_sub_path()
        cr.arc(w-r, r, r, -math.pi/2, 0)
        cr.arc(w-r, h-r, r, 0, math.pi/2)
        cr.arc(r, h-r, r, math.pi/2, math.pi)
        cr.arc(r, r, r, math.pi, 3*math.pi/2)
        cr.close_path()
        
        # Set Color (BG) - converting hex to rgb
        bg_color = self.hex_to_rgb(self.config["bg"])
        cr.set_source_rgba(bg_color[0], bg_color[1], bg_color[2], 0.92) # 0.92 alpha
        cr.fill()
        
        # 2. Icon (Left)
        cr.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(20)
        fg_color = self.hex_to_rgb(self.config["fg"])
        cr.set_source_rgb(*fg_color)
        
        # Center icon vertically around h/2, x=30
        (xb, yb, width, height, dx, dy) = cr.text_extents(self.config["icon"])
        cr.move_to(30 - width/2, h/2 + height/2)
        cr.show_text(self.config["icon"])
        
        # 3. Text (Top Rightish)
        cr.set_font_size(10)
        cr.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        (xb, yb, width, height, dx, dy) = cr.text_extents(self.config["text"])
        cr.move_to(110 - width/2, 20) # Approx center of right side
        cr.show_text(self.config["text"])
        
        # 4. Waveform (Bottom Rightish)
        self.draw_waveform(cr, 60, 210, 45, fg_color)

    def draw_waveform(self, cr, start_x, end_x, center_y, color):
        data = None
        while not viz_queue.empty():
            try: data = viz_queue.get_nowait()
            except queue.Empty: break
            
        cr.set_source_rgb(*color)
        cr.set_line_width(3)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        
        if data is not None and len(data) > 0:
            width = end_x - start_x
            num_bars = 30
            step = max(1, len(data) // num_bars)
            bar_width = width / num_bars
            max_height = 15
            
            for i in range(num_bars):
                idx = i * step
                if idx >= len(data): break
                
                chunk = data[idx:idx+step]
                amp = np.max(np.abs(chunk)) if len(chunk) > 0 else 0
                
                bar_h = min(max_height, amp * 40 * max_height)
                bar_h = max(1, bar_h)
                
                x = start_x + (i * bar_width)
                cr.move_to(x, center_y - bar_h)
                cr.line_to(x, center_y + bar_h)
                cr.stroke()
        else:
            # Idle line
            cr.move_to(start_x, center_y)
            cr.line_to(end_x, center_y)
            cr.set_line_width(2)
            cr.set_source_rgb(0.33, 0.33, 0.33) # Grey
            cr.stroke()

    def result(self):
        return True # Keep animation running

    def animate_waveform(self):
        self.drawing_area.queue_draw()
        return True

    def hex_to_rgb(self, hex_str):
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16)/255.0 for i in (0, 2, 4))
    
    def close(self):
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None
        self.destroy()


def _show_overlay_main_thread(mode):
    global overlay_window
    if overlay_window:
        try: overlay_window.close()
        except: pass
    overlay_window = GtkOverlay(mode)

def _hide_overlay_main_thread():
    global overlay_window
    if overlay_window:
        overlay_window.close()
        overlay_window = None

def show_overlay(mode):
    """Schedules the overlay to show on the main GTK thread."""
    GLib.idle_add(_show_overlay_main_thread, mode)

def hide_overlay():
    """Schedules the overlay to hide on the main GTK thread."""
    GLib.idle_add(_hide_overlay_main_thread)


# ==========================================
# 6. CHAT OVERLAY (WhatsApp-Style with WebKit2)
# ==========================================

CHAT_HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    height: 100%;
    background: #ECE5DD;
    font-family: -apple-system, Helvetica, Arial, sans-serif;
    font-size: 14px;
    overflow-x: hidden;
  }
  body {
    background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4cfc4' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  }
  .pin-hint {
    position: sticky;
    top: 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    text-align: center;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 500;
    z-index: 100;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    border-radius: 0 0 12px 12px;
    margin: 0 20px 10px 20px;
  }
  .pin-hint kbd {
    background: rgba(255,255,255,0.25);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: inherit;
    font-weight: 600;
  }
  /* Custom Voice Dropdown */
  .voice-btn {
    background: rgba(255,255,255,0.25);
    border: none;
    color: white;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: inherit;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .voice-btn:hover { background: rgba(255,255,255,0.35); }
  .dropdown { position: relative; display: inline-block; }
  .dropdown-content {
    display: none;
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    background-color: white;
    min-width: 100px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    border-radius: 8px;
    z-index: 1000;
    margin-top: 6px;
    padding: 4px 0;
    overflow: hidden;
  }
  .dropdown-content.show { display: block; animation: slideDown 0.2s ease; }
  @keyframes slideDown {
    from { opacity: 0; transform: translate(-50%, -10px); }
    to { opacity: 1; transform: translate(-50%, 0); }
  }
  .dropdown-item {
    color: #4a5568;
    padding: 6px 12px;
    text-decoration: none;
    display: block;
    text-align: left;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.1s;
  }
  .dropdown-item:hover { background-color: #f7fafc; color: #667eea; }
  .dropdown-item.selected { background-color: #ebf4ff; color: #5a67d8; font-weight: 600; }
  .chat-container {
    display: flex;
    flex-direction: column;
    padding: 12px 10px 10px 10px;
    min-height: 100%;
  }
  .message-wrapper {
    display: flex;
    align-items: flex-start;
    margin-bottom: 4px;
    animation: fadeIn 0.3s ease-out;
  }
  .message-wrapper.user { justify-content: flex-end; }
  .message-wrapper.assistant { justify-content: flex-start; }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .message {
    max-width: 80%;
    padding: 6px 10px 8px;
    border-radius: 7.5px;
    position: relative;
    word-wrap: break-word;
    box-shadow: 0 1px 0.5px rgba(0,0,0,0.13);
  }
  .user .message {
    background: #DCF8C6;
    border-top-right-radius: 0;
    margin-right: 8px;
  }
  .user .message::after {
    content: '';
    position: absolute;
    right: -8px;
    top: 0;
    border-width: 0 0 10px 8px;
    border-style: solid;
    border-color: transparent transparent transparent #DCF8C6;
  }
  .assistant .message {
    background: #FFFFFF;
    border-top-left-radius: 0;
    margin-left: 8px;
  }
  .assistant .message::before {
    content: '';
    position: absolute;
    left: -8px;
    top: 0;
    border-width: 0 8px 10px 0;
    border-style: solid;
    border-color: transparent #FFFFFF transparent transparent;
  }
  .copy-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px 6px;
    opacity: 0.35;
    transition: opacity 0.2s, transform 0.1s;
    align-self: flex-start;
    margin-top: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .copy-btn svg {
    width: 16px;
    height: 16px;
    fill: #54656f;
  }
  .copy-btn:hover { opacity: 1; transform: scale(1.1); }
  .copy-btn.copied { opacity: 1; }
  .copy-btn.copied svg { fill: #25D366; }
  .user .copy-btn { order: -1; }
  .status {
    align-self: center;
    background: rgba(255,255,255,0.9);
    color: #667781;
    font-size: 12px;
    padding: 4px 12px;
    border-radius: 7px;
    margin: 8px 0;
    box-shadow: 0 1px 0.5px rgba(0,0,0,0.1);
  }
  .text {
    color: #111b21;
    line-height: 1.45;
  }
  /* Inline Code */
  .text code {
    background: rgba(0,0,0,0.06);
    padding: 1px 5px;
    border-radius: 4px;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 13px;
    color: #c7254e;
  }
  /* Code Blocks */
  .text pre {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 10px 12px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 6px 0;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.4;
  }
  .text pre code {
    background: none;
    padding: 0;
    color: inherit;
    font-size: inherit;
  }
  /* Bold & Italic */
  .text strong { font-weight: 600; }
  .text em { font-style: italic; }
</style>
</head>
<body>
{pin_hint}
<div id="chat" class="chat-container">
{messages}
</div>
<script>
  const copyIcon = '<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>';
  const checkIcon = '<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
  
  function copyText(btn, id) {
    const el = document.getElementById(id);
    if (!el) return;
    
    const text = el.innerText;
    
    // Try modern clipboard API first, fallback to execCommand
    const copyPromise = navigator.clipboard ? 
      navigator.clipboard.writeText(text) : 
      new Promise((resolve, reject) => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand('copy') ? resolve() : reject();
        } catch(e) { reject(e); }
        document.body.removeChild(ta);
      });
    
    copyPromise.then(() => {
      btn.innerHTML = checkIcon;
      btn.classList.add('copied');
      setTimeout(() => { btn.innerHTML = copyIcon; btn.classList.remove('copied'); }, 1500);
    }).catch(() => {});
  }
  
  // Scroll to bottom after content loads
  setTimeout(() => {
    const chat = document.getElementById('chat');
    if (chat) chat.scrollIntoView({ behavior: 'smooth', block: 'end' });
    window.scrollTo(0, document.body.scrollHeight);
  }, 50);

  // Toggle Dropdown
  function toggleVoiceMenu() {
    const el = document.getElementById("voiceDropdown");
    if(el) el.classList.toggle("show");
  }
  
  // Close dropdown if clicked outside
  window.onclick = function(event) {
    if (!event.target.matches('.voice-btn')) {
      const dropdowns = document.getElementsByClassName("dropdown-content");
      for (let i = 0; i < dropdowns.length; i++) {
        if (dropdowns[i].classList.contains('show')) {
          dropdowns[i].classList.remove('show');
        }
      }
    }
  }
</script>
</body>
</html>
'''


class ChatOverlay(Gtk.Window):
    """WhatsApp-style chat overlay using WebKit2."""
    
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        
        # Window setup
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        
        # Transparent background
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        
        # Position at right edge of screen
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geometry = monitor.get_geometry()
        self.win_width = 340
        self.win_height = 450
        x = geometry.x + geometry.width - self.win_width - 20
        y = geometry.y + (geometry.height - self.win_height) // 2
        self.move(x, y)
        self.set_default_size(self.win_width, self.win_height)
        
        # WebKit2 WebView
        self.webview = WebKit2.WebView()
        self.webview.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)
        
        # Connect signal to handle voice:// URIs
        self.webview.connect("decide-policy", self._on_decide_policy)
        
        # Container with rounded corners
        self.add(self.webview)
        
        # Fade animation state
        self.opacity_value = 0.0
        self.fade_in_active = False
        self.fade_out_active = False
        self.fade_timer = None
        
        # Start fade in
        self.start_fade_in()
        
        self.show_all()
    
    def start_fade_in(self):
        """Start fade-in animation."""
        self.fade_out_active = False
        self.fade_in_active = True
        self.opacity_value = 0.0
        if self.fade_timer:
            GLib.source_remove(self.fade_timer)
        self.fade_timer = GLib.timeout_add(16, self._fade_in_step)
    
    def _fade_in_step(self):
        """Animation step for fade-in."""
        self.opacity_value = min(1.0, self.opacity_value + 0.1)
        try:
            self.set_opacity(self.opacity_value)
        except:
            pass
        if self.opacity_value >= 1.0:
            self.fade_in_active = False
            self.fade_timer = None
            return False
        return True
    
    def start_fade_out(self, callback=None):
        """Start fade-out animation."""
        self.fade_in_active = False
        self.fade_out_active = True
        self.fade_callback = callback
        if self.fade_timer:
            GLib.source_remove(self.fade_timer)
        self.fade_timer = GLib.timeout_add(16, self._fade_out_step)
    
    def _fade_out_step(self):
        """Animation step for fade-out."""
        self.opacity_value = max(0.0, self.opacity_value - 0.1)
        try:
            self.set_opacity(self.opacity_value)
        except:
            pass
        if self.opacity_value <= 0.0:
            self.fade_out_active = False
            self.fade_timer = None
            if hasattr(self, 'fade_callback') and self.fade_callback:
                self.fade_callback()
            return False
        return True
    
    def update_content(self, messages, status_text=None, is_pinned=False, is_tts=False):
        """Update the chat content with Markdown rendering."""
        html_messages = []
        for idx, msg in enumerate(messages):
            role_class = msg["role"]
            text = msg["text"]
            
            # Simple Markdown to HTML conversion
            rendered = self._render_markdown(text)
            
            msg_id = f"msg_{idx}"
            # SVG clipboard icon (like ChatGPT/Gemini)
            svg_icon = '<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>'
            copy_btn = f'<button class="copy-btn" onclick="copyText(this, \'{msg_id}\')">{svg_icon}</button>'
            
            html_messages.append(
                f'<div class="message-wrapper {role_class}">'
                f'<div class="message"><div class="text" id="{msg_id}">{rendered}</div></div>'
                f'{copy_btn}'
                f'</div>'
            )
        
        if status_text:
            html_messages.append(f'<div class="message status">{status_text}</div>')
        
        # Pin status banner with Voice indicator and dropdown
        if is_tts:
            dropdown_items = []
            for v in TTS_VOICES:
                sel_class = "selected" if v == tts_voice else ""
                dropdown_items.append(f'<div class="dropdown-item {sel_class}" onclick="window.location.href=\'voice://{v}\'">{v.title()}</div>')
            
            menu_html = "".join(dropdown_items)
            voice_html = f'''
            <div class="dropdown">
              <button onclick="toggleVoiceMenu()" class="voice-btn">🔊 {tts_voice.title()} ▼</button>
              <div id="voiceDropdown" class="dropdown-content">
                {menu_html}
              </div>
            </div>
            '''
        else:
            voice_html = '🔇 F10: Voice'
        
        if is_pinned:
            pin_hint = f'<div class="pin-hint pinned">📌 Pinned | {voice_html}</div>'
        else:
            pin_hint = f'<div class="pin-hint">⏱️ F9: Pin | {voice_html}</div>'
        
        html = CHAT_HTML_TEMPLATE.replace("{messages}", "\n".join(html_messages))
        html = html.replace("{pin_hint}", pin_hint)
        self.webview.load_html(html, None)
    
    def _on_decide_policy(self, webview, decision, decision_type):
        """Handle navigation to intercept voice:// URIs."""
        global tts_voice
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            nav_action = decision.get_navigation_action()
            request = nav_action.get_request()
            uri = request.get_uri()
            if uri and uri.startswith("voice://"):
                voice = uri.replace("voice://", "")
                if voice in TTS_VOICES:
                    tts_voice = voice
                    # Refresh overlay to show new selection
                    GLib.idle_add(_show_chat_overlay_main_thread, None)
                decision.ignore()
                return True
        return False
    
    def _render_markdown(self, text):
        """Convert simple Markdown to HTML."""
        import html as html_lib
        
        # Escape HTML first
        text = html_lib.escape(text)
        
        # Code blocks: ```code```
        def replace_code_block(match):
            code = match.group(1)
            return f'<pre><code>{code}</code></pre>'
        text = re.sub(r'```(?:\w+)?\n?(.*?)```', replace_code_block, text, flags=re.DOTALL)
        
        # Inline code: `code`
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # Bold: **text** or __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        
        # Italic: *text* or _text_ (but not inside words)
        text = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'<em>\1</em>', text)
        text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<em>\1</em>', text)
        
        # Line breaks
        text = text.replace('\n', '<br>')
        
        return text
    
    def close(self):
        """Clean up and destroy."""
        if self.fade_timer:
            GLib.source_remove(self.fade_timer)
            self.fade_timer = None
        self.destroy()


def _show_chat_overlay_main_thread(status_text=None):
    """Show or update the chat overlay on the main thread."""
    global chat_overlay_window, chat_hide_timer
    
    # Cancel existing hide timer
    if chat_hide_timer:
        GLib.source_remove(chat_hide_timer)
        chat_hide_timer = None
    
    if not chat_overlay_window:
        chat_overlay_window = ChatOverlay()
    elif chat_overlay_window.fade_out_active:
        # Interrupt fade-out, start fade-in again
        chat_overlay_window.start_fade_in()
    
    # Pass pinned and TTS state to show appropriate banner
    chat_overlay_window.update_content(chat_messages, status_text, is_pinned=chat_pinned, is_tts=tts_enabled)
    
    # Schedule auto-hide if not pinned
    if not chat_pinned:
        chat_hide_timer = GLib.timeout_add_seconds(CHAT_AUTO_HIDE_SEC, _auto_hide_chat_overlay)


def _auto_hide_chat_overlay():
    """Auto-hide callback for the chat overlay."""
    global chat_hide_timer
    chat_hide_timer = None
    if not chat_pinned and chat_overlay_window:
        chat_overlay_window.start_fade_out(callback=_destroy_chat_overlay)
    return False


def _destroy_chat_overlay():
    """Destroy the chat overlay window."""
    global chat_overlay_window
    if chat_overlay_window:
        chat_overlay_window.close()
        chat_overlay_window = None


def _hide_chat_overlay_main_thread():
    """Hide the chat overlay on the main thread."""
    global chat_hide_timer
    if chat_hide_timer:
        GLib.source_remove(chat_hide_timer)
        chat_hide_timer = None
    if chat_overlay_window:
        chat_overlay_window.start_fade_out(callback=_destroy_chat_overlay)


def add_chat_message(role, text):
    """Add a message to the chat overlay history and show/update the overlay."""
    global chat_messages
    chat_messages.append({"role": role, "text": text})
    # Limit to last 20 messages
    if len(chat_messages) > 20:
        chat_messages = chat_messages[-20:]
    GLib.idle_add(_show_chat_overlay_main_thread, None)


def show_chat_status(status_text):
    """Show a status message in the chat overlay."""
    GLib.idle_add(_show_chat_overlay_main_thread, status_text)


def toggle_chat_pin():
    """Toggle the pin mode for the chat overlay."""
    global chat_pinned, chat_hide_timer
    chat_pinned = not chat_pinned
    
    # If unpinning, hide immediately
    if not chat_pinned and chat_overlay_window:
        if chat_hide_timer:
            GLib.source_remove(chat_hide_timer)
            chat_hide_timer = None
        chat_overlay_window.start_fade_out(callback=_destroy_chat_overlay)
    else:
        # Just refresh the overlay to show updated pin status in banner
        GLib.idle_add(_show_chat_overlay_main_thread, None)


def toggle_tts():
    """Toggle TTS (text-to-speech) mode for AI responses."""
    global tts_enabled
    tts_enabled = not tts_enabled
    # Refresh the overlay to show updated TTS status
    GLib.idle_add(_show_chat_overlay_main_thread, None)


def speak_text(text):
    """Convert text to speech using Groq Orpheus TTS and play it."""
    if not tts_enabled or not text:
        return
    
    def _speak_thread():
        try:
            response = client_g.audio.speech.create(
                model="canopylabs/orpheus-v1-english",
                voice=tts_voice,
                input=text[:4000],  # Limit to avoid API limits
                response_format="wav"
            )
            # Save and play
            audio_path = "/tmp/linuxwhisper_tts.wav"
            response.write_to_file(audio_path)
            subprocess.run(["aplay", "-q", audio_path], capture_output=True)
        except Exception as e:
            print(f"TTS Error: {e}")
    
    # Run TTS in background thread to not block UI
    threading.Thread(target=_speak_thread, daemon=True).start()

def type_text(text):
    """Pastes text instantly via clipboard (much faster than xdotool type)."""
    if not text: return
    
    # Save original clipboard content
    try:
        original_clipboard = pyperclip.paste()
    except:
        original_clipboard = None
    
    # Add leading space to prevent merging with previous words
    clean_text = " " + text.strip() if not text.startswith(" ") else text
    
    # Copy to clipboard and paste instantly
    pyperclip.copy(clean_text)
    subprocess.run(["xdotool", "key", "ctrl+v"])
    
    # Small delay to ensure paste completes, then restore original clipboard
    time.sleep(0.1)
    if original_clipboard is not None:
        try:
            pyperclip.copy(original_clipboard)
        except:
            pass

def transcribe_audio(audio_data):
    """Sends audio data to Groq Whisper Large V3."""
    wav_buffer = io.BytesIO()
    wav_buffer.name = "audio.wav"
    write(wav_buffer, FS, audio_data)
    wav_buffer.seek(0)
    try:
        transcript = client_g.audio.transcriptions.create(model="whisper-large-v3", file=wav_buffer)
        return transcript.text.strip()
    except Exception as e: return ""

def encode_image(image_path):
    """Encodes an image to Base64 for the Groq Vision API."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ==========================================
# 4. AUDIO CALLBACK
# ==========================================
def callback(indata, frames, time_info, status):
    """Captures audio chunks into the buffer while recording."""
    if recording: 
        data_copy = indata.copy()
        audio_buffer.append(data_copy)
        
        # Send data to visualization queue (downsample to reduce load)
        # Indata is (frames, 1), we want flat array
        try:
            flat_data = data_copy[:, 0]
            # Put every 10th sample is enough for vis, or just the whole thing
            # We skip if queue is full to prevent lag
            if viz_queue.qsize() < 5:
                viz_queue.put_nowait(flat_data[::10])
        except:
            pass

# ==========================================
# 5. KEYBOARD LOGIC (F3, F4, F7, F8, F9)
# ==========================================
def check_key(key, target_mode):
    """
    Prüft, ob die gedrückte Taste entweder die Standard-F-Taste
    ODER die Apple/Media-Spezialtaste ist.
    Funktioniert für alle Tastatur-Typen.
    """
    # 1. Standard F-Tasten (für normale Tastaturen / GitHub User)
    if target_mode == "f3" and key == keyboard.Key.f3: return True
    if target_mode == "f4" and key == keyboard.Key.f4: return True
    if target_mode == "f7" and key == keyboard.Key.f7: return True
    if target_mode == "f8" and key == keyboard.Key.f8: return True

    # 2. Apple/Media-Tasten (ohne Fn-Taste zu drücken)
    if hasattr(key, 'vk'):
        if target_mode == "f3" and key.vk == 269025098: return True  # Expose/Mission Control
        if target_mode == "f4" and key.vk == 269025099: return True  # Launchpad
    
    # 3. Media-Tasten (F7/F8 auf Apple-Tastaturen)
    if target_mode == "f7" and key == keyboard.Key.media_previous: return True
    if target_mode == "f8" and key == keyboard.Key.media_play_pause: return True
    
    # 4. F9 Key (Toggle Pin-Mode) + media_next for Apple keyboards
    if target_mode == "f9":
        if key == keyboard.Key.f9: return True
        if key == keyboard.Key.media_next: return True
        # Some keyboards use vk code
        if hasattr(key, 'vk') and key.vk == 269025047: return True  # XF86AudioNext
    
    # 5. F10 Key (Toggle TTS)
    if target_mode == "f10":
        if key == keyboard.Key.f10: return True
        # Media volume mute as alternative
        if key == keyboard.Key.media_volume_mute: return True

    return False


def on_press(key):
    global recording, stream, audio_buffer, current_mode
    if recording: return

    # Prüfe alle Tasten mit der Helfer-Funktion (Standard + Apple)
    is_f3 = check_key(key, "f3")
    is_f4 = check_key(key, "f4")
    is_f7 = check_key(key, "f7")
    is_f8 = check_key(key, "f8")
    is_f9 = check_key(key, "f9")
    is_f10 = check_key(key, "f10")
    
    # F9: Toggle Chat Pin Mode (does not require recording)
    if is_f9:
        toggle_chat_pin()
        return
    
    # F10: Toggle TTS Mode (does not require recording)
    if is_f10:
        toggle_tts()
        return

    if is_f3 or is_f4 or is_f7 or is_f8:
        # Determine the mode
        if is_f3:   current_mode = "dictation"
        elif is_f4: current_mode = "ai"
        elif is_f7: 
            current_mode = "ai_rewrite"
            # 1. Immediately copy the currently selected text
            subprocess.run(["xdotool", "key", "ctrl+c"])
            # 2. Short pause to allow the OS to update the clipboard
            time.sleep(0.1)
        elif is_f8: current_mode = "vision"

        recording = True
        audio_buffer = []
        
        # Clear viz queue
        try:
            while not viz_queue.empty(): viz_queue.get_nowait()
        except: pass

        # Show floating overlay
        show_overlay(current_mode)
        
        # Start the audio stream
        stream = sd.InputStream(samplerate=FS, channels=1, dtype='float32', callback=callback)
        stream.start()

def on_release(key):
    global recording, stream, audio_buffer
    
    # Prüfe alle Tasten mit der Helfer-Funktion (Standard + Apple)
    is_f3 = check_key(key, "f3")
    is_f4 = check_key(key, "f4")
    is_f7 = check_key(key, "f7")
    is_f8 = check_key(key, "f8")

    if (is_f3 or is_f4 or is_f7 or is_f8) and recording:
        recording = False
        hide_overlay()  # Remove floating overlay
        if stream: stream.stop(); stream.close()
        
        if len(audio_buffer) > 0:
            full_audio = np.concatenate(audio_buffer, axis=0)
            final_text = transcribe_audio(full_audio)

            if not final_text: return

            # MODE 1: DICTATION (Pure Speech-to-Text)
            if current_mode == "dictation":
                add_to_answer_history(f"[Dictation] {final_text}")
                add_chat_message("user", f"🎤 {final_text}")
                type_text(final_text)

            # MODE 2: GENERAL AI (With NVC System Prompt + History)
            elif current_mode == "ai":
                try:
                    messages = build_messages_with_history(final_text)
                    res = client_g.chat.completions.create(
                        model="moonshotai/kimi-k2-instruct", 
                        messages=messages
                    )
                    ai_response = res.choices[0].message.content
                    
                    # Add to conversation history
                    add_to_history("user", final_text)
                    add_to_history("assistant", ai_response)
                    
                    # Add to tray history and chat overlay
                    add_to_answer_history(ai_response)
                    add_chat_message("user", final_text)
                    add_chat_message("assistant", ai_response)
                    
                    type_text(ai_response)
                    speak_text(ai_response)  # TTS if enabled
                except Exception as e: print(f"AI Error: {e}")

            # MODE 3: SMART REWRITE (In-Place Editing + History)
            elif current_mode == "ai_rewrite":
                original_text = pyperclip.paste().strip()
                
                # The prompt instructs the AI to rewrite the selected text based on the voice input.
                prompt = (
                    f"INSTRUCTION:\n{final_text}\n\n"
                    f"ORIGINAL TEXT:\n{original_text}\n\n"
                    "Rewrite the original text based on the instruction. "
                    "Output ONLY the finished text, without introduction or formatting."
                )
                
                try:
                    messages = build_messages_with_history(prompt)
                    res = client_g.chat.completions.create(
                        model="moonshotai/kimi-k2-instruct", 
                        messages=messages
                    )
                    new_text = res.choices[0].message.content.strip()
                    
                    # Add to conversation history
                    add_to_history("user", f"[Rewrite] {final_text}\nOriginal: {original_text[:200]}...")
                    add_to_history("assistant", new_text)
                    
                    # Add to tray history and chat overlay
                    add_to_answer_history(new_text)
                    add_chat_message("user", f"✍️ {final_text}")
                    add_chat_message("assistant", new_text)
                    
                    # Copy the new, improved text to the clipboard and paste it directly
                    pyperclip.copy(new_text)
                    subprocess.run(["xdotool", "key", "ctrl+v"])
                    speak_text(new_text)  # TTS if enabled
                    
                except Exception as e: print(f"AI Error: {e}")

            # MODE 4: SCREENSHOT VISION (With NVC System Prompt + History via Llama 4)
            elif current_mode == "vision":
                try:
                    # Takes a silent screenshot using standard Linux tools
                    subprocess.run(["gnome-screenshot", "-f", "/tmp/temp_screen.png"])
                    base64_image = encode_image("/tmp/temp_screen.png")
                    
                    # Build messages with history, but add image to last user message
                    messages = build_messages_with_history(final_text)
                    # Replace the last user message with multimodal content
                    messages[-1] = {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": final_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                        ]
                    }
                    
                    res = client_g.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=messages
                    )
                    ai_response = res.choices[0].message.content
                    
                    # Add to conversation history (text only, no image)
                    add_to_history("user", f"[Screenshot] {final_text}")
                    add_to_history("assistant", ai_response)
                    
                    # Add to tray history and chat overlay
                    add_to_answer_history(ai_response)
                    add_chat_message("user", f"📸 {final_text}")
                    add_chat_message("assistant", ai_response)
                    
                    type_text(ai_response)
                    speak_text(ai_response)  # TTS if enabled
                    os.remove("/tmp/temp_screen.png") # Clean up image file
                except Exception as e: print(f"Vision Error: {e}")

# ==========================================
# MAIN EXECUTION
# ==========================================
print("🚀 LinuxWhisper is running.")
print(" 1. F3            : Live dictation at cursor position (Whisper V3)")
print(" 2. F4            : Empathic AI question (Groq Moonshot)")
print(" 3. F7 (Previous) : Smart Rewrite - Highlight text & speak to edit (Groq Moonshot)")
print(" 4. F8 (Play)     : Empathic Vision / Screenshot (Groq Llama 4)")
print(" 5. F9 (Next)     : Toggle Chat Overlay Pin Mode")
print(" 6. F10           : Toggle TTS (Read AI responses aloud)")
print("\n📌 System tray icon active")

# Start keyboard listener in a thread
def run_keyboard_listener():
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

keyboard_thread = threading.Thread(target=run_keyboard_listener, daemon=True)
keyboard_thread.start()

# Start system tray (runs in main thread)
start_tray()
