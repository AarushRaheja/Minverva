"""Backend selection and per-role model names.

Roles: manager, database, auth, network, frontend (one LoRA adapter per domain), monolith.

Environment overrides:
  SLM_BACKEND=fake|vllm           (default: fake)
  SLM_MODEL=<name>                default base model for every role
  SLM_MODEL_<ROLE>=<name>         pin one role, e.g. SLM_MODEL_MANAGER=Qwen/Qwen3-1.7B
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from slm.contracts import BASE_MODEL, DOMAINS, MANAGER_BASE
from slm.domains import ADAPTER
from slm.llm.base import LLMClient
from slm.trace import Tracer

ROLES: tuple[str, ...] = ("manager", *DOMAINS, "monolith")

DEFAULT_MODELS = {
    "fake": "fake",
    "vllm": BASE_MODEL,
}


@dataclass
class Config:
    backend: str = "fake"
    models: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Config:
        backend = os.environ.get("SLM_BACKEND", "fake")
        if backend not in DEFAULT_MODELS:
            raise ValueError(f"SLM_BACKEND must be one of {sorted(DEFAULT_MODELS)}, got {backend!r}")
        default = os.environ.get("SLM_MODEL", DEFAULT_MODELS[backend])
        models = {role: os.environ.get(f"SLM_MODEL_{role.upper()}", default) for role in ROLES}
        return cls(backend=backend, models=models)

    def client(self, role: str, tracer: Tracer | None = None) -> LLMClient:
        """A client addressed at `role`. Domain roles are served by that domain's LoRA adapter."""
        model = self.models.get(role, DEFAULT_MODELS[self.backend])
        if self.backend == "fake":
            from slm.llm.fake import FakeClient

            return FakeClient(tracer=tracer, model=model)
        if self.backend == "vllm":
            from slm.llm.vllm import VLLMLoRAClient

            name = ADAPTER[role] if role in ADAPTER else (MANAGER_BASE if role == "manager" else model)
            return VLLMLoRAClient(name, tracer=tracer)
        raise NotImplementedError(f"backend {self.backend!r}")

    def specialists(self, tracer: Tracer | None = None) -> dict[str, LLMClient]:
        """The four domain clients, one per specialist adapter."""
        return {d: self.client(d, tracer) for d in DOMAINS}
