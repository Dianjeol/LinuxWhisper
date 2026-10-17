"""Isolated recording indicator: key edges only, never audio or release-path IPC."""
import os
from pathlib import Path
import select
import subprocess
import sys


class Overlay:
    """Prepare the optional visual process before microphone/WebSocket readiness."""

    def __init__(self, devices, agent_enabled):
        self.process = None
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("DEEPGRAM_API_KEY", "OPENROUTER_API_KEY")}
        command = [sys.executable, str(Path(__file__).resolve()),
                   "agent" if agent_enabled else "dictation", *(device.path for device in devices)]
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=environment, start_new_session=True,
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

    def close(self):
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


def watch(agent_enabled, paths):
    """Observe independent evdev readers; the main app arms each available take."""
    import selectors
    import signal
    import socket
    import struct
    import tempfile

    def terminate(*_):
        raise SystemExit

    signal.signal(signal.SIGTERM, terminate)
    packet = struct.Struct("llHHI")
    devices = []
    visual = None
    with tempfile.TemporaryDirectory(prefix="linuxwhisper-", dir=os.environ["XDG_RUNTIME_DIR"]) as directory, \
            socket.socket(socket.AF_UNIX) as server, selectors.DefaultSelector() as events:
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
                print("ready", flush=True)
                armed = False
                active = None
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
    watch(sys.argv[1] == "agent", sys.argv[2:])
