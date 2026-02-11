"""
Groq API client initialization.
"""
from __future__ import annotations

import os
import sys

from groq import Groq


def _init_groq_client() -> Groq:
    """Initialize Groq API client with environment key."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("❌ Error: GROQ_API_KEY missing. Please check your environment variables!")
        sys.exit(1)
    return Groq(api_key=api_key)


GROQ_CLIENT = _init_groq_client()
