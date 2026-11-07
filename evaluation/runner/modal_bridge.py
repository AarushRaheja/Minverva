"""A local Ollama-shaped server that forwards to the Modal app, so agents need no code changes. It listens on
localhost only, and it is the one route to the GPU, so the spend check here covers every model call."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from evaluation.runner.spend import SpendGuard

ALLOWED = ("/api/chat",)
CACHED = ("/api/version", "/api/tags")  # asked once, so a status check doesn't wake a GPU every time


def modal_forwarder(app_name: str) -> Callable[[str, bytes | None], tuple[int, bytes]]:
    import modal

    server = modal.Cls.from_name(app_name, "Server")()
    return lambda path, body: tuple(server.request.remote(path, body))


class Bridge:
    def __init__(self, guard: SpendGuard, forward: Callable[[str, bytes | None], tuple[int, bytes]], port: int = 0):
        self.guard, self.forward = guard, forward
        self.cache: dict[str, tuple[int, bytes]] = {}
        self.calls = 0
        self.refused = 0
        self.tripped: str | None = None
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, data: bytes):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, body: bytes | None):
                code, data = bridge.handle(self.path, body)
                self._send(code, data)

            def do_GET(self):
                self._handle(None)

            def do_POST(self):
                self._handle(self.rfile.read(int(self.headers.get("Content-Length", 0))))

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def handle(self, path: str, body: bytes | None) -> tuple[int, bytes]:
        if path == "/spend":
            return 200, json.dumps(self.guard.status()).encode()
        if path not in (*ALLOWED, *CACHED):
            return 404, b'{"error":"not forwarded"}'
        if path in self.cache:
            return self.cache[path]
        why = self.guard.blocked()
        if why:  # a 503 reads as an outage: the trial is recorded as not attempted, never as the model failing
            self.tripped = why
            self.refused += 1
            return 503, json.dumps({"error": why}).encode()
        try:
            self.calls += 1
            code, data = self.forward(path, body)
        except Exception as e:  # noqa: BLE001 - any failure reaching Modal is an outage for the caller
            return 503, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()
        if path in CACHED and code == 200:
            self.cache[path] = (code, data)
        return code, data

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def digest_problem(tags: bytes, cfg: dict) -> str | None:
    """Different weights under the same name would quietly change the experiment."""
    for m in json.loads(tags).get("models", []):
        if m.get("name") == cfg["model"]:
            return None if str(m.get("digest", "")).startswith(cfg["digest_prefix"]) else f"Modal has {m.get('digest', '')[:12]}, expected {cfg['digest_prefix']}"
    return f"{cfg['model']} isn't on the Modal server"
