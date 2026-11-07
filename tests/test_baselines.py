from __future__ import annotations

from slm.baselines.monolith import files_to_artifacts, run_monolith, single_clients
from slm.bench.catalog import TRAIN_TEMPLATES, build_plan
from slm.bench.projects import generate_balanced
from slm.contracts import ArtifactFile, DOMAINS, integrate
from slm.llm.fake import FakeClient
from slm.trace import Tracer


def test_files_are_attributed_to_tasks_by_canonical_path():
    plan = build_plan(TRAIN_TEMPLATES[0])
    files = [ArtifactFile(path="src/database/users.sql", content="CREATE TABLE users"),
             ArtifactFile(path="src/scratch/ignore_me.py", content="pass")]
    arts = files_to_artifacts(plan, files)
    t = next(t for t in plan.tasks if t.target == "users")
    assert list(arts) == [t.id]


def test_monolith_run_records_one_final_event_per_project(tmp_path):
    projects = generate_balanced(2, "dev", 0)
    tracer = Tracer(run_id="mono", trace_dir=tmp_path)
    out = run_monolith(projects, FakeClient(tracer=tracer), tracer)
    assert len(out) == 2
    finals = [e for e in tracer.events() if e.kind == "final"]
    assert len(finals) == 2
    assert all(e.mode == "monolith" for e in finals)
    assert all(e.output and e.output.startswith("fail:") for e in finals)  # one file cannot pass


def test_monolith_is_graded_with_the_same_integrator():
    plan = build_plan(TRAIN_TEMPLATES[3])
    from slm.bench.catalog import gold_artifacts

    files = [f for art in gold_artifacts(plan).values() for f in art.files]
    d = integrate("p", plan, files_to_artifacts(plan, files))
    assert d.ok, d.failures  # the full file list is exactly the specialists' output


def test_single_clients_map_every_domain_to_one_client():
    c = FakeClient()
    clients = single_clients(c)
    assert set(clients) == set(DOMAINS)
    assert all(v is c for v in clients.values())
