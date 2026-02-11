"""
Chat overlay using WebKit2 with HTML/CSS/JS rendering.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Callable, Dict, List, Optional

import cairo
import pyperclip

from linuxwhisper.config import CFG
from linuxwhisper.state import STATE

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gdk, GLib, Gtk, WebKit2


# ---------------------------------------------------------------------------
# HTML / CSS / JS Templates
# ---------------------------------------------------------------------------
SVG_COPY_ICON = '<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>'

CHAT_CSS = '''
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  height: 100%;
  background: transparent !important;
  font-family: 'Inter', 'Ubuntu', system-ui, -apple-system, sans-serif;
  color: {text}; 
  font-size: 14px;
  line-height: 1.6;
  overflow: hidden; /* Hide native window scrollbar */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}}

/* Rounded Window Container */
.chat-window {{
  display: flex; 
  flex-direction: column;
  height: 100%;
  background-color: {bg_rgba};
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 20px;
  border: 1px solid {accent_alpha20}; /* Accent border */
  box-shadow: 0 8px 32px {black_alpha40};
  overflow: hidden;
  margin: 0; position: relative;
}}

/* Drag Handle */
.drag-handle {{
  position: absolute; top: 0; left: 0; width: 100%; height: 60px;
  z-index: 5; cursor: move; -webkit-app-region: drag;
}}

/* Scroll Area */
.chat-scroll-area {{
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
  padding-bottom: 10px;
  z-index: 10; /* Above drag handle */
  position: relative;
  /* Optimization for smoother scrolling and less blurring */
  transform: translateZ(0);
  will-change: transform;
}}
/* Custom Scrollbar for inner area */
.chat-scroll-area::-webkit-scrollbar {{ width: 6px; }}
.chat-scroll-area::-webkit-scrollbar-track {{ background: transparent; }}
.chat-scroll-area::-webkit-scrollbar-thumb {{ background: {white_alpha10}; border-radius: 3px; }}
.chat-scroll-area::-webkit-scrollbar-thumb:hover {{ background: {white_alpha25}; }}

/* HUD / Pin Hint - Static Header */
.pin-hint {{
  flex-shrink: 0; /* Keep it fixed height */
  width: fit-content;
  margin: 12px auto 4px auto;
  background: {accent};
  color: {text_on_accent}; /* Contrast text */
  padding: 5px 14px;
  font-size: 11px; font-weight: 600;
  border-radius: 20px;
  z-index: 20; /* Above drag handle */
  display: flex; gap: 10px; align-items: center; justify-content: center;
  transition: opacity 0.3s;
  cursor: default; position: relative;
}}
.pin-hint a {{ color: inherit; text-decoration: none; opacity: 0.8; transition: opacity 0.2s; cursor: pointer; }}
.pin-hint a:hover {{ opacity: 1; color: {white}; }}

/* Chat Content */
.chat-container {{
  display: flex; flex-direction: column;
  padding: 10px 16px 20px 16px;
}}

/* Messages */
.message-wrapper {{
  display: flex;
  margin-bottom: 14px;
  animation: slideFadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  opacity: 0;
  transform: translate3d(0, 15px, 0);
}}
.message-wrapper.user {{ justify-content: flex-end; }}
.message-wrapper.assistant {{ justify-content: flex-start; }}

@keyframes slideFadeIn {{
  to {{ opacity: 1; transform: translate3d(0, 0, 0); }}
}}

.message {{
  max-width: 86%;
  padding: 10px 16px;
  border-radius: 14px;
  position: relative;
  word-wrap: break-word;
  /* Force hardware acceleration and stabilization */
  transform: translateZ(0);
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}}

/* User Bubble - Surface Color */
.user .message {{
  background: {surface};
  color: {text};
  border: 1px solid {white_alpha05};
}}

/* Assistant Bubble - Accent Color */
.assistant .message {{
  background: {accent};
  color: {text_on_accent}; /* Contrast text */
  border: 1px solid {white_alpha10};
  font-weight: 500;
}}

/* Copy Button */
.copy-btn {{
  background: none; border: none; cursor: pointer;
  padding: 6px; margin: 0 4px;
  opacity: 0.6; /* Always visible */
  transition: opacity 0.2s;
  align-self: center;
  color: {accent}; /* Accent */
  z-index: 20; /* Ensure Clickable */
}}
.message-wrapper:hover .copy-btn {{ opacity: 1; }}
.copy-btn:hover {{ opacity: 1; color: {text}; transform: scale(1.05); }}
.copy-btn svg {{ width: 15px; height: 15px; fill: currentColor; }}
.copy-btn.copied {{ opacity: 1; color: {accent}; }}
.user .copy-btn {{ order: -1; }}

.text code {{
  background: {accent_alpha10}; padding: 2px 5px; border-radius: 4px;
  font-family: 'SF Mono', monospace; font-size: 0.9em; color: {accent};
}}
.text pre {{
  background: {bg}; border: 1px solid {surface};
  color: {text}; padding: 12px; border-radius: 10px;
  overflow-x: auto; margin: 8px 0; font-family: 'SF Mono', monospace;
  font-size: 0.85em;
}}
.text strong {{ font-weight: 600; color: {accent}; }}

/* Code block copy button styles */
.code-block-wrapper {{
  position: relative;
  margin: 12px 0;
}}
.code-block-wrapper pre {{ margin: 0; }}
.code-copy-btn {{
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: {surface_alpha80};
  border: 1px solid {accent_alpha30};
  border-radius: 6px;
  color: {text};
  padding: 4px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}}
.code-block-wrapper:hover .code-copy-btn {{ opacity: 1; }}
.code-copy-btn:hover {{ background: {selection_alpha90}; color: {white}; transform: scale(1.05); }}
.code-copy-btn svg {{ width: 14px; height: 14px; fill: currentColor; }}
.code-copy-btn.copied {{ color: {success}; border-color: {success}; }}

.status {{
  align-self: center; background: {white_alpha05}; color: {dim_text};
  font-size: 11px; padding: 3px 10px; border-radius: 10px;
  margin: 10px 0; border: 1px solid {white_alpha05};
}}
'''

CHAT_JS = '''
const copyIcon = '<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>';
const checkIcon = '<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';

function copyText(btn, index) {
  // Use custom protocol to let Python handle clipboard safely
  window.location.href = "copy://" + index;
  
  // Optimistic UI update
  btn.innerHTML = checkIcon;
  btn.classList.add('copied');
  setTimeout(() => { btn.innerHTML = copyIcon; btn.classList.remove('copied'); }, 1500);
}

function signalDrag() {
  window.webkit.messageHandlers.signal.postMessage(JSON.stringify({action: 'Drag'}));
}

function copyCode(btn) {
  const code = btn.nextElementSibling.querySelector('code');
  if (!code) return;
  
  const text = code.innerText;
  // Use robust postMessage IPC for large content
  window.webkit.messageHandlers.signal.postMessage(JSON.stringify({
    action: 'CopyContent',
    content: text
  }));
  
  // Feedback
  btn.innerHTML = checkIcon;
  btn.classList.add('copied');
  setTimeout(() => { btn.innerHTML = copyIcon; btn.classList.remove('copied'); }, 1500);
}

// Scroll Logic: Improved to handle reloads and dynamic content
function checkScroll(smooth=true) {
  const scrollArea = document.getElementById('scroll-area');
  if (!scrollArea) return;
  
  const scrollToBottom = () => {
    scrollArea.scrollTo({ 
      top: scrollArea.scrollHeight, 
      behavior: smooth ? 'smooth' : 'auto' 
    });
  };

  // Immediate scroll
  scrollToBottom();
  
  // Backup scrolls to account for rendering delays and images
  requestAnimationFrame(scrollToBottom);
  setTimeout(scrollToBottom, 50);
  setTimeout(scrollToBottom, 250);
}

// Observe new messages
const chat = document.getElementById('chat');
if (chat) {
  new MutationObserver(() => checkScroll(true)).observe(chat, { childList: true, subtree: true });
}

window.onload = () => checkScroll(false);
'''

CHAT_HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{CHAT_CSS}</style></head>
<body>
<div class="chat-window">
  <div class="drag-handle" onmousedown="signalDrag()"></div>
  {pin_hint}
  <div class="chat-scroll-area" id="scroll-area">
    <div id="chat" class="chat-container">{messages}</div>
  </div>
</div>
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
        self.connect("draw", self._on_draw_window)
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

    def _on_draw_window(self, widget: Gtk.Window, cr: cairo.Context) -> bool:
        """Clear window background to fixed transparency for rounded corners."""
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        return False

    def _setup_webview(self) -> None:
        """Setup WebKit2 webview."""
        self.webview = WebKit2.WebView()
        self.webview.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)

        # Robust IPC via UserContentManager
        content_manager = self.webview.get_user_content_manager()
        content_manager.register_script_message_handler("signal")
        content_manager.connect("script-message-received::signal", self._on_script_message)

        self.webview.connect("decide-policy", self._on_policy_decision)
        self.add(self.webview)

    def _on_script_message(self, manager, message) -> None:
        """Handle robust signals from JavaScript."""
        try:
            val = message.get_js_value()
            if not val:
                return

            # Message is sent as a JSON string from JS
            data = val.to_string()
            msg = json.loads(data)

            action = msg.get('action')
            if action == 'Drag':
                display = self.get_display()
                seat = display.get_default_seat()
                pointer = seat.get_pointer()
                screen, x, y = pointer.get_position()
                self.begin_move_drag(1, x, y, Gtk.get_current_event_time())
            elif action == 'CopyContent':
                content = msg.get('content', '')
                pyperclip.copy(content)
        except Exception as e:
            print(f"❌ ScriptMessage Error: {e}")

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

        for idx, msg in enumerate(messages):
            role = msg["role"]
            rendered = self._render_markdown(msg["text"])
            # Pass index, not ID, for robust handling
            copy_btn = f'<button class="copy-btn" onclick="copyText(this, {idx})">{SVG_COPY_ICON}</button>'
            msg_html = f'<div class="message"><div class="text">{rendered}</div></div>'

            html_messages.append(
                f'<div class="message-wrapper {role}">'
                f'{msg_html}'
                f'{copy_btn}'
                f'</div>'
            )

        if status_text:
            html_messages.append(f'<div class="message status">{status_text}</div>')

        # Build pin hint - simple text with gear icon
        pin_label = CFG.HOTKEY_DEFS["pin"][0]
        tts_label = CFG.HOTKEY_DEFS["tts"][0]
        pin_status = f"{pin_label}: Unpin" if is_pinned else f"{pin_label}: Pin"
        voice_status = f"{tts_label}: Mute" if is_tts else f"{tts_label}: Voice"

        pin_hint = (
            f'<div class="pin-hint">'
            f'<span>{pin_status}</span>'
            f'<span style="opacity:0.2; margin:0 4px">|</span>'
            f'<span>{voice_status}</span>'
            f'<span style="opacity:0.2; margin:0 4px">|</span>'
            f'<a href="settings://open" class="settings-link" title="Settings">⚙️</a>'
            f'</div>'
        )

        # Prepare dynamic CSS with centralized colors
        def hex_to_rgba(hex_str, alpha):
            h = hex_str.lstrip('#')
            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"

        def get_contrast_text(bg_hex):
            # Simple luminance-based contrast
            h = bg_hex.lstrip('#')
            rgb = [int(h[i:i+2], 16) for i in (0, 2, 4)]
            # Standard relative luminance formula
            lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
            return "#000000" if lum > 0.5 else "#FFFFFF"

        scheme = CFG.COLOR_SCHEMES.get(STATE.color_scheme, CFG.COLOR_SCHEMES[CFG.DEFAULT_SCHEME])

        formatted_css = CHAT_CSS.format(
            bg=scheme["bg"],
            bg_rgba=hex_to_rgba(scheme["bg"], 0.95),
            surface=scheme["surface"],
            surface_alpha80=hex_to_rgba(scheme["surface"], 0.8),
            accent=scheme["accent"],
            accent_alpha10=hex_to_rgba(scheme["accent"], 0.1),
            accent_alpha20=hex_to_rgba(scheme["accent"], 0.2),
            accent_alpha30=hex_to_rgba(scheme["accent"], 0.3),
            text=scheme["text"],
            text_on_accent=scheme["text"] if STATE.color_scheme == "Pink Orchid" else get_contrast_text(scheme["accent"]),
            success=scheme["accent"],
            dim_text=hex_to_rgba(scheme["text"], 0.6),
            selection_alpha90=hex_to_rgba(scheme["accent"], 0.3),
            white=scheme["text"],
            white_alpha05=hex_to_rgba(scheme["text"], 0.05),
            white_alpha10=hex_to_rgba(scheme["text"], 0.1),
            white_alpha25=hex_to_rgba(scheme["text"], 0.25),
            black_alpha40=hex_to_rgba(scheme["bg"], 0.4)
        )

        html = CHAT_HTML_TEMPLATE.replace("{messages}", "\n".join(html_messages))
        html = html.replace("{pin_hint}", pin_hint)
        html = html.replace("{CHAT_CSS}", formatted_css)
        html = html.replace("{CHAT_JS}", CHAT_JS)

        self.webview.load_html(html, None)

    def _on_policy_decision(self, webview, decision, decision_type) -> bool:
        """Handle URI navigations (copy://, settings://)."""
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            nav = decision.get_navigation_action()
            uri = nav.get_request().get_uri()
            if not uri:
                return False

            if uri.startswith("settings://"):
                from linuxwhisper.ui.settings_dialog import SettingsDialog
                GLib.idle_add(SettingsDialog.show)
                decision.ignore()
                return True

            if uri.startswith("copy://"):
                try:
                    idx = int(uri.split("copy://")[1])
                    if 0 <= idx < len(STATE.chat_messages):
                        text = STATE.chat_messages[idx]["text"]
                        pyperclip.copy(text)
                except Exception:
                    pass
                decision.ignore()
                return True

        return False

    @staticmethod
    def _render_markdown(text: str) -> str:
        """Convert simple markdown to HTML."""
        text = html_lib.escape(text)

        # Code blocks with copy button
        def repl_code_block(match):
            code_content = match.group(1).strip()
            return (
                f'<div class="code-block-wrapper">'
                f'<button class="code-copy-btn" onclick="copyCode(this)" title="Copy Code">{SVG_COPY_ICON}</button>'
                f'<pre><code>{code_content}</code></pre>'
                f'</div>'
            )
        text = re.sub(r'```(?:\w+)?(?:\s*\n)(.*?)\n?```', repl_code_block, text, flags=re.DOTALL)
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
