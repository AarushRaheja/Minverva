"""Smoke measurements against a live slm-serve server (one multi-LoRA vLLM deployment).

Measures what the architecture lives or dies on: four adapters answering one dependency level
at once versus the same tasks one after another, plus the per-adapter warm latency.

  python -m slm.serve.smoke <url>
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

from slm.bench.catalog import build_plan
from slm.bench.catalog import TRAIN_TEMPLATES
from slm.contracts import DOMAINS, Artifact, BASE_MODEL
from slm.llm.base import SchemaValidationFailed
from slm.llm.vllm import VLLMLoRAClient
from slm.pipeline.dispatch import run_plan
from slm.trace import Tracer

PLAN = build_plan(TRAIN_TEMPLATES[0])


def _clients(url: str, tracer: Tracer) -> dict:
    c = VLLMLoRAClient(BASE_MODEL, tracer=tracer, base_url=url, cold_start_timeout_s=900)
    return {d: c for d in DOMAINS}  # one client per domain; for_model() addresses the adapter


async def _timed_dispatch(url: str, parallel: bool) -> dict:
    tracer = Tracer(run_id=f"smoke-{'par' if parallel else 'ser'}", trace_dir=Path(tempfile.mkdtemp()))
    t = time.perf_counter()
    result = await run_plan("smoke", PLAN, _clients(url, tracer), tracer, mode="specialists",
                            parallel=parallel)
    wall = time.perf_counter() - t
    events = tracer.events()
    return {
        "wall_s": round(wall, 3),
        "calls": sum(1 for e in events if e.kind == "llm"),
        "retries": sum(1 for e in events if e.kind == "llm" and e.attempt > 1),  # inflate wall_s
        "tasks_ok": sum(1 for e in events if e.kind == "task" and e.ok),
        "tasks_total": sum(1 for e in events if e.kind == "task"),
        "checks_failed": result.failures,
    }


async def _run(url: str) -> dict:
    client = VLLMLoRAClient(BASE_MODEL, base_url=url, cold_start_timeout_s=900)
    trace_dir = Path(tempfile.mkdtemp())
    out: dict = {}
    for d in DOMAINS:  # first touch loads the adapter (and, for the first domain, wakes the server)
        out[f"first_{d}_s"] = round(await _one(client, d, trace_dir), 3)
        warm = [await _one(client, d, trace_dir) for _ in range(4)]
        out[f"warm_{d}_s"] = round(statistics.median(warm), 3)
    # all four adapters are loaded now; the first one is still warm unless the server evicted it
    out[f"rewarm_{DOMAINS[0]}_s"] = round(await _one(client, DOMAINS[0], trace_dir), 3)
    out["parallel"] = await _timed_dispatch(url, True)
    out["serial"] = await _timed_dispatch(url, False)
    p, s = out["parallel"]["wall_s"], out["serial"]["wall_s"]
    out["parallel_speedup"] = round(s / p, 2) if p else None
    return out


async def _one(client: VLLMLoRAClient, domain: str, trace_dir: Path) -> float:
    """Seconds for one request to `domain`'s adapter: the first attempt only, so a validation retry
    on an untrained adapter does not double the number."""
    from slm.contracts import specialist_prompt, specialist_system

    task = next(t for t in PLAN.tasks if t.domain == domain)
    sibling = client.for_model(task.adapter_name)
    sibling.tracer = Tracer(trace_dir=trace_dir)
    try:
        await sibling.acomplete(specialist_system(task.domain), specialist_prompt(PLAN, task), Artifact)
    except SchemaValidationFailed:
        pass  # an untrained adapter still proves the latency
    first = next(e for e in sibling.tracer.events() if e.kind == "llm" and e.attempt == 1)
    return first.latency_ms / 1000


def run_smoke(url: str) -> dict:
    return asyncio.run(_run(url))


if __name__ == "__main__":
    print(json.dumps(run_smoke(sys.argv[1]), indent=2))
