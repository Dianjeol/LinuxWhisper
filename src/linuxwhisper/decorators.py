"""
Utility decorators for error handling and GTK thread scheduling.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Callable

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib

logger = logging.getLogger(__name__)


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
        def _callback():
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.error("Main-thread callback error: %s", e)
            return False  # Run once only
        GLib.idle_add(_callback)
    return wrapper
