#!/usr/bin/env python3
"""Low-latency AltGr dictation and F4 voice editing for Omarchy."""
import argparse
import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
import fcntl
import json
import math
import os
from pathlib import Path
import struct
import time
from urllib.parse import urlencode

import evdev
import sounddevice as sd
from websockets.asyncio.client import connect

from agent import Agent
from desktop import Desktop
from overlay import Overlay

RATE = 16000
FRAME = 160  # 10 ms, mono, signed little-endian PCM16
KEYS = (evdev.ecodes.KEY_RIGHTALT, evdev.ecodes.KEY_F4)


def clip(data, adc, pressed, released=None):
    """Keep only samples acquired while the recording key was down."""
    first = max(0, math.ceil((pressed - adc) * RATE - 1e-5))
    last = len(data) // 2
    if released is not None:
        last = min(last, math.ceil((released - adc) * RATE - 1e-5))
    if last <= first:
        return b"", adc
    return data[first * 2:last * 2], adc + first / RATE


@dataclass
class Take:
    pressed: float
    key: int = evdev.ecodes.KEY_RIGHTALT
    released: float | None = None
    flushed: float | None = None
    turns: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


async def finish_take(take, desktop, latency_log):
    text = " ".join(m["transcript"] for _, m in sorted(take.turns.items())).strip()
    if not text:
        print("No text; nothing pasted or logged.", flush=True)
        return
    delivered = await desktop.paste(text)
    elapsed_ms = (delivered - take.released) * 1000
    # The timestamp is captured before logging/output, never after either.
    latency_log.write(f"{elapsed_ms:.1f}\n")
    latency_log.flush()
    print(f"Text delivered — Alt released → paste acknowledged: {elapsed_ms:.1f} ms", flush=True)


async def agent_take(ws, events, take, chunk_ms, desktop, key, overlay=None):
    # Both preparations run during recording, not after key release.
    selection = asyncio.create_task(desktop.selection())
    agent = Agent(key)
    try:
        await capture_take(ws, events, take, chunk_ms, overlay)
        instruction = " ".join(m["transcript"] for _, m in sorted(take.turns.items())).strip()
        if not instruction:
            print("No text; no agent request and nothing pasted.", flush=True)
            return
        context, target = await selection
        answer = await agent.answer(instruction, context)
        await desktop.paste(answer, target=target)
        # Keep the existing AltGr-only latency log comparable.
        print("Agent response pasted at the cursor and available on the clipboard.", flush=True)
    finally:
        await asyncio.gather(selection, return_exceptions=True)
        await agent.close()


async def receive(ws, take):
    async for raw in ws:
        message = json.loads(raw)
        if message["type"] in ("Error", "FatalError", "ConfigureFailure"):
            raise RuntimeError(f"Deepgram reported {message['type']}; recording aborted.")
        if message["type"] == "Warning":
            take.warnings.append(message)
        if message["type"] != "TurnInfo":
            continue
        take.turns[message["turn_index"]] = message
    if take.flushed is None:
        raise RuntimeError("Deepgram closed before CloseStream; no complete result.")


async def capture_take(ws, events, take, chunk_ms, overlay=None):
    """Send clipped PCM in order, then drain the decoder (never ForceEndTurn)."""
    pending = bytearray()
    packet_bytes = RATE * chunk_ms // 1000 * 2
    captured_until = take.pressed

    async def audio(data, adc):
        nonlocal captured_until
        captured_until = max(captured_until, adc + len(data) / 2 / RATE)
        data, adc = clip(data, adc, take.pressed, take.released)
        if overlay is not None and take.released is None and data:
            overlay.audio(data, adc)
        pending.extend(data)
        while len(pending) >= packet_bytes:
            await ws.send(bytes(pending[:packet_bytes]))
            del pending[:packet_bytes]

    receiver = asyncio.create_task(receive(ws, take))
    try:
        # Equivalent ADC endpoints can differ by float roundoff, not a new frame.
        while take.released is None or captured_until + 1e-9 < take.released:
            if receiver.done():
                await receiver
            # A broken microphone must not produce a plausible latency number.
            kind, when, data = await asyncio.wait_for(events.get(), timeout=3)
            if kind == "audio":
                await audio(data, when)
            elif kind == "up" and data == take.key and take.released is None:
                take.released = when
            elif kind == "error":
                raise RuntimeError(data)
        if pending:
            await ws.send(bytes(pending))
        # ForceEndTurn only commits the latest decoded Update and can lose the tail.
        # CloseStream decodes all submitted audio; finality is known at server close.
        take.flushed = time.monotonic()
        await ws.send('{"type":"CloseStream"}')
        await asyncio.wait_for(receiver, timeout=15)
    finally:
        if not receiver.done():
            receiver.cancel()
        with suppress(asyncio.CancelledError):
            await receiver


def keyboards(loop, events):
    devices = []
    try:
        for path in evdev.list_devices():
            device = evdev.InputDevice(path)
            if not any(key in device.capabilities().get(evdev.ecodes.EV_KEY, []) for key in KEYS):
                device.close()
                continue
            devices.append(device)
            # Linux EVIOCSCLOCKID = _IOW('E', 0xa0, int); evdev has no wrapper.
            fcntl.ioctl(device.fd, 0x400445A0, struct.pack("i", time.CLOCK_MONOTONIC))

            def readable(device=device):
                try:
                    for event in device.read():
                        if event.type == evdev.ecodes.EV_KEY and event.code in KEYS:
                            if event.value in (0, 1):
                                events.put_nowait(("down" if event.value else "up", event.timestamp(), event.code))
                except OSError as error:
                    loop.remove_reader(device.fd)
                    events.put_nowait(("error", time.monotonic(), f"Keyboard disconnected: {error}"))

            loop.add_reader(device.fd, readable)
        if not devices:
            raise RuntimeError("No readable AltGr/F4 keyboard under /dev/input; input-device permission is required.")
        return devices
    except BaseException:
        for device in devices:
            loop.remove_reader(device.fd)
            device.close()
        raise


