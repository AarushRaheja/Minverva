from __future__ import annotations

import json

from slm.arch.__main__ import load_nested_plans, oneline_heldout
from slm.bench.variety import generate_varied
from slm.manager.spec import gold_spec


def test_heldout_briefs_are_unseen_one_liners_without_oauth():
    ps = oneline_heldout()
    assert len(ps) == 10 and len({p.template_id for p in ps}) == 10
    train = {p.template_id for p in generate_varied(1000, "train", 20261101)}
    for p in ps:
        assert p.id.startswith("proj-test-") and p.template_id not in train and "\n" not in p.description
        assert not any(t.kind == "oauth" for t in p.plan.tasks) and "oauth" not in p.description.lower()


def test_nested_plans_load_and_a_bad_plan_is_recorded_not_raised(tmp_path):
    ps = oneline_heldout()[:2]
    file = tmp_path / "plans.jsonl"
    file.write_text(json.dumps({"project_id": ps[0].id, "output": gold_spec(ps[0].plan).model_dump_json()}) + "\n"
                    + json.dumps({"project_id": ps[1].id, "output": "not json"}) + "\n")
    stats = load_nested_plans(str(file), ps)
    assert stats[ps[0].id].plan == ps[0].plan and stats[ps[0].id].recall == 1.0
    assert stats[ps[1].id].plan is None and stats[ps[1].id].error
