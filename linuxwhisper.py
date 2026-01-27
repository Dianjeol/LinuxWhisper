import os
import sys
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
from gi.repository import Gtk, GLib, Gdk, AyatanaAppIndicator3 as AppIndicator

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
    global answer_history, conversation_history
    answer_history = []
    conversation_history = []
    update_tray_menu()


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
# 5. KEYBOARD LOGIC (F3, F4, F7, F8)
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

    return False


def on_press(key):
    global recording, stream, audio_buffer, current_mode
    if recording: return

    # Prüfe alle Tasten mit der Helfer-Funktion (Standard + Apple)
    is_f3 = check_key(key, "f3")
    is_f4 = check_key(key, "f4")
    is_f7 = check_key(key, "f7")
    is_f8 = check_key(key, "f8")

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
                    
                    # Add to tray history
                    add_to_answer_history(ai_response)
                    
                    type_text(ai_response)
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
                    
                    # Add to tray history
                    add_to_answer_history(new_text)
                    
                    # Copy the new, improved text to the clipboard and paste it directly
                    pyperclip.copy(new_text)
                    subprocess.run(["xdotool", "key", "ctrl+v"])
                    
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
                    
                    # Add to tray history
                    add_to_answer_history(ai_response)
                    
                    type_text(ai_response)
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
print("\n📌 System tray icon active - click for history & settings")

# Start keyboard listener in a thread
def run_keyboard_listener():
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

keyboard_thread = threading.Thread(target=run_keyboard_listener, daemon=True)
keyboard_thread.start()

# Start system tray (runs in main thread)
start_tray()
