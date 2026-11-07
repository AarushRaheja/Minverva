from __future__ import annotations

import pytest

from slm.bench.catalog import gold_artifacts
from slm.bench.variety import (
    DEV_CONCEPTS, SHARED_PHRASINGS, TEST_CONCEPTS, TEST_PHRASINGS, TRAIN_CONCEPTS, generate_varied,
)
from slm.contracts import SLUG, integrate
from slm.domains import plural

SEED = 20261101
# SQL keywords, and names the catalog's fixed tasks already use.
RESERVED = {"user", "users", "session", "routes", "oauth", "shell", "order", "group", "table", "check",
            "select", "from", "to", "default", "end", "case", "grant", "class", "page", "form", "route"}


def _entities(concepts) -> set[str]:
    return {e for c in concepts for e in c.entities}


def test_concepts_and_entities_do_not_leak_between_splits():
    groups = [TRAIN_CONCEPTS, DEV_CONCEPTS, TEST_CONCEPTS]
    ids = [c.id for g in groups for c in g]
    assert len(ids) == len(set(ids))
    train, dev, test = (_entities(g) for g in groups)
    assert not train & dev and not train & test and not dev & test


def test_entity_names_are_regular_and_safe():
    for e in _entities(TRAIN_CONCEPTS + DEV_CONCEPTS + TEST_CONCEPTS):
        assert SLUG.match(e) and e not in RESERVED
        assert not plural(e).endswith(("ys", "shs", "fs", "zs")) or e.endswith(("ey", "ay", "oy")), e


@pytest.mark.parametrize("split,n", [("train", 1000), ("dev", 100), ("test", 160)])
def test_full_size_splits_have_only_distinct_one_line_briefs(split, n):
    briefs = [p.description for p in generate_varied(n, split, SEED)]
    assert len(set(briefs)) == n
    assert all("\n" not in b for b in briefs)


def test_no_brief_appears_in_two_splits():
    sets = [{p.description for p in generate_varied(n, s, SEED)}
            for s, n in (("train", 1000), ("dev", 100), ("test", 160))]
    assert not sets[0] & sets[1] and not sets[0] & sets[2] and not sets[1] & sets[2]


def test_test_split_uses_phrasings_train_never_saw():
    def opener(template: str) -> str:
        return template.split("{article}")[0]

    assert not {opener(t) for t in TEST_PHRASINGS} & {opener(t) for t in SHARED_PHRASINGS}
    openers = tuple(opener(t) for t in TEST_PHRASINGS)
    assert all(p.description.startswith(openers) for p in generate_varied(40, "test", SEED))
    assert not any(p.description.startswith(openers) for p in generate_varied(200, "train", SEED))


def test_generation_is_deterministic_and_prefix_stable():
    long = generate_varied(50, "train", SEED)
    assert generate_varied(20, "train", SEED) == long[:20]


def test_splits_vary_entity_count_and_oauth():
    train = generate_varied(1000, "train", SEED)
    assert {sum(t.kind == "rest" for t in p.plan.tasks) for p in train} == {1, 2, 3, 4}
    with_oauth = sum(any(t.kind == "oauth" for t in p.plan.tasks) for p in train)
    assert 300 < with_oauth < 700


def test_brief_determines_the_plan():
    """Every entity, the form target and any OAuth requirement must be readable from the brief."""
    for p in generate_varied(200, "train", SEED) + generate_varied(50, "test", SEED):
        text = p.description.lower()
        for t in p.plan.tasks:
            if t.kind in ("rest", "form"):
                assert plural(t.target).replace("_", " ") in text, (t.target, text)
        assert ("oauth" in text) == any(t.kind == "oauth" for t in p.plan.tasks), text


@pytest.mark.parametrize("split,n", [("train", 300), ("dev", 100), ("test", 160)])
def test_every_generated_project_integrates_with_gold_artifacts(split, n):
    for p in generate_varied(n, split, SEED):
        d = integrate(p.id, p.plan, gold_artifacts(p.plan))
        assert d.ok, (p.description, d.failures)
