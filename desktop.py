"""Clipboard + focused-surface paste, using Omarchy's existing conventions."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import time


class Desktop:
    def __init__(self):
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        self.wl_copy = shutil.which("wl-copy")
        if not runtime or not signature or not self.wl_copy:
            raise RuntimeError("Omarchy/Hyprland unter Wayland und wl-copy werden benötigt.")
        self.socket = Path(runtime) / "hypr" / signature / ".socket.sock"

    async def request(self, command):
        async with asyncio.timeout(3):
            reader, writer = await asyncio.open_unix_connection(self.socket)
            try:
                writer.write(command.encode())
                await writer.drain()
                response = await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
        return response.decode()

    async def check(self):
        await self.request("j/activewindow")

    async def selection(self):
        """Snapshot PRIMARY during F4 recording; never overwrite the clipboard."""
        wl_paste = shutil.which("wl-paste")
        if not wl_paste:
            raise RuntimeError("F4 benötigt wl-paste aus wl-clipboard.")
        process = await asyncio.create_subprocess_exec(
            wl_paste, "--primary", "--no-newline", "--type", "text",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(3):
                active, (text, _) = await asyncio.gather(
                    self.request("j/activewindow"), process.communicate())
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
        if process.returncode or not text.strip():
            raise RuntimeError("Keine Textauswahl verfügbar; Text markieren und F4 erneut halten.")
        target = json.loads(active).get("address")
        if not target:
            raise RuntimeError("F4 benötigt ein fokussiertes Anwendungsfenster.")
        return text.decode("utf-8"), target

    async def copy(self, text):
        # wl-copy's parent exits only after its child owns the selection. Unlike
        # --paste-once, the owner also survives the clipboard-history reader.
        process = await asyncio.create_subprocess_exec(
            self.wl_copy, "--type", "text/plain;charset=utf-8",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            # The long-lived clipboard owner inherits stderr. Do not let it keep
            # the app's/caller's pipes open after --once; exit errors are raised.
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(3):
                await process.communicate(text.encode("utf-8"))
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise RuntimeError(f"Clipboard-Übergabe fehlgeschlagen (wl-copy: {process.returncode}).")

    async def paste(self, text, target=None):
        # Clipboard setup and window classification are independent. Omarchy's
        # terminal tag is the source of truth, not a second list of app names.
        active, _ = await asyncio.gather(self.request("j/activewindow"), self.copy(text))
        window = json.loads(active)
        if target is not None and window.get("address") != target:
            raise RuntimeError("Fokus gewechselt; Antwort nur im Clipboard, nicht eingefügt.")
        terminal = any(tag.rstrip("*") == "terminal" for tag in window.get("tags", []))
        mods, key = ("SHIFT", "Insert") if terminal else ("CTRL", "V")
        # No window argument: reach the focused surface, including layer shells.
        # Explicit down/up avoids sendshortcut's stuck/repeating-key issue.
        try:
            response = await self.request(
                f'/dispatch hl.dsp.send_key_state({{mods="{mods}",key="{key}",state="down"}})')
            if response.strip() != "ok":
                raise RuntimeError(f"Einfügen fehlgeschlagen: {response.strip()}")
        finally:
            response = await self.request(
                f'/dispatch hl.dsp.send_key_state({{mods="{mods}",key="{key}",state="up"}})')
            if response.strip() != "ok":
                raise RuntimeError(f"Paste-Taste konnte nicht losgelassen werden: {response.strip()}")
        return time.monotonic()
