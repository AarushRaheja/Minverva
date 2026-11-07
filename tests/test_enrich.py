from __future__ import annotations

import json

from slm.bench.variety import generate_varied
from slm.manager.enrich import (
    SECTIONS, apply_texts, judge_section, problem_with, section_items, section_prompt,
)
from slm.manager.spec import ProjectSpec, gold_spec, score_spec_json, to_plan

PROJECT = generate_varied(3, "train", 20261101)[2]
SPEC = gold_spec(PROJECT.plan)


def _reply(items: dict[str, str], **override) -> str:
    return json.dumps({"items": [{"id": k, "text": override.get(k, v)} for k, v in items.items()]})


def test_every_section_has_items_and_ids_are_unique_across_sections():
    seen: list[str] = []
    for s in SECTIONS:
        items = section_items(SPEC, s)
        assert items
        seen += list(items)
        prompt = section_prompt(PROJECT.description, s, items)
        assert PROJECT.description in prompt and all(k in prompt for k in items)
    assert len(seen) == len(set(seen))


def test_acceptance_criteria_are_not_offered_to_the_teacher():
    items = section_items(SPEC, "network")
    assert not any("acceptance" in k or "check_task" in v for k, v in items.items())


def test_a_good_rewrite_is_accepted_and_applied():
    items = section_items(SPEC, "database")
    key = "database.summary"
    new = "Postgres tables that hold this app's records and its accounts."
    original = items[key]
    r = judge_section("database", items, _reply(items, **{key: new}))
    assert r.accepted and r.changed == 1, r.problems
    out = apply_texts(SPEC, r.texts)
    assert out.database.summary == new and original != new


def test_applying_texts_cannot_change_structure():
    texts: dict[str, str] = {}
    for s in SECTIONS:
        texts |= {k: "Reworded text for this item." for k in section_items(SPEC, s)}
    texts |= {"t1.deps": "evil", "DB-1.1.kind": "evil", "DB-1.1.acceptance": "evil"}
    out = apply_texts(SPEC, texts)
    assert to_plan(out) == PROJECT.plan
    s = score_spec_json(out.model_dump_json(), PROJECT.plan)
    assert s.plan.isomorphic and s.symbol_coverage == 1.0 and s.known_refs == 1.0 and s.tests_scoped == 1.0
    assert out.database.groups[0].tasks[0].acceptance == SPEC.database.groups[0].tasks[0].acceptance
    ProjectSpec.model_validate_json(out.model_dump_json())


def test_rejects_off_stack_technology():
    assert problem_with("Store rows in Postgres.", "Store rows in Postgres with a Redis cache.") == "off_stack:redis"
    assert problem_with("Sign people in.", "Issue a JWT to people on sign-in.") == "off_stack:jwt"


def test_rejects_invented_performance_numbers():
    assert problem_with("The page lists rows.", "The page lists rows in 50ms.") == "invented_metric"
    assert problem_with("The page lists rows.", "The page lists rows within 2 seconds.") == "invented_metric"
    assert problem_with("The page lists rows.", "Rows load for 99% of visitors.") == "invented_metric"


def test_counts_that_are_not_performance_claims_are_allowed():
    assert problem_with("Send GET /api/pets when two rows exist.", "Send GET /api/pets once 2 pets are stored.") is None


def test_sentence_punctuation_is_not_part_of_a_path():
    assert problem_with("It is listed on /receipts.", "It shows up on the /receipts page.") is None
    assert problem_with("See src/auth/session.py now.", "Read src/auth/session.py first.") is None
    assert problem_with("See src/auth/session.py now.", "Read src/auth/session first.").startswith("lost_anchor")


def test_step_unit_tests_are_not_offered_and_stay_exact():
    for s in SECTIONS:
        assert not any(k.startswith("UT-") for k in section_items(SPEC, s))
    out = apply_texts(SPEC, {"UT-DB-1.1.1.expected": "evil"})
    assert out.database.groups[0].tasks[0].steps[0] == SPEC.database.groups[0].tasks[0].steps[0]


def test_multi_word_entities_may_be_written_as_words_but_code_identifiers_may_not():
    entities = frozenset({"ticket_item"})
    assert problem_with("Tables: users, ticket_item.", "Tables for users and ticket items.", entities) is None
    assert problem_with("Tables: users, ticket_item.", "Tables for users and ticket items.") is not None
    assert problem_with("Every owner_id references users.", "Every owner id references users.", entities) is not None


def test_rejects_a_lost_identifier():
    why = problem_with("Send POST /api/pets with a title.", "Create a pet with a title.")
    assert why is not None and why.startswith("lost_anchor")
    assert problem_with("require_session raises HTTPException.", "It fails with an error.").startswith("lost_anchor")


def test_rejects_multi_line_and_bad_lengths():
    assert problem_with("Some sentence here.", "line one\nline two") == "multi_line"
    assert problem_with("Some sentence here.", "x") == "length"
    assert problem_with("Some sentence here.", "x" * 400) == "length"


def test_short_headings_may_stay_short():
    assert problem_with("Forms", "Pet forms") is None


def test_one_bad_item_rejects_the_whole_section():
    items = section_items(SPEC, "auth")
    key = next(iter(items))
    r = judge_section("auth", items, _reply(items, **{key: "Sessions stored in Redis for this app."}))
    assert not r.accepted and not r.texts and any("off_stack" in p for p in r.problems)


def test_missing_or_extra_ids_reject_the_section():
    items = section_items(SPEC, "auth")
    partial = dict(list(items.items())[:-1])
    assert not judge_section("auth", items, _reply(partial)).accepted
    extra = json.dumps({"items": [{"id": k, "text": v} for k, v in items.items()] +
                                 [{"id": "invented", "text": "A whole new item here."}]})
    assert not judge_section("auth", items, extra).accepted


def test_bad_json_rejects_the_section():
    r = judge_section("auth", section_items(SPEC, "auth"), "sure! here is the json")
    assert not r.accepted and r.problems == ["bad_json"]


def test_unchanged_text_is_accepted_but_counted_as_unchanged():
    items = section_items(SPEC, "frontend")
    r = judge_section("frontend", items, _reply(items))
    assert r.accepted and r.changed == 0
