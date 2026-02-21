"""
System tray (AppIndicator) management.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Dict

from linuxwhisper.config import CFG
from linuxwhisper.decorators import run_on_main_thread
from linuxwhisper.state import STATE

import gi
gi.require_version('AyatanaAppIndicator3', '0.1')
gi.require_version('Gtk', '3.0')
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import Gtk


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
    @run_on_main_thread
    def update_menu() -> None:
        """Rebuild and update tray menu."""
        if not STATE.indicator:
            return
        STATE.gtk_menu = TrayManager._build_menu()
        STATE.indicator.set_menu(STATE.gtk_menu)

    @staticmethod
    def _build_menu() -> Gtk.Menu:
        """Build GTK menu for tray."""
        # Late imports to avoid circular dependencies
        from linuxwhisper.managers.history import HistoryManager
        from linuxwhisper.services.clipboard import ClipboardService
        from linuxwhisper.ui.settings_dialog import SettingsDialog

        menu = Gtk.Menu()

        # History items
        if STATE.answer_history:
            for item in STATE.answer_history[:CFG.ANSWER_HISTORY_LIMIT]:
                preview = item["text"][:50].replace("\n", " ")
                if len(item["text"]) > 50:
                    preview += "..."
                label = f"[{item['timestamp']}] {preview}"
                menu_item = Gtk.MenuItem(label=label)
                menu_item.connect("activate", TrayManager._make_history_callback(item, ClipboardService))
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
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Chat toggle
        chat_toggle = Gtk.CheckMenuItem(label="Show Chat Overlay")
        chat_toggle.set_active(STATE.chat_enabled)
        chat_toggle.connect("toggled", TrayManager._toggle_chat)
        menu.append(chat_toggle)

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
    def _make_history_callback(item: Dict[str, str], clipboard_service) -> Callable:
        """Create callback for history item click."""
        def callback(widget):
            # Remove prefix labels like [Dictation]
            clean = re.sub(r"^\[.*?\]\s*", "", item["text"])
            clipboard_service.paste_text(clean)
        return callback

    @staticmethod
    def _toggle_chat(widget) -> None:
        """Toggle chat overlay visibility."""
        STATE.chat_enabled = widget.get_active()
        from linuxwhisper.state import SettingsManager
        SettingsManager.save(STATE)
        
        from linuxwhisper.managers.chat import ChatManager
        if not STATE.chat_enabled:
            ChatManager._destroy()
        else:
            ChatManager.refresh_overlay()

    @staticmethod
    def _quit(widget) -> None:
        """Quit application."""
        Gtk.main_quit()
        os._exit(0)
