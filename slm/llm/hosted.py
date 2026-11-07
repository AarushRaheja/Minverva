"""Anthropic adapter (teacher plans + Haiku-class baseline). `anthropic` is imported lazily.

Single calls use Messages (via LLMClient.complete). Bulk work uses the Message Batches API:
`complete_batch` submits, polls, and returns parsed objects (None where validation failed).
Needs ANTHROPIC_API_KEY; install with `uv sync --group teacher`.
"""

from __future__ import annotations

import json
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from slm.llm.base import LLMClient, RawResponse, _strip_fences
from slm.trace import Tracer

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-haiku-5-5"  # Haiku 4.5 is deprecated
MAX_TOKENS = 2048


def _sdk(api_key: str | None = None):
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("anthropic is not installed: run `uv sync --group teacher`") from e
    return anthropic.Anthropic(api_key=api_key)


def _system_with_schema(system: str, json_schema: dict) -> str:
    return f"{system}\n\nReply with ONLY a JSON object matching this JSON Schema:\n{json.dumps(json_schema)}"


def _text(message) -> str:
    return "".join(b.text for b in message.content if getattr(b, "type", "") == "text")


class AnthropicClient(LLMClient):
    def __init__(self, model: str = DEFAULT_MODEL, tracer: Tracer | None = None, sdk=None):
        super().__init__(model, tracer)
        self._sdk_client = sdk

    @property
    def sdk(self):
        if self._sdk_client is None:
            self._sdk_client = _sdk()
        return self._sdk_client

    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:
        msg = self.sdk.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=_system_with_schema(system, json_schema),
            messages=[{"role": "user", "content": user}],
        )
        return RawResponse(_text(msg), msg.usage.input_tokens, msg.usage.output_tokens)

    def complete_batch(
        self,
        requests: list[tuple[str, str]],
        schema: type[T],
        *,
        poll_seconds: float = 30.0,
        sleep=time.sleep,
    ) -> list[T | None]:
        """Bulk-complete [(system, user), ...] with the Batches API (50% cheaper, async).

        One attempt per request (no retry loop); results come back in input order, None on failure.
        """
        json_schema = schema.model_json_schema()
        reqs = [
            {
                "custom_id": f"r{i}",
                "params": {
                    "model": self.model,
                    "max_tokens": MAX_TOKENS,
                    "temperature": 0,
                    "system": _system_with_schema(system, json_schema),
                    "messages": [{"role": "user", "content": user}],
                },
            }
            for i, (system, user) in enumerate(requests)
        ]
        batch = self.sdk.messages.batches.create(requests=reqs)
        while batch.processing_status != "ended":
            sleep(poll_seconds)
            batch = self.sdk.messages.batches.retrieve(batch.id)
        out: dict[str, T | None] = {}
        for item in self.sdk.messages.batches.results(batch.id):
            parsed = None
            if item.result.type == "succeeded":
                try:
                    parsed = schema.model_validate_json(_strip_fences(_text(item.result.message)))
                except ValidationError:
                    parsed = None
            out[item.custom_id] = parsed
        return [out.get(f"r{i}") for i in range(len(requests))]
