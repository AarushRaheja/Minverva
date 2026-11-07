"""The local model on a Modal GPU (app `slm-ollama`), so repeated experiments don't tie up the laptop.

  uv run modal deploy modal_apps/ollama_app.py
  uv run python -m evaluation modal-check               # one call, checks the weights and the spend limit
  uv run python -m evaluation run functional-gate       # the bridge starts itself

It has no web endpoint, so only your Modal login can reach it. Use it through evaluation/runner/modal_bridge.py, which
checks the spend limit before every call. At most one container runs, and it shuts down 2 minutes after its last call,
so a deployed app with nothing to do costs nothing.
"""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request

import modal

OLLAMA_VERSION = "0.40.14"  # older servers ignore JSON schemas (see slm/llm/ollama.py)
MODEL = "qwen3.5:4b"
PORT = 11434
URL = f"http://127.0.0.1:{PORT}"
RELEASE = f"https://github.com/ollama/ollama/releases/download/v{OLLAMA_VERSION}/ollama-linux-amd64.tar.zst"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "zstd", "ca-certificates")
    .run_commands(
        f"curl -fsSL {RELEASE} | tar --zstd -x -C /usr",
        f"sh -c 'OLLAMA_MODELS=/models ollama serve & sleep 5; OLLAMA_MODELS=/models ollama pull {MODEL}; kill %1 || true'",
    )
    .env({"OLLAMA_MODELS": "/models", "OLLAMA_HOST": f"127.0.0.1:{PORT}", "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_KEEP_ALIVE": "30m"})
)
app = modal.App("slm-ollama")


def _call(path: str, body: bytes | None = None, timeout: float = 1740.0) -> tuple[int, bytes]:
    req = urllib.request.Request(URL + path, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@app.cls(image=image, gpu="L4", cpu=4, memory=16384, min_containers=0, max_containers=1, scaledown_window=120, timeout=1800)
@modal.concurrent(max_inputs=16)  # calls wait in Ollama's queue, one at a time, as they do on the laptop
class Server:
    @modal.enter()
    def start(self):
        self.proc = subprocess.Popen(["ollama", "serve"])
        for _ in range(120):
            try:
                if _call("/api/version", timeout=2)[0] == 200:
                    return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("ollama didn't start")

    @modal.exit()
    def stop(self):
        self.proc.terminate()

    @modal.method()
    def request(self, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        return _call(path, body)
