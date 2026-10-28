"""Local-only newline-delimited JSON receiver for Level Archaeologist.

The bridge accepts snapshots from a game-side mod/debug exporter. It does not
inspect another process' memory or inject code into a game.
"""
from __future__ import annotations

import json
import socket
import threading
from typing import Any, Callable

HOST = "127.0.0.1"
PORT = 47831
MAX_LINE_BYTES = 8 * 1024 * 1024


def normalize_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a snapshot to center/size object records."""
    if not isinstance(payload, dict):
        raise ValueError("Snapshot root must be a JSON object")
    raw_objects = payload.get("objects", [])
    if not isinstance(raw_objects, list):
        raise ValueError("'objects' must be a list")

    objects = []
    for index, obj in enumerate(raw_objects):
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name", f"Object_{index + 1}"))[:200]
        kind = str(obj.get("type", "unknown"))[:80]
        if isinstance(obj.get("bounds"), list) and len(obj["bounds"]) == 2:
            lo, hi = obj["bounds"]
            if not (isinstance(lo, list) and isinstance(hi, list)
                    and len(lo) >= 3 and len(hi) >= 3):
                continue
            try:
                minimum = [float(lo[i]) for i in range(3)]
                maximum = [float(hi[i]) for i in range(3)]
            except (TypeError, ValueError):
                continue
            position = [(minimum[i] + maximum[i]) / 2 for i in range(3)]
            size = [abs(maximum[i] - minimum[i]) for i in range(3)]
        else:
            try:
                position = [float(v) for v in obj.get("position", [0, 0, 0])[:3]]
                size = [abs(float(v)) for v in obj.get("size", [100, 100, 100])[:3]]
            except (TypeError, ValueError):
                continue
            if len(position) != 3 or len(size) != 3:
                continue
        if not all(abs(v) < 1e9 for v in position + size):
            continue
        objects.append({
            "name": name,
            "type": kind,
            "position": position,
            "size": size,
        })

    return {
        "name": str(payload.get("name", "Runtime capture"))[:200],
        "units": str(payload.get("units", "cm"))[:30],
        "source": str(payload.get("source", "runtime bridge"))[:100],
        "objects": objects,
    }


class RuntimeBridge:
    """TCP snapshot receiver bound to loopback only."""

    def __init__(
        self,
        on_snapshot: Callable[[dict], None],
        on_status: Callable[[str], None] | None = None,
        host: str = HOST,
        port: int = PORT,
    ):
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("Runtime bridge may only bind to localhost")
        self.on_snapshot = on_snapshot
        self.on_status = on_status or (lambda _message: None)
        self.host = "127.0.0.1" if host == "localhost" else host
        self.port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._sock is not None

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((self.host, self.port))
            server.listen(4)
            server.settimeout(0.5)
        except Exception:
            server.close()
            raise
        self._sock = server
        self._thread = threading.Thread(
            target=self._serve, args=(server,), daemon=True
        )
        self._thread.start()
        self.on_status(f"Runtime bridge listening on {self.host}:{self.port}")

    def stop(self) -> None:
        self._stop.set()
        server, self._sock = self._sock, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        self.on_status("Runtime bridge stopped")

    def _serve(self, server: socket.socket) -> None:
        while not self._stop.is_set():
            try:
                conn, address = server.accept()
            except (socket.timeout, OSError):
                continue
            with conn:
                if address[0] not in ("127.0.0.1", "::1") and not address[0].startswith("127."):
                    self.on_status(f"Rejected non-local peer: {address[0]}")
                    continue
                conn.settimeout(2.0)
                buffer = b""
                try:
                    while not self._stop.is_set():
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        buffer += chunk
                        if len(buffer) > MAX_LINE_BYTES and b"\n" not in buffer:
                            raise ValueError("Snapshot exceeds 8 MiB")
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            if not line.strip():
                                continue
                            if len(line) > MAX_LINE_BYTES:
                                raise ValueError("Snapshot exceeds 8 MiB")
                            payload = json.loads(line.decode("utf-8"))
                            snapshot = normalize_snapshot(payload)
                            self.on_snapshot(snapshot)
                            reply = {"ok": True, "objects": len(snapshot["objects"])}
                            conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    self.on_status(f"Runtime snapshot error: {exc}")
