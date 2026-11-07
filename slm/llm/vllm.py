"""Client for the vLLM multi-LoRA OpenAI-compatible server (modal_apps/serve_app.py).

`model` is an adapter name (loaded on first request by the server's LoRA resolver) or the base
model name for no adapter. Env: SLM_VLLM_URL (base URL, e.g. https://x--slm-serve-serve.modal.run).
Enable it from config with SLM_BACKEND=vllm via `make_client` (the orchestrator hooks it in).
`for_model(adapter)` returns a sibling client for another adapter that shares the connection pool.
"""

from __future__ import annotations

import asyncio
import copy
import os
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from slm.llm.base import MAX_ATTEMPTS, LLMClient, RawResponse, SchemaValidationFailed, _strip_fences
from slm.trace import Tracer

T = TypeVar("T", bound=BaseModel)

RETRY_STATUS = {502, 503, 504}  # server (re)starting or scaled to zero
# Output budget for one specialist artifact: the same 768 tokens the trainer gates with
# (modal_apps/train_app.py, _eval_gate). Gold artifacts are at most ~450 tokens.
SPECIALIST_MAX_TOKENS = 768
RETRYABLE_EXC = (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError)


class _Pool:
    """HTTP clients shared by sibling clients (one per adapter name)."""

    def __init__(self, timeout, transport, async_transport):
        self.timeout = timeout
        self.sync = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)
        self.async_transport = async_transport
        self._async: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None

    def aclient(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._async is None or self._async[0] is not loop:  # pooled per event loop
            client = httpx.AsyncClient(
                timeout=self.timeout, transport=self.async_transport, follow_redirects=True,
                limits=httpx.Limits(max_connections=256, max_keepalive_connections=64),
            )
            self._async = (loop, client)
        return self._async[1]


class VLLMLoRAClient(LLMClient):
    def __init__(
        self,
        model: str,
        tracer: Tracer | None = None,
        base_url: str | None = None,
        *,
        max_tokens: int = SPECIALIST_MAX_TOKENS,
        request_timeout_s: float = 120.0,
        cold_start_timeout_s: float = 600.0,  # total budget for 503/connection retries
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ):
        super().__init__(model, tracer)
        url = base_url or os.environ.get("SLM_VLLM_URL")
        if not url:
            raise ValueError("set SLM_VLLM_URL or pass base_url")
        self.base_url = url.rstrip("/")
        self.max_tokens = max_tokens
        self.cold_start_timeout_s = cold_start_timeout_s
        self._pool = _Pool(httpx.Timeout(request_timeout_s, connect=30.0), transport, async_transport)

    def for_model(self, model: str) -> VLLMLoRAClient:
        sibling = copy.copy(self)
        sibling.model = model
        return sibling

    # --- request building / parsing ---
    def _payload(self, system: str, user: str, json_schema: dict) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": json_schema.get("title", "Schema"), "schema": json_schema},
            },
            "chat_template_kwargs": {"enable_thinking": False},
        }

    @staticmethod
    def _parse(data: dict) -> RawResponse:
        usage = data.get("usage") or {}
        return RawResponse(
            data["choices"][0]["message"]["content"] or "",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    @staticmethod
    def _backoff(n: int) -> float:
        return min(1.0 * 2**n, 10.0)

    # --- sync ---
    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        payload = self._payload(system, user, json_schema)
        deadline = time.monotonic() + self.cold_start_timeout_s
        n = 0
        while True:
            try:
                r = self._pool.sync.post(f"{self.base_url}/v1/chat/completions", json=payload)
                if r.status_code not in RETRY_STATUS:
                    r.raise_for_status()
                    return self._parse(r.json())
                err: Exception = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            except RETRYABLE_EXC as e:
                err = e
            if time.monotonic() + self._backoff(n) > deadline:
                raise err
            time.sleep(self._backoff(n))
            n += 1

    # --- async ---
    async def _araw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        payload = self._payload(system, user, json_schema)
        client = self._pool.aclient()
        deadline = time.monotonic() + self.cold_start_timeout_s
        n = 0
        while True:
            try:
                r = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                if r.status_code not in RETRY_STATUS:
                    r.raise_for_status()
                    return self._parse(r.json())
                err: Exception = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            except RETRYABLE_EXC as e:
                err = e
            if time.monotonic() + self._backoff(n) > deadline:
                raise err
            await asyncio.sleep(self._backoff(n))
            n += 1

    async def acomplete(
        self, system: str, user: str, schema: type[T], *,
        caller: str = "user", callee: str = "model", ctx: dict | None = None,
    ) -> T:
        """Same semantics as LLMClient.complete (validate, one retry with the error, trace)."""
        json_schema = schema.model_json_schema()
        prompt = user
        error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t_start = time.time()
            start = time.perf_counter()
            raw = await self._araw(system, prompt, json_schema)
            latency_ms = (time.perf_counter() - start) * 1000
            times = {"t_start": t_start, "t_end": time.time()}
            try:
                parsed = schema.model_validate_json(_strip_fences(raw.text))
                error = ""
            except ValidationError as e:
                error = str(e)
            self._trace(caller, callee, system, prompt, raw, latency_ms, attempt, error, {**(ctx or {}), **times})
            if not error:
                return parsed
            prompt = (
                f"{user}\n\nYour previous response failed validation:\n{error}\n\n"
                f"Previous response:\n{raw.text}\n\n"
                "Return ONLY a JSON object that matches the schema."
            )
        raise SchemaValidationFailed(
            f"{callee} returned invalid {schema.__name__} after {MAX_ATTEMPTS} attempts:\n{error}"
        )


def make_client(model: str | None = None, tracer: Tracer | None = None) -> VLLMLoRAClient:
    """Factory for SLM_BACKEND=vllm (the orchestrator wires this into slm/config.py)."""
    from slm.contracts import BASE_MODEL

    return VLLMLoRAClient(model or BASE_MODEL, tracer)
