"""VLLMLoRAClient against a mocked transport: cold starts, retries, payloads, the shared pool."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES, build_plan, gold_artifact
from slm.bench.projects import generate_balanced
from slm.contracts import BASE_MODEL, DOMAINS, Artifact
from slm.domains import ADAPTER
from slm.llm.vllm import SPECIALIST_MAX_TOKENS, VLLMLoRAClient
from slm.pipeline.dispatch import run_plan
from slm.serve.mock import MockVLLM
from slm.trace import Tracer

ART = Artifact.model_validate({"files": [{"path": "src/database/users.sql", "content": "CREATE TABLE users ();"}],
                               "summary": "fixed"})


def _art(body: dict) -> str:  # a fixed valid artifact, for calls made outside the dispatcher
    return ART.model_dump_json()


def _project():
    return generate_balanced(1, "dev", 0)[0]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(VLLMLoRAClient, "_backoff", staticmethod(lambda n: 0.0))


def test_503_then_200_is_absorbed_async(tmp_path):
    server = MockVLLM(_art, script=[503, 503])
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    got = asyncio.run(server.client("spec-database", tracer=tracer).acomplete("sys", "user", Artifact))
    assert got == ART
    assert len(server.requests) == 3
    llm = [e for e in tracer.events() if e.kind == "llm"]
    assert len(llm) == 1 and llm[0].ok and llm[0].attempt == 1  # a transport retry is not a model attempt


def test_503_then_200_is_absorbed_sync():
    server = MockVLLM(_art, script=[503, 502, 504])
    assert server.client("spec-auth").complete("sys", "user", Artifact) == ART
    assert len(server.requests) == 4


def test_connection_errors_during_a_cold_start_are_retried():
    server = MockVLLM(_art, script=[httpx.ConnectError("refused"), httpx.ReadTimeout("booting")])
    assert asyncio.run(server.client("spec-network").acomplete("s", "u", Artifact)) == ART
    assert len(server.requests) == 3


def test_exhausted_cold_start_budget_raises(monkeypatch):
    monkeypatch.setattr(VLLMLoRAClient, "_backoff", staticmethod(lambda n: 1.0))
    server = MockVLLM(_art, script=[503] * 10)
    client = server.client("spec-frontend", cold_start_timeout_s=0.5)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.acomplete("s", "u", Artifact))
    assert len(server.requests) == 1  # the next backoff would overshoot the budget: stop at once


def test_client_errors_are_not_retried():
    server = MockVLLM(_art, script=[404])
    with pytest.raises(httpx.HTTPStatusError):
        server.client("spec-unknown").complete("s", "u", Artifact)
    assert len(server.requests) == 1


def test_cold_start_503s_do_not_turn_into_failed_tasks(tmp_path):
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    server = MockVLLM(script=[503] * 4)  # the first dependency level hits a server still booting
    shared = server.client(BASE_MODEL, tracer=tracer)
    d = asyncio.run(run_plan(p.id, p.plan, {dom: shared for dom in DOMAINS}, tracer))
    assert d.ok, d.failures
    tasks = [e for e in tracer.events() if e.kind == "task"]
    assert len(tasks) == len(p.plan.tasks) and all(e.ok for e in tasks)
    assert len(server.requests) == len(p.plan.tasks) + 4


def test_unreachable_server_is_a_task_failure_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(VLLMLoRAClient, "_backoff", staticmethod(lambda n: 1.0))
    p = _project()
    tracer = Tracer(run_id="t", trace_dir=tmp_path)
    server = MockVLLM(script=[503] * 1000)
    shared = server.client(BASE_MODEL, tracer=tracer, cold_start_timeout_s=0.5)
    d = asyncio.run(run_plan(p.id, p.plan, {dom: shared for dom in DOMAINS}, tracer))
    assert not d.ok
    tasks = [e for e in tracer.events() if e.kind == "task"]
    assert len(tasks) == len(p.plan.tasks)
    assert not any(e.ok for e in tasks) and all("HTTPStatusError" in e.output for e in tasks)
    final = [e for e in tracer.events() if e.kind == "final"][-1]
    assert final.ok and final.output.startswith("fail:")  # the run completed; the product failed


def test_payload_addresses_the_adapter_with_the_trained_budget():
    server = MockVLLM(_art)
    server.client(BASE_MODEL).for_model("spec-auth").complete("sys", "user", Artifact)
    body = server.requests[0]
    assert body["model"] == "spec-auth"
    assert body["max_tokens"] == SPECIALIST_MAX_TOKENS
    assert body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["response_format"]["json_schema"]["schema"]["title"] == "Artifact"
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}]


def test_every_gold_artifact_fits_the_default_output_budget():
    for template in [*TRAIN_TEMPLATES, *HELDOUT_TEMPLATES]:
        plan = build_plan(template)
        for task in plan.tasks:
            chars = len(gold_artifact(plan, task).model_dump_json())
            assert chars / 2 < SPECIALIST_MAX_TOKENS, (task.domain, task.kind, chars)  # pessimistic 2 chars/token


def test_for_model_siblings_share_one_connection_pool():
    server = MockVLLM(_art)
    base = server.client(BASE_MODEL)
    siblings = [base.for_model(ADAPTER[d]) for d in DOMAINS]
    assert all(s._pool is base._pool for s in siblings)
    assert [s.model for s in siblings] == [ADAPTER[d] for d in DOMAINS] and base.model == BASE_MODEL

    async def fire() -> set[int]:
        await asyncio.gather(*(s.acomplete("s", "u", Artifact) for s in siblings))
        return {id(s._pool.aclient()) for s in siblings}

    assert len(asyncio.run(fire())) == 1  # one AsyncClient per event loop, reused by every adapter
    assert sorted(server.models()) == sorted(ADAPTER.values())
