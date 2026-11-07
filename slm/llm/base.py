"""The one model interface: LLMClient.complete(system, user, schema) -> parsed object.

Adapters implement only _raw(). Validation, the single retry, and tracing live here,
so every backend behaves identically.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from slm.trace import Tracer

T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 2  # the first try plus one retry with the validation error appended


@dataclass
class RawResponse:
    text: str
    input_tokens: int
    output_tokens: int


class SchemaValidationFailed(RuntimeError):
    pass


class LLMClient(ABC):
    def __init__(self, model: str, tracer: Tracer | None = None):
        self.model = model
        self.tracer = tracer

    @abstractmethod
    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        """Send one request and return the model's text (expected to be JSON)."""

    def complete(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        caller: str = "user",
        callee: str = "model",
        ctx: dict | None = None,
    ) -> T:
        """ctx: extra TraceEvent fields for this call (mode, project_id, task_id, domain, adapter, ...)."""
        json_schema = schema.model_json_schema()
        prompt = user
        error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t_start = time.time()
            start = time.perf_counter()
            raw = self._raw(system, prompt, json_schema)
            latency_ms = (time.perf_counter() - start) * 1000
            times = {"t_start": t_start, "t_end": time.time()}
            try:
                parsed = schema.model_validate_json(_strip_fences(raw.text))
                error = ""
            except ValidationError as e:
                error = str(e)
            ctx_times = {**(ctx or {}), **times}
            self._trace(caller, callee, system, prompt, raw, latency_ms, attempt, error, ctx_times)
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

    async def acomplete(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        caller: str = "user",
        callee: str = "model",
        ctx: dict | None = None,
    ) -> T:
        """Async variant so sibling DAG nodes can be fired with asyncio.gather.

        This default runs the sync path in a thread. Network backends (vLLM) should
        override it with a real async request.
        """
        return await asyncio.to_thread(
            self.complete, system, user, schema, caller=caller, callee=callee, ctx=ctx
        )

    def _trace(self, caller, callee, system, prompt, raw, latency_ms, attempt, error, ctx):
        if self.tracer is None:
            return
        self.tracer.record(
            kind="llm",
            caller=caller,
            callee=callee,
            model=self.model,
            input_chars=len(system) + len(prompt),
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
            latency_ms=round(latency_ms, 1),
            attempt=attempt,
            ok=not error,
            error=error or None,
            **ctx,
        )


def _strip_fences(text: str) -> str:
    """Small models often wrap JSON in ```json fences despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()
