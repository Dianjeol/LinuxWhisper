"""
Conversation and answer history management.
"""
from __future__ import annotations

import time
from typing import Dict, List

from linuxwhisper.config import CFG
from linuxwhisper.state import STATE


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

        # Late import to avoid circular dependency
        from linuxwhisper.ui.tray import TrayManager
        TrayManager.update_menu()

    @staticmethod
    def clear_all() -> None:
        """Clear all history."""
        STATE.answer_history = []
        STATE.conversation_history = []
        STATE.chat_messages = []
        # Late imports to avoid circular dependencies
        from linuxwhisper.ui.tray import TrayManager
        from linuxwhisper.managers.chat import ChatManager
        TrayManager.update_menu()
        ChatManager.refresh_overlay()
