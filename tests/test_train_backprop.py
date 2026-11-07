"""Offline tests for the free-compute trainer's pure logic (no torch)."""

from __future__ import annotations

import pytest

from slm import contracts as C
from slm.bench.build import build_all
from slm.manager.train_logic import IGNORE
from slm.train import backprop as B


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    r = tmp_path_factory.mktemp("free")
    build_all(root=str(r), scale=0.1)
    return r


def test_paths_mirror_the_volume_layout(tmp_path):
    assert B.data_path(tmp_path, "domain_data", "auth") == tmp_path / "data/domains/auth.jsonl"
    assert B.adapter_dir(tmp_path, "network", 3) == tmp_path / "adapters/3/spec-network"
    assert B.adapter_dir(tmp_path, "manager", 0, run="m1") == tmp_path / "manager/m1"
    assert B.base_model("manager") == C.MANAGER_BASE and B.base_model("auth") == C.BASE_MODEL


@pytest.mark.parametrize("role", list(C.DOMAINS))
def test_specialist_rows_use_the_serving_prompt(root, role):
    train, ev = B.load_rows(root, role)
    assert train and ev
    assert all(r.system == C.specialist_system(role) for r in train + ev)
    assert all(C.Artifact.model_validate_json(r.completion) for r in train[:3])
    assert all(r.kind in C.KINDS[role] for r in train)


def test_manager_rows(root):
    train, ev = B.load_rows(root, "manager")
    assert train and ev
    assert C.ProjectPlan.model_validate_json(train[0].completion)


def test_missing_data_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        B.load_rows(tmp_path, "auth")
    with pytest.raises(ValueError):
        B.load_rows(tmp_path, "nope")


def test_encode_masks_prompt_and_drops_too_long():
    rows = [B.Row("s", "p", "abc"), B.Row("s", "p", "x" * 50)]
    enc_p = lambda s, p: [1, 2, 3]  # noqa: E731
    enc_c = lambda t: [ord(c) for c in t]  # noqa: E731
    ex, lengths, dropped = B.encode_rows(rows, enc_p, enc_c, eos_id=0, max_len=20)
    assert dropped == 1 and lengths == [7, 54] and len(ex) == 1
    ids, labels = ex[0]
    assert ids == [1, 2, 3, 97, 98, 99, 0]
    assert labels == [IGNORE] * 3 + [97, 98, 99, 0]  # loss on completion + eos only


def test_pad_batch_and_target_tokens():
    batch = [([5, 6, 7], [IGNORE, 6, 7]), ([5], [IGNORE])]
    ids, labels, att = B.pad_batch(batch, pad_id=0)
    assert ids == [[5, 6, 7], [5, 0, 0]]
    assert labels == [[IGNORE, 6, 7], [IGNORE, IGNORE, IGNORE]]
    assert att == [[1, 1, 1], [1, 0, 0]]
    assert B.target_tokens([IGNORE, 6, 7]) == 2 and B.target_tokens([7, IGNORE]) == 0


def test_lr_schedule_warms_up_then_decays():
    total, peak = 100, 1e-3
    lrs = [B.lr_at(s, total, peak, 0.05) for s in range(total)]
    assert lrs[0] < lrs[4] == pytest.approx(peak)
    assert all(a >= b for a, b in zip(lrs[5:], lrs[6:]))
    assert lrs[-1] < 0.01 * peak
    assert B.total_steps(17, 8, 2) == 6


def test_gate_on_gold_and_garbage(root):
    from slm.bench.catalog import gold_artifact
    from slm.bench.projects import generate_balanced

    p = generate_balanced(1, "dev", 0)[0]
    t = p.plan.tasks[0]
    gold = gold_artifact(p.plan, t).model_dump_json()
    assert B.gate_ok_text(gold, t.domain, t.kind, t.target)
    assert B.gate_ok_text(f"```json\n{gold}\n```", t.domain, t.kind, t.target)
    assert not B.gate_ok_text("not json", t.domain, t.kind, t.target)


def test_trainer_module_does_not_import_torch():
    import sys

    assert "torch" not in sys.modules
