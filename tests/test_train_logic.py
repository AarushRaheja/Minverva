from __future__ import annotations

import pytest

from slm.bench.build import build_all
from slm.contracts import DOMAINS
from slm.train import logic
from slm.train.jobs import chunk, job_for, jobs


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    man = build_all(root=str(root), scale=0.1)
    return root, man


def test_one_job_per_domain():
    js = jobs(seed=3)
    assert [j.domain for j in js] == list(DOMAINS)
    assert len({j.adapter_name for j in js}) == len(DOMAINS)
    assert all(j.seed == 3 for j in js)


def test_load_examples_reads_only_its_domain(data):
    root, _ = data
    train, ev = logic.load_examples(job_for("auth"), str(root / "data" / "domains" / "{name}.jsonl"))
    assert train and ev
    assert all(e.domain == "auth" for e in train + ev)
    assert {e.split for e in train} == {"train"} and {e.split for e in ev} == {"eval"}


def test_missing_file_raises_unless_allowed(tmp_path):
    job = job_for("network")
    with pytest.raises(FileNotFoundError):
        logic.load_examples(job, str(tmp_path / "{name}.jsonl"))
    assert logic.load_examples(job, str(tmp_path / "{name}.jsonl"), allow_missing=True) == ([], [])


def test_fixed_budget_guard(data):
    root, man = data
    job = job_for("database")
    train, _ = logic.load_examples(job, str(root / "data" / "domains" / "{name}.jsonl"))
    assert logic.check_counts(job, len(train), man) == len(train)
    with pytest.raises(AssertionError):
        logic.check_counts(job, len(train) + 1, man)


def test_stratified_eval_keeps_every_kind():
    from slm.contracts import TrainExample

    ev = [TrainExample(domain="frontend", kind=k, prompt=f"{k}{i}", completion="{}", split="eval")
          for k in ("page", "form", "layout") for i in range(4)]
    got = logic.stratified_eval(ev, cap=3)
    assert len(got) == 3 and {e.kind for e in got} == {"page", "form", "layout"}


def test_per_kind_accuracy_groups_correctly():
    from slm.contracts import TrainExample

    ev = [TrainExample(domain="network", kind=k, prompt=str(i), completion="{}", split="eval")
          for i, k in enumerate(["rest", "rest", "client"])]
    assert logic.per_kind_accuracy(ev, [True, False, True]) == {"client": 1.0, "rest": 0.5}


def test_retry_policy_is_one_retry_below_threshold():
    job = job_for("database")
    assert logic.needs_retry(job, 0.5, escalated=False)
    assert not logic.needs_retry(job, 0.95, escalated=False)
    assert not logic.needs_retry(job, 0.5, escalated=True)


def test_chunk_balances():
    js = jobs()
    chunks = chunk(js, 2)
    assert [len(c) for c in chunks] == [2, 2]
    assert chunk([], 2) == []


def test_registry_summary_reports_every_domain():
    out = logic.registry_summary([])
    assert set(out) == set(DOMAINS)
    assert all(v["missing"] for v in out.values())
