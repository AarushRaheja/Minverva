"""The specialist definitions agree with the contract (domains.py) and with the gold training data."""

from __future__ import annotations

import pytest

from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES, build_plan, gold_artifacts
from slm.contracts import DOMAINS, specialist_system
from slm.domains import ADAPTER, KINDS, canonical_path
from slm.specialists import SPECIALISTS, describe, fill, system_prompt

PLANS = [build_plan(t) for t in TRAIN_TEMPLATES + HELDOUT_TEMPLATES]


def test_one_spec_per_domain_covering_every_kind():
    assert list(SPECIALISTS) == list(DOMAINS)
    for d, s in SPECIALISTS.items():
        assert s.adapter == ADAPTER[d]
        assert tuple(k.kind for k in s.kinds) == KINDS[d]


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.name)
def test_spec_paths_match_the_contract(plan):
    for t in plan.tasks:
        assert fill(SPECIALISTS[t.domain].kind(t.kind).path, t.target) == canonical_path(t.domain, t.kind, t.target)


@pytest.mark.parametrize("plan", PLANS, ids=lambda p: p.name)
def test_gold_artifacts_follow_the_spec(plan):
    """Every must_contain snippet is in the gold file, so the prompt never contradicts the data."""
    gold = gold_artifacts(plan)
    for t in plan.tasks:
        text = gold[t.id].files[0].content
        for snippet in SPECIALISTS[t.domain].kind(t.kind).must_contain:
            assert fill(snippet, t.target) in text, (t.id, t.domain, t.kind, snippet)


def test_gold_tsx_has_no_template_escapes():
    for plan in PLANS:
        for art in gold_artifacts(plan).values():
            for f in art.files:
                assert "import {{" not in f.content, f.path  # string.Template does not unescape {{


@pytest.mark.parametrize("domain", DOMAINS)
def test_system_prompt_is_rendered_from_the_spec(domain):
    p = specialist_system(domain)
    assert p == system_prompt(domain)
    assert f"You are the {domain} specialist" in p and '{"files"' in p
    for k in KINDS[domain]:
        assert f"[{k}]" in p
    assert "{" not in p.replace('{"files"', "").replace('{"path"', "").replace("{ id", "").replace("{item_id}", "")
    assert len(p) < 2000  # ~500 tokens: leaves room for the task prompt and a 1k-token artifact


def test_describe_lists_every_specialist():
    text = describe()
    for s in SPECIALISTS.values():
        assert s.title in text and s.adapter in text
