"""Hyperparameter tuning, offline: the trial grid, resuming, and the rule for changing the default. No torch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slm.bench.build import build_all
from slm.train import tune as T
from slm.train.backprop import TARGET_MODULES, Recipe, load_rows

DOMAIN = "database"


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    r = tmp_path_factory.mktemp("tune")
    build_all(root=str(r), scale=0.1)
    return r


def fake_train(scores, seen=None, fail=()):
    """A train_role stand-in: scores[trial values] gives each row's pass flags."""

    def train(role, root, recipe, *, device=None, base=None, out_root=None):
        key = next((f"{k}={getattr(recipe, k)}" for k in T.SEARCH if getattr(recipe, k) != getattr(Recipe(), k)), T.DEFAULT)
        if seen is not None:
            seen.append((role, key))
        if key in fail:
            raise RuntimeError("out of memory")
        Path(out_root).mkdir(parents=True, exist_ok=True)
        flags = scores.get(key, scores[T.DEFAULT])
        return {"gate_task_ok": sum(flags) / len(flags), "gate_flags": flags, "gate_clusters": [f"c{i}" for i in range(len(flags))],
                "train_seconds": 1.0, "final_loss": 0.5, "n_train": 8, "steps": 2}

    return train


def row(trial, flags, clusters=None):
    return {"role": DOMAIN, "trial": trial, "gate": sum(flags) / len(flags), "flags": flags,
            "clusters": clusters or [f"c{i}" for i in range(len(flags))], "train_seconds": 1.0, "final_loss": 0.5}


def test_grid_is_one_factor_at_a_time_around_the_default():
    ts = T.trials()
    assert [t.id for t in ts] == ["default", "r=8", "r=32", "lr=0.0001", "lr=0.0005", "epochs=1", "epochs=3", "target=attn"]
    base = Recipe()
    for t in ts[1:]:
        changed = [k for k in ("r", "lr", "epochs", "target") if getattr(t.recipe, k) != getattr(base, k)]
        assert len(changed) == 1
    assert next(t for t in ts if t.id == "r=32").recipe.alpha == 64  # alpha stays 2r
    assert all(t.recipe.target in TARGET_MODULES for t in ts)


def test_dry_run_lists_every_trial(root):
    lines = T.plan_lines([DOMAIN, "auth"], root)
    assert len(lines) == 2 * 8 + 1 and lines[-1].startswith("16 trials")


def test_max_train_caps_the_steps(root):
    capped = T.plan_lines([DOMAIN], root, Recipe(max_train=8, epochs=1))
    assert "train=8 " in capped[0]


def test_tuning_only_scores_dev_rows(root):
    _, ev = load_rows(root, DOMAIN)
    assert ev  # every eval row comes from the dev split: build_all marks only dev projects as "eval"
    projects = [json.loads(x)["id"] for x in Path(root, "data/projects/test.jsonl").read_text().splitlines()]
    assert projects and not any(p in r.prompt for r in ev for p in projects)


def test_run_records_every_trial_resumes_and_removes_adapters(tmp_path):
    seen: list = []
    results = T.run_tuning([DOMAIN], tmp_path, train_fn=fake_train({T.DEFAULT: [True, False]}, seen), log=lambda _: None)
    assert len(T._load(results)) == 8 and len(seen) == 8
    assert not (tmp_path / "tune/hp1/adapters" / DOMAIN / "default").exists()
    T.run_tuning([DOMAIN], tmp_path, train_fn=fake_train({T.DEFAULT: [True, False]}, seen), log=lambda _: None)
    assert len(seen) == 8  # nothing ran twice


def test_a_crashed_trial_records_nothing_and_is_retried(tmp_path):
    results = T.run_tuning([DOMAIN], tmp_path, train_fn=fake_train({T.DEFAULT: [True]}, fail={"r=32"}), log=lambda _: None)
    assert "r=32" not in {r["trial"] for r in T._load(results)} and len(T._load(results)) == 7
    seen: list = []
    T.run_tuning([DOMAIN], tmp_path, train_fn=fake_train({T.DEFAULT: [True]}, seen), log=lambda _: None)
    assert seen == [(DOMAIN, "r=32")]


def test_clear_win_replaces_the_default():
    n = 40
    rows = [row(T.DEFAULT, [False] * n), row("r=32", [True] * n), row("lr=0.0005", [True] * 20 + [False] * 20)]
    assert T.choose(rows) == {DOMAIN: "r=32"}


def test_a_small_gain_inside_the_ci_keeps_the_default():
    base = [True] * 30 + [False] * 10
    better = [True] * 31 + [False] * 9  # one more row right
    assert T.choose([row(T.DEFAULT, base), row("r=32", better)]) == {DOMAIN: T.DEFAULT}


def test_a_higher_score_on_different_rows_is_not_compared():
    rows = [row(T.DEFAULT, [False] * 4), row("r=32", [True] * 4, clusters=["x", "y", "z", "w"])]
    assert T.choose(rows) == {DOMAIN: T.DEFAULT}
    assert T.verdict(rows[0], rows[1]) is None


def test_no_default_result_means_no_change():
    assert T.choose([row("r=32", [True] * 8)]) == {DOMAIN: T.DEFAULT}
    assert "has no result yet" in T.report([row("r=32", [True] * 8)])


def test_report_flags_a_gate_that_cannot_separate_trials():
    text = T.report([row(T.DEFAULT, [True] * 8), row("r=32", [True] * 8)])
    assert f"## {DOMAIN}: use `default`" in text and "can't separate them" in text and "Not tuned yet: " in text
