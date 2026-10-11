"""
GTK Settings dialog for voice, AI model and hotkey configuration.
"""
from __future__ import annotations

import math
import threading
from typing import Dict, List, Optional, Tuple

import cairo

from linuxwhisper.api import list_models
from linuxwhisper.config import CFG
from linuxwhisper.state import STATE, SettingsManager

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

# Providers the model selectors offer, with display names.
PROVIDER_TITLES = {"openrouter": "OpenRouter", "groq": "Groq"}

# Placeholder shown while a provider's model list is being fetched.
MODEL_LOADING_TEXT = "Loading models…"


class SettingsDialog:
    """GTK Settings dialog for voice, AI model and hotkey configuration."""

    _instance: Optional[Gtk.Window] = None
    _listbox: Optional[Gtk.ListBox] = None
    # mode ("chat"/"rewrite") -> (provider combo, model combo)
    _model_combos: Dict[str, Tuple[Gtk.ComboBoxText, Gtk.ComboBoxText]] = {}
    # provider -> model ids, filled on first use
    _model_cache: Dict[str, List[str]] = {}

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
        dialog.set_default_size(420, 760)
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

        # --- AI Models Section ---
        models_label = Gtk.Label()
        models_label.set_halign(Gtk.Align.START)
        models_label.set_markup("<b>AI Models</b>")
        vbox.pack_start(models_label, False, False, 0)

        vbox.pack_start(cls._create_model_selector("Chat (F4)", "chat"), False, False, 0)
        vbox.pack_start(cls._create_model_selector("Rewrite (F9)", "rewrite"), False, False, 0)

        model_hint = Gtk.Label()
        model_hint.set_markup(
            "<small><i>(Provider and model are stored in settings.json.)</i></small>"
        )
        model_hint.set_halign(Gtk.Align.START)
        vbox.pack_start(model_hint, False, False, 0)

        # --- Color Scheme Gallery ---
        scheme_label = Gtk.Label()
        scheme_label.set_halign(Gtk.Align.START)
        scheme_label.set_markup("<b>Color Scheme Gallery</b>")
        vbox.pack_start(scheme_label, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_size_request(-1, 230)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)

        cls._listbox = Gtk.ListBox()
        cls._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        cls._listbox.connect("row-activated", cls._on_scheme_selected)

        schemes = list(CFG.COLOR_SCHEMES.keys())
        for name in schemes:
            row = cls._create_theme_row(name)
            cls._listbox.add(row)
            if name == STATE.color_scheme:
                cls._listbox.select_row(row)

        scrolled.add(cls._listbox)
        vbox.pack_start(scrolled, True, True, 0)

        # --- Hotkeys Section ---
        hotkey_label = Gtk.Label()
        hotkey_label.set_halign(Gtk.Align.START)
        hotkey_label.set_markup("<b>Hotkeys</b>")
        vbox.pack_start(hotkey_label, False, False, 10)

        hotkey_grid = Gtk.Grid()
        hotkey_grid.set_column_spacing(15)
        hotkey_grid.set_row_spacing(8)

        hotkeys = []
        display_names = {
            "dictation": "Dictation:",
            "ai": "AI Chat:",
            "ai_rewrite": "Rewrite:",
            "vision": "Vision:",
        }

        for mode_id, (label, _, _) in CFG.HOTKEY_DEFS.items():
            name = display_names.get(mode_id, mode_id.replace("_", " ").title() + ":")
            hotkeys.append((name, label))

        for i, (name, key) in enumerate(hotkeys):
            name_label = Gtk.Label(label=name)
            name_label.set_halign(Gtk.Align.START)
            key_label = Gtk.Label(label=key)
            key_label.set_halign(Gtk.Align.START)
            key_label.get_style_context().add_class("dim-label")
            hotkey_grid.attach(name_label, 0, i, 1, 1)
            hotkey_grid.attach(key_label, 1, i, 1, 1)

        vbox.pack_start(hotkey_grid, False, False, 0)

        # Info label
        info_label = Gtk.Label()
        info_label.set_markup("<small><i>(Hotkeys are defined in config.py.)</i></small>")
        info_label.set_halign(Gtk.Align.START)
        vbox.pack_start(info_label, False, False, 10)

        # --- Close Button ---
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda w: dialog.destroy())
        vbox.pack_end(close_btn, False, False, 0)

        dialog.add(vbox)
        dialog.connect("destroy", lambda w: setattr(cls, '_instance', None))

        return dialog

    # -- AI model selection -------------------------------------------------
    @classmethod
    def _create_model_selector(cls, title: str, mode: str) -> Gtk.Box:
        """Build a provider + model selector for one mode ("chat" or "rewrite")."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        label = Gtk.Label(label=title)
        label.set_markup(f"<b>{title}</b>")
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        provider_combo = Gtk.ComboBoxText()
        for provider in CFG.PROVIDERS:
            provider_combo.append(provider, PROVIDER_TITLES.get(provider, provider))
        provider_combo.set_active_id(getattr(STATE, f"{mode}_provider"))
        row.pack_start(provider_combo, False, False, 0)

        model_combo = Gtk.ComboBoxText()
        row.pack_start(model_combo, True, True, 0)
        box.pack_start(row, False, False, 0)

        cls._model_combos[mode] = (provider_combo, model_combo)
        cls._refresh_models(mode, provider_combo.get_active_id(), getattr(STATE, f"{mode}_model"))

        provider_combo.connect("changed", cls._on_provider_changed, mode)
        model_combo.connect("changed", cls._on_model_changed, mode)
        return box

    @classmethod
    def _refresh_models(cls, mode: str, provider: str, preferred: str) -> None:
        """Fill a mode's model combo, fetching the provider catalog when needed."""
        model_combo = cls._model_combos[mode][1]
        models = cls._model_cache.get(provider)

        if models is None:
            model_combo.remove_all()
            model_combo.append_text(MODEL_LOADING_TEXT)
            model_combo.set_active(0)
            model_combo.set_sensitive(False)
            cls._request_models(mode, provider, preferred)
            return

        cls._apply_models(mode, provider, models, preferred)

    @classmethod
    def _request_models(cls, mode: str, provider: str, preferred: str) -> None:
        """Fetch a provider's model list in the background."""

        def worker() -> None:
            try:
                models: List[str] = list_models(provider)
                error = None
            except Exception as e:  # noqa: BLE001 - surfaced in the log below
                models, error = [], str(e)
            GLib.idle_add(cls._on_models_loaded, mode, provider, models, preferred, error)

        threading.Thread(target=worker, daemon=True).start()

    @classmethod
    def _on_models_loaded(cls, mode: str, provider: str, models: List[str],
                          preferred: str, error: Optional[str]) -> bool:
        """Apply a fetched model list on the GTK main thread."""
        if models:
            cls._model_cache[provider] = models
        else:
            print(f"⚠️ Could not load {provider} models: {error}")
        cls._apply_models(mode, provider, models, preferred)
        return False  # run once

    @classmethod
    def _apply_models(cls, mode: str, provider: str, models: List[str], preferred: str) -> None:
        """Populate a mode's model combo and keep the persisted choice in sync."""
        provider_combo, model_combo = cls._model_combos.get(mode, (None, None))
        if model_combo is None or provider_combo.get_active_id() != provider:
            # Dialog closed or the user switched provider again meanwhile.
            return

        default_model = CFG.DEFAULT_MODELS.get(provider, "")
        if not models:
            # No catalog (offline / missing key): keep the configured model.
            choices = [preferred]
        elif preferred in models:
            choices = list(models)
        else:
            choices = list(models)
            preferred = default_model if default_model in models else models[0]

        model_combo.remove_all()
        for name in choices:
            model_combo.append_text(name)
        model_combo.set_sensitive(True)
        model_combo.set_active(choices.index(preferred))

        if getattr(STATE, f"{mode}_model") != preferred:
            setattr(STATE, f"{mode}_model", preferred)
            SettingsManager.save(STATE)

    @classmethod
    def _on_provider_changed(cls, combo: Gtk.ComboBoxText, mode: str) -> None:
        """Handle provider selection change."""
        provider = combo.get_active_id()
        if not provider or provider == getattr(STATE, f"{mode}_provider"):
            return

        setattr(STATE, f"{mode}_provider", provider)
        SettingsManager.save(STATE)
        print(f"🔀 {mode} provider: {provider}")
        cls._refresh_models(mode, provider, getattr(STATE, f"{mode}_model"))

    @classmethod
    def _on_model_changed(cls, combo: Gtk.ComboBoxText, mode: str) -> None:
        """Handle model selection change."""
        model = combo.get_active_text()
        if not model or model == MODEL_LOADING_TEXT:
            return
        if getattr(STATE, f"{mode}_model") == model:
            return

        setattr(STATE, f"{mode}_model", model)
        print(f"🧠 {mode} model: {model}")
        SettingsManager.save(STATE)

    @staticmethod
    def _on_voice_changed(combo: Gtk.ComboBoxText) -> None:
        """Handle voice selection change."""
        voice = combo.get_active_text().lower()
        STATE.tts_voice = voice
        print(f"🎙️ Voice changed to: {voice}")
        SettingsManager.save(STATE)

    @staticmethod
    def _on_scheme_selected(listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        """Handle theme gallery selection."""
        if not row:
            return
        # Find theme name from child labels
        name = None
        def find_name(child):
            nonlocal name
            if isinstance(child, Gtk.Label) and not child.get_style_context().has_class("dim-label"):
                name = child.get_text()
            elif hasattr(child, "get_children"):
                for c in child.get_children():
                    find_name(c)

        find_name(row.get_child())

        if name in CFG.COLOR_SCHEMES:
            STATE.color_scheme = name
            print(f"🎨 Color scheme changed to: {name}")
            SettingsManager.save(STATE)
            # Late import to avoid circular dependency
            from linuxwhisper.managers.chat import ChatManager
            ChatManager.refresh_overlay()

    @classmethod
    def _create_theme_row(cls, name: str) -> Gtk.ListBoxRow:
        """Create a visual card for a theme in the gallery."""
        scheme = CFG.COLOR_SCHEMES[name]
        row = Gtk.ListBoxRow()
        row.set_margin_top(4)
        row.set_margin_bottom(4)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_start(10)
        hbox.set_margin_end(10)
        hbox.set_margin_top(8)
        hbox.set_margin_bottom(8)

        # --- Preview Swatches ---
        swatch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        colors = [scheme["bg"], scheme["surface"], scheme["accent"], scheme["text"]]
        for hex_color in colors:
            swatch = Gtk.DrawingArea()
            swatch.set_size_request(16, 16)
            swatch.connect("draw", cls._on_draw_gallery_swatch, hex_color)
            swatch_box.pack_start(swatch, False, False, 0)

        hbox.pack_start(swatch_box, False, False, 0)

        # --- Name & Description ---
        text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_label = Gtk.Label(label=name)
        name_label.set_halign(Gtk.Align.START)
        name_label.set_markup(f"<b>{name}</b>")

        desc_label = Gtk.Label(label=scheme.get("desc", ""))
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_line_wrap(True)
        desc_label.set_max_width_chars(30)
        desc_label.get_style_context().add_class("dim-label")
        desc_label.set_markup(f"<small><i>{scheme.get('desc', '')}</i></small>")

        text_vbox.pack_start(name_label, False, False, 0)
        text_vbox.pack_start(desc_label, False, False, 0)
        hbox.pack_start(text_vbox, True, True, 0)

        row.add(hbox)
        return row

    @staticmethod
    def _on_draw_gallery_swatch(widget: Gtk.DrawingArea, cr: cairo.Context, hex_color: str) -> bool:
        """Draw a small color swatch circle in the gallery row."""
        # Convert hex to RGB
        h = hex_color.lstrip('#')
        rgb = tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

        # Draw circle
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        cr.arc(w/2, h/2, min(w, h)/2 - 1, 0, 2 * math.pi)
        cr.set_source_rgb(*rgb)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.15)
        cr.set_line_width(1)
        cr.stroke()
        return True
