"""Isolated recording indicator with best-effort, low-rate volume snapshots."""
import math
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import time


_AUDIO_TIME = struct.Struct("<d")


def volume_level(pcm):
    """Map mono PCM16 RMS to bar travel: quiet below -42 dBFS, full at -16."""
    samples = memoryview(pcm).cast("h")
    if not samples:
        return 0.0
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768
    decibels = 20 * math.log10(max(rms, 1 / 32768))
    return max(0.0, min(1.0, (decibels + 42) / 26))


class Overlay:
    """Prepare the optional visual process before microphone/WebSocket readiness."""

    def __init__(self, devices, agent_enabled):
        self.process = None
        self.audio_socket = None
        self.next_audio = 0.0
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("DEEPGRAM_API_KEY", "OPENROUTER_API_KEY")}
        command = [sys.executable, str(Path(__file__).resolve()),
                   "agent" if agent_enabled else "dictation"]
        try:
            self.audio_socket, reader = socket.socketpair(
                socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_NONBLOCK)
            self.audio_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            with reader:
                self.process = subprocess.Popen(
                    [*command, str(reader.fileno()), *(device.path for device in devices)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, env=environment, start_new_session=True,
                    pass_fds=(reader.fileno(),),
                )
            if not select.select([self.process.stdout], [], [], 5)[0] or self.process.stdout.readline() != b"ready\n":
                raise RuntimeError("Quickshell could not initialize; see README requirements")
            os.set_blocking(self.process.stdin.fileno(), False)
        except (OSError, RuntimeError) as error:
            self.close()
            print(f"Recording overlay unavailable: {error}. Dictation remains available.", flush=True)

    def ready(self):
        # Only called before READY; a stalled renderer must never block dictation.
        if self.process is not None:
            try:
                os.write(self.process.stdin.fileno(), b"ready\n")
            except (OSError, ValueError):
                pass

    def audio(self, data, adc):
        # At most 20 snapshots/s; a full/dead observer drops visuals, never audio.
        if self.audio_socket is None or adc < self.next_audio:
            return
        self.next_audio = adc + 0.05
        try:
            self.audio_socket.sendmsg([_AUDIO_TIME.pack(adc), data])
        except OSError:
            pass

    def close(self):
        if self.audio_socket is not None:
            self.audio_socket.close()
            self.audio_socket = None
        if self.process is not None:
            self.process.stdin.close()
            self.process.stdout.close()
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, 9)
                self.process.wait()
            self.process = None


def watch(agent_enabled, audio_fd, paths):
    """Observe key edges and evaluate volume outside the dictation process."""
    import selectors
    import signal
    import tempfile

    def terminate(*_):
        raise SystemExit

    signal.signal(signal.SIGTERM, terminate)
    packet = struct.Struct("llHHI")
    devices = []
    visual = None
    with tempfile.TemporaryDirectory(prefix="linuxwhisper-", dir=os.environ["XDG_RUNTIME_DIR"]) as directory, \
            socket.socket(socket.AF_UNIX) as server, selectors.DefaultSelector() as events, \
            socket.socket(fileno=audio_fd) as audio_channel:
        path = str(Path(directory) / "overlay.sock")
        server.bind(path)
        server.listen(1)
        try:
            for path in paths:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                devices.append(fd)
                events.register(fd, selectors.EVENT_READ, "keyboard")
            environment = dict(os.environ, LINUXWHISPER_OVERLAY_SOCKET=server.getsockname())
            visual = subprocess.Popen(
                ["quickshell", "-p", str(Path(__file__).with_name("overlay.qml"))],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=environment,
            )
            server.settimeout(4)
            connection, _ = server.accept()
            with connection:
                connection.setblocking(False)
                events.register(connection, selectors.EVENT_READ, "visual")
                events.register(sys.stdin.fileno(), selectors.EVENT_READ, "control")
                events.register(audio_channel, selectors.EVENT_READ, "audio")
                print("ready", flush=True)
                armed = False
                active = None
                pressed = 0.0
                while True:
                    for event, _ in events.select():
                        if event.data == "visual":
                            if not connection.recv(64):
                                return
                        elif event.data == "control":
                            data = os.read(event.fd, 4096)
                            if not data:
                                return
                            if b"ready\n" in data:
                                active = None
                                armed = True
                                connection.sendall(b"idle\n")
                        elif event.data == "audio":
                            snapshot = audio_channel.recv(4096)
                            if active is None or len(snapshot) <= _AUDIO_TIME.size:
                                continue
                            adc, = _AUDIO_TIME.unpack_from(snapshot)
                            if adc < pressed or not 0 <= time.monotonic() - adc <= 0.2:
                                continue
                            level = volume_level(memoryview(snapshot)[_AUDIO_TIME.size:])
                            connection.sendall(f"level:{level:.3f}\n".encode("ascii"))
                        else:
                            try:
                                data = os.read(event.fd, packet.size * 64)
                            except BlockingIOError:
                                continue
                            except OSError:
                                data = b""
                            if not data:
                                events.unregister(event.fd)
                                armed = False
                                active = None
                                connection.sendall(b"idle\n")
                                continue
                            for _, _, kind, code, value in packet.iter_unpack(data):
                                if kind == 0 and code == 3:  # SYN_DROPPED: hide stale state.
                                    armed = False
                                    active = None
                                    connection.sendall(b"idle\n")
                                if kind != 1 or code not in ((100, 62) if agent_enabled else (100,)):
                                    continue
                                if value == 1 and armed and active is None:
                                    armed = False
                                    active = code
                                    pressed = time.monotonic()
                                    connection.sendall(b"f4\n" if code == 62 else b"alt\n")
                                elif value == 0 and active == code:
                                    active = None
                                    connection.sendall(b"idle\n")
        finally:
            for fd in devices:
                os.close(fd)
            if visual is not None:
                visual.terminate()
                try:
                    visual.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    visual.kill()
                    visual.wait()


if __name__ == "__main__":
    watch(sys.argv[1] == "agent", int(sys.argv[2]), sys.argv[3:])
