"""
API client initialization.

Chat and rewrite (F4/F9) run on OpenRouter; vision and TTS still run on Groq.
Both expose an OpenAI-compatible chat API, but Groq's SDK hardcodes the
`/openai/v1` path prefix and therefore cannot address OpenRouter's `/api/v1`,
so OpenRouter gets a minimal httpx client instead.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import httpx
from groq import Groq

from linuxwhisper.config import CFG


def _env_key(name: str) -> Optional[str]:
    """Return the environment key, or None when it is unset/empty."""
    return os.environ.get(name) or None


def _create_groq_client() -> Groq:
    """Build the Groq client used by vision and TTS."""
    api_key = _env_key("GROQ_API_KEY")
    if not api_key:
        print("❌ Error: GROQ_API_KEY missing. Please check your environment variables!")
        sys.exit(1)
    return Groq(api_key=api_key)


class OpenRouterClient:
    """Minimal OpenRouter chat-completions client."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def chat(self, model: str, messages: List[Dict[str, Any]]) -> str:
        """Return the assistant text for a chat completion."""
        response = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": messages},
            timeout=CFG.OPENROUTER_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


GROQ_CLIENT = _create_groq_client()

# Only chat and rewrite use this one, so a missing key must not take down the app.
OPENROUTER_API_KEY = _env_key("OPENROUTER_API_KEY")
OPENROUTER_CLIENT = (
    OpenRouterClient(OPENROUTER_API_KEY, CFG.OPENROUTER_BASE_URL)
    if OPENROUTER_API_KEY
    else None
)
if OPENROUTER_CLIENT is None:
    print("⚠️  OPENROUTER_API_KEY missing — F4 Chat and F9 Rewrite are disabled.")
