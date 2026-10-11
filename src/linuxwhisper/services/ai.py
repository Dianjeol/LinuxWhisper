"""
AI chat and vision completion service.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from linuxwhisper.api import GROQ_CLIENT, OPENROUTER_CLIENT
from linuxwhisper.config import CFG
from linuxwhisper.decorators import safe_execute
from linuxwhisper.state import STATE


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
        """Send chat completion request (OpenRouter)."""
        if OPENROUTER_CLIENT is None:
            raise RuntimeError("OPENROUTER_API_KEY is not set — add it to ~/.bashrc")
        messages = AIService.build_messages(prompt)
        return OPENROUTER_CLIENT.chat(CFG.MODEL_CHAT, messages)

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
