"""The one place a local model is called."""

from __future__ import annotations

import os

import httpx


class ModelUnavailable(RuntimeError):
    pass


class OllamaChat:
    """Temperature and seed are sent on every call; the trial manifest records them."""

    def __init__(self, model: str, *, host: str | None = None, temperature: float = 0.0, seed: int = 0,
                 max_output_tokens: int = 2048, num_ctx: int = 8192, timeout_s: float = 600.0, transport=None):
        # The same variable the custom agent reads, so both agents always reach the same server.
        self.model, self.host = model, (host or os.environ.get("SLM_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.options = {"temperature": temperature, "seed": seed, "num_predict": max_output_tokens, "num_ctx": num_ctx}
        self.client = httpx.Client(timeout=timeout_s, transport=transport)

    def chat(self, messages: list[dict], json_mode: bool = True) -> dict:
        body = {"model": self.model, "messages": messages, "stream": False, "think": False, "keep_alive": "30m", "options": self.options,
                **({"format": "json"} if json_mode else {})}
        try:
            r = self.client.post(f"{self.host}/api/chat", json=body)
            r.raise_for_status()
            d = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ModelUnavailable(f"{type(e).__name__}: {e}") from e
        return {"text": (d.get("message") or {}).get("content") or "", "tok_in": d.get("prompt_eval_count", 0),
                "tok_out": d.get("eval_count", 0)}

    def version(self) -> str | None:
        try:
            return self.client.get(f"{self.host}/api/version").json().get("version")
        except (httpx.HTTPError, ValueError):
            return None

    def digest(self) -> str | None:
        """The exact weights, so a re-pulled model under the same name is visible in the manifest."""
        try:
            for m in self.client.get(f"{self.host}/api/tags").json().get("models", []):
                if m.get("name") == self.model:
                    return m.get("digest")
        except (httpx.HTTPError, ValueError):
            pass
        return None
