"""Ollama client (local models, $0): native /api/chat with JSON-schema constrained output.

Thinking is turned off (`think: false`) and decoding is greedy, so runs are reproducible and every
architecture sees the same model behaviour. Env: SLM_OLLAMA_URL (default http://127.0.0.1:11434).
"""

from __future__ import annotations

import json
import os

import httpx

from slm.llm.base import LLMClient, RawResponse
from slm.llm.cli import BackendUnavailable
from slm.trace import Tracer


class OllamaClient(LLMClient):
    def __init__(self, model: str = "qwen3.5:4b", tracer: Tracer | None = None, *, base_url: str | None = None,
                 num_predict: int = 1536, num_ctx: int = 8192, timeout_s: float = 1800.0,
                 transport: httpx.BaseTransport | None = None):
        super().__init__(model, tracer)
        self.base_url = (base_url or os.environ.get("SLM_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.num_predict = num_predict
        self.num_ctx = num_ctx
        self._http = httpx.Client(timeout=timeout_s, transport=transport)

    def payload(self, system: str, user: str, json_schema: dict) -> dict:
        return {
            "model": self.model, "stream": False, "think": False, "format": json_schema,
            "keep_alive": "30m",
            "options": {"temperature": 0, "seed": 0, "num_predict": self.num_predict, "num_ctx": self.num_ctx},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }

    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        try:
            r = self._http.post(f"{self.base_url}/api/chat", json=self.payload(system, user, json_schema))
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendUnavailable(f"ollama: {type(e).__name__}: {e}") from e
        data = r.json()
        text = data["message"]["content"]
        # A schema-constrained reply that stopped by itself is always valid JSON. If it isn't, the server is
        # ignoring `format` (Homebrew's 0.31.1 did), which would be scored as model failures.
        if data.get("done_reason") == "stop" and not _is_json(text):
            raise BackendUnavailable(f"ollama server is not enforcing the JSON schema: {self.server_version()}")
        return RawResponse(text, int(data.get("prompt_eval_count", 0)), int(data.get("eval_count", 0)))

    def server_version(self) -> str:
        try:
            return self._http.get(f"{self.base_url}/api/version").json().get("version", "unknown")
        except (httpx.HTTPError, ValueError):
            return "unknown"


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True
