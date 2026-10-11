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
    def _complete(messages: List[Dict[str, Any]], provider: str, model: str) -> str:
        """Run one chat completion on the configured provider."""
        if provider == "openrouter":
            if OPENROUTER_CLIENT is None:
                raise RuntimeError("OPENROUTER_API_KEY is not set — add it to ~/.bashrc")
            return OPENROUTER_CLIENT.chat(model, messages)

        if provider == "groq":
            response = GROQ_CLIENT.chat.completions.create(model=model, messages=messages)
            return response.choices[0].message.content

        raise ValueError(f"unknown provider: {provider}")

    @staticmethod
    @safe_execute("AI Chat")
    def chat(prompt: str) -> Optional[str]:
        """Send chat completion request with the provider/model chosen for F4."""
        messages = AIService.build_messages(prompt)
        return AIService._complete(messages, STATE.chat_provider, STATE.chat_model)

    @staticmethod
    @safe_execute("AI Rewrite")
    def rewrite(prompt: str) -> Optional[str]:
        """Send rewrite completion request with the provider/model chosen for F9."""
        messages = AIService.build_messages(prompt)
        return AIService._complete(messages, STATE.rewrite_provider, STATE.rewrite_model)

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
