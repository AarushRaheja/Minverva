from __future__ import annotations

import json
from pathlib import Path

from slm.bench.build import build_all, domain_examples, load_projects
from slm.bench.projects import generate_balanced
from slm.contracts import DOMAINS, Artifact, Project, TrainExample
from slm.trace import Tracer


def test_build_writes_every_split_and_domain(tmp_path):
    man = build_all(root=str(tmp_path), scale=0.1)
    assert man["data_version"] >= 1
    for split in ("train", "dev", "test"):
        path = tmp_path / "data" / "projects" / f"{split}.jsonl"
        assert path.exists()
        rows = [json.loads(x) for x in path.read_text().splitlines() if x]
        assert rows and all(Project.model_validate(r).plan for r in rows)
    for d in DOMAINS:
        lines = (tmp_path / "data" / "domains" / f"{d}.jsonl").read_text().splitlines()
        assert lines
        for line in lines:
            ex = TrainExample.model_validate_json(line)
            assert ex.domain == d
            Artifact.model_validate_json(ex.completion)
    assert set(man["domains"]) == set(DOMAINS)
    assert (tmp_path / "data" / "manager" / "train.jsonl").exists()


def test_domain_examples_use_the_right_split_labels():
    train = generate_balanced(2, "train", 0)
    ex = domain_examples(train, "train")
    assert all(e.split == "train" for v in ex.values() for e in v)
    assert sum(len(v) for v in ex.values()) == sum(len(p.plan.tasks) for p in train)


def test_load_projects_round_trips(tmp_path):
    build_all(root=str(tmp_path), scale=0.1)
    got = load_projects("dev", root=str(tmp_path))
    assert got and all(p.plan is not None for p in got)


def test_manifest_counts_match_the_files(tmp_path):
    man = build_all(root=str(tmp_path), scale=0.1)
    train = load_projects("train", root=str(tmp_path))
    for d in DOMAINS:
        n = sum(1 for p in train for t in p.plan.tasks if t.domain == d)
        assert man["domains"][d]["train"] == n
    assert man["projects"]["train"]["total"] == len(train)


def test_gate_accepts_gold_artifacts_and_rejects_wrong_paths():
    from slm.bench.catalog import build_plan, gold_artifact, TRAIN_TEMPLATES
    from slm.bench.score import gate_ok

    plan = build_plan(TRAIN_TEMPLATES[0])
    for t in plan.tasks:
        assert gate_ok(t.domain, t.kind, t.target, gold_artifact(plan, t))
    t = plan.tasks[0]
    bad = Artifact(files=[{"path": "src/nope.sql", "content": "CREATE TABLE users"}])  # type: ignore[arg-type]
    assert not gate_ok(t.domain, t.kind, t.target, bad)


def test_trace_round_trip(tmp_path: Path):
    tr = Tracer(run_id="r", trace_dir=tmp_path)
    tr.record(kind="final", caller="x", callee="y", output="pass", project_id="p")
    ev = tr.events()
    assert ev[0].kind == "final" and ev[0].output == "pass"


def test_build_writes_nested_rows_that_compile_to_the_gold_plans(tmp_path):
    from slm.manager.spec import SPEC_SYSTEM, ProjectSpec, to_plan

    man = build_all(root=str(tmp_path), scale=0.05)
    train = load_projects("train", root=str(tmp_path))
    lines = (tmp_path / "data" / "manager" / "spec-train.jsonl").read_text().splitlines()
    assert len(lines) == len(train) == man["manager"]["spec_train"]
    for line, p in zip(lines, train, strict=True):
        row = json.loads(line)
        assert row["system"] == SPEC_SYSTEM and p.description in row["prompt"]
        assert to_plan(ProjectSpec.model_validate_json(row["completion"])) == p.plan
    assert (tmp_path / "data" / "manager" / "spec-dev.jsonl").exists()


def test_built_splits_have_distinct_briefs_and_do_not_overlap(tmp_path):
    man = build_all(root=str(tmp_path), scale=0.1)
    briefs = {s: {p.description for p in load_projects(s, root=str(tmp_path))} for s in ("train", "dev", "test")}
    for s, b in briefs.items():
        assert len(b) == man["projects"][s]["total"] == man["projects"][s]["distinct_briefs"]
    assert not briefs["train"] & briefs["dev"] and not briefs["train"] & briefs["test"]
