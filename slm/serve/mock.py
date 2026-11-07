"""In-process stand-in for the slm-serve vLLM server, so VLLMLoRAClient runs end to end offline.

It answers /v1/chat/completions over an httpx.MockTransport. By default the answer is the gold
artifact of the task being dispatched (read from the dispatcher's CALL contextvar, like the oracle
specialist), so a gold plan integrates green through the real client, payloads and retries.
`script` serves statuses or exceptions to the first requests, e.g. [503, 503] for a cold start.
"""

from __future__ import annotations

import json
import threading
from typing import Callable

import httpx

from slm.bench.catalog import gold_artifact
from slm.llm.vllm import VLLMLoRAClient
from slm.pipeline.oracle import CALL

BASE_URL = "http://slm-serve.test"
Answer = Callable[[dict], str]  # request body -> message content


def gold_answer(body: dict) -> str:
    call = CALL.get()
    if call is None:
        raise RuntimeError("gold_answer needs a dispatcher-set CALL context; pass answer= instead")
    return gold_artifact(*call).model_dump_json()


class MockVLLM:
    def __init__(self, answer: Answer = gold_answer, *, script: list[int | Exception] | None = None):
        self.answer = answer
        self.script = list(script or [])
        self.requests: list[dict] = []  # every request body, in arrival order (failed ones too)
        self._lock = threading.Lock()
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        with self._lock:
            self.requests.append(body)
            step = self.script.pop(0) if self.script else None
        if isinstance(step, Exception):
            raise step
        if step is not None:
            return httpx.Response(step, json={"error": f"scripted {step}"})
        text = self.answer(body)
        usage = {"prompt_tokens": len(json.dumps(body["messages"])) // 4, "completion_tokens": len(text) // 4}
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}], "usage": usage})

    def client(self, model: str, **kw) -> VLLMLoRAClient:
        return VLLMLoRAClient(model, base_url=BASE_URL, transport=self.transport,
                              async_transport=self.transport, **kw)

    def models(self) -> list[str]:
        return [b["model"] for b in self.requests]