async def main(args):
    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        raise RuntimeError("DEEPGRAM_API_KEY is missing. Start with ./run (loads ~/.bashrc if needed).")
    agent_key = os.environ.get("OPENROUTER_API_KEY")
    desktop = Desktop()
    await desktop.check()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    loop = asyncio.get_running_loop()
    events = asyncio.Queue()
    devices = keyboards(loop, events)

    def microphone(data, frames, timing, status):
        now = time.monotonic()
        if status:
            loop.call_soon_threadsafe(events.put_nowait, ("error", now, f"Audio loss: {status}; measurement invalid."))
            return
        adc = now + timing.inputBufferAdcTime - timing.currentTime
        if not 0 <= timing.currentTime - timing.inputBufferAdcTime < 1:
            loop.call_soon_threadsafe(events.put_nowait, ("error", now, "No plausible ADC timestamp; measurement aborted."))
            return
        loop.call_soon_threadsafe(events.put_nowait, ("audio", adc, bytes(data)))

    params = dict(model="flux-general-multi", language_hint=args.language,
                  encoding="linear16", sample_rate=RATE, eot_threshold="1.0",
                  eot_timeout_ms=60000, mip_opt_out="true")
    url = f"wss://api.eu.deepgram.com/v2/listen?{urlencode(params)}"
    print(f"Flux Multilingual | EU only, MIP opt-out | {args.language} | {args.chunk_ms} ms packets")
    print("Hold right Alt/AltGr, speak, release → paste at the current cursor. Ctrl+C quits.")
    print("Hold F4 → spoken instruction + selected text → DeepSeek response at the cursor.")
    if not agent_key:
        print("F4 disabled: OPENROUTER_API_KEY is missing; AltGr remains available.")
    print("Microphone warms up locally; only audio during AltGr/F4 is sent. Idle: WebSocket pings only.", flush=True)
    print(f"Latency log (ms, one value per dictation): {args.log}", flush=True)
    overlay = None
    try:
        if not args.no_overlay:
            overlay = Overlay(devices, bool(agent_key))
        with args.log.open("a", encoding="utf-8") as latency_log, sd.RawInputStream(
                samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                latency="low", device=args.device, callback=microphone):
            while True:
                async with connect(url, additional_headers={"Authorization": f"Token {key}"},
                                   compression=None, ping_interval=15, open_timeout=15, close_timeout=3) as ws:
                    hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                    if hello.get("type") != "Connected":
                        raise RuntimeError(f"Deepgram connection failed ({hello.get('type', 'unknown response')}).")
                    if overlay is not None:
                        overlay.ready()
                    ready = time.monotonic()
                    print("\nREADY — hold AltGr to dictate, F4 to edit the text selection.", flush=True)
                    recent = deque(maxlen=20)
                    while True:
                        kind, when, data = await events.get()
                        if kind == "error":
                            raise RuntimeError(data)
                        if kind == "audio":
                            recent.append((kind, when, data))
                        if kind == "down" and when >= ready:
                            if data == evdev.ecodes.KEY_F4 and not agent_key:
                                print("F4 requires OPENROUTER_API_KEY (loaded from ~/.bashrc by ./run).", flush=True)
                                continue
                            take = Take(when, key=data)
                            # Preserve ADC samples that arrived just before the key event.
                            buffered = list(recent)
                            remaining = []
                            while not events.empty():
                                remaining.append(events.get_nowait())
                            for event in buffered + remaining:
                                events.put_nowait(event)
                            print("RECORDING …", flush=True)
                            if take.key == evdev.ecodes.KEY_F4:
                                try:
                                    await agent_take(ws, events, take, args.chunk_ms, desktop, agent_key, overlay)
                                except (RuntimeError, OSError, TimeoutError, UnicodeError) as error:
                                    print(f"F4 failed: {error}", flush=True)
                            else:
                                await capture_take(ws, events, take, args.chunk_ms, overlay)
                                await finish_take(take, desktop, latency_log)
                            for warning in take.warnings:
                                print("Deepgram warning:", warning.get("code", "unspecified"), flush=True)
                            break
                if args.once:
                    return
    finally:
        for device in devices:
            loop.remove_reader(device.fd)
            device.close()
        if overlay is not None:
            overlay.close()


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="de", help="Flux language_hint (default: de)")
    parser.add_argument("--chunk-ms", type=int, choices=(20, 40, 80), default=80,
                        help="80 ms recommended by Deepgram; 20/40 ms for comparison")
    parser.add_argument("--device", help="PortAudio device name (list: .venv/bin/python -m sounddevice)")
    parser.add_argument("--once", action="store_true", help="Exit after one AltGr or F4 recording")
    parser.add_argument("--no-overlay", action="store_true", help="Disable the recording indicator")
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    parser.add_argument("--log", type=Path, default=state / "sound" / "latency.log",
                        help="Latency log: one number in milliseconds per successful dictation")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(main(arguments()))
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as error:
        raise SystemExit(f"ERROR: {error}") from None
