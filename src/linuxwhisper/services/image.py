"""
Screenshot and image encoding service.
"""
from __future__ import annotations

import base64
import os
import subprocess
from typing import Optional

from linuxwhisper.config import CFG
from linuxwhisper.decorators import safe_execute


class ImageService:
    """Screenshot and image encoding service."""

    @staticmethod
    @safe_execute("Screenshot")
    def take_screenshot() -> Optional[str]:
        """Take screenshot and return base64 encoded string."""
        subprocess.run(["gnome-screenshot", "-f", CFG.TEMP_SCREEN_PATH])
        with open(CFG.TEMP_SCREEN_PATH, "rb") as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
        os.remove(CFG.TEMP_SCREEN_PATH)
        return encoded
