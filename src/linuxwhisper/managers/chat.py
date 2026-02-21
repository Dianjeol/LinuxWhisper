"""
Chat overlay state and message management.
"""
from __future__ import annotations

from typing import Optional

from linuxwhisper.config import CFG
from linuxwhisper.decorators import run_on_main_thread
from linuxwhisper.state import STATE

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib


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
        if not STATE.chat_enabled:
            return
            
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

        if not STATE.chat_enabled:
            ChatManager._destroy()
            return

        if not STATE.chat_overlay_window:
            # Late import to avoid circular dependency
            from linuxwhisper.ui.chat_overlay import ChatOverlay
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
