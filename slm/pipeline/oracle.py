"""OracleSpecialist: answers every dispatched task with its gold artifact (slm.bench.catalog).

With a gold plan the pipeline must score 100% end to end, which is the integration test for the
contracts (`integrate` + `check_task`) and the fallback for measuring latency without model error.

The dispatcher publishes the (plan, task) being served through the CALL contextvar, not through
the trace ctx, because contextvars propagate into asyncio tasks and into threads.
"""

from __future__ import annotations

import time
from contextvars import ContextVar

from slm.bench.catalog import gold_artifact
from slm.contracts import Artifact, ProjectPlan, Task
from slm.llm.base import LLMClient, RawResponse

CALL: ContextVar[tuple[ProjectPlan, Task] | None] = ContextVar("slm_pipeline_call", default=None)


class OracleSpecialist(LLMClient):
    def __init__(self, tracer=None, model: str = "oracle"):
        super().__init__(model, tracer)

    def _raw(self, system: str, user: str, json_schema: dict) -> RawResponse:  # pragma: no cover
        raise NotImplementedError("OracleSpecialist is driven by the dispatcher's CALL contextvar")

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        call = CALL.get()
        if call is None:
            raise RuntimeError("OracleSpecialist needs a dispatcher-set CALL context")
        plan, task = call
        t0 = time.time()
        artifact = gold_artifact(plan, task)
        if schema is not Artifact:  # be loud rather than silently answering the wrong question
            raise RuntimeError(f"OracleSpecialist answers Artifact, not {schema.__name__}")
        return self._trace_and_return(artifact, system, user, caller, callee, ctx, t0)

    def _trace_and_return(self, artifact: Artifact, system, user, caller, callee, ctx, t0):
        text = artifact.model_dump_json()
        self._trace(caller, callee, system, user, RawResponse(text, 0, 0), 0.0, 1, "",
                    {**(ctx or {}), "t_start": t0, "t_end": time.time()})
        return artifact
