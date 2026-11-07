"""Elo over architecture-grid rows: one match per (project, domain), higher pass rate wins."""

import pytest

from slm.arch.__main__ import elo_inputs, elo_table
from slm.bench import elo as E


def _row(arm, proj, rates, rate=None):
    return {"arm": arm, "project_id": proj, "gold_task_rate": rate if rate is not None else sum(rates.values()) / 4,
            "by_domain": rates}


ALL = dict.fromkeys(("database", "auth", "network", "frontend"), 1.0)


def test_inputs_one_item_per_project_domain():
    rows = [_row("a", "p1", ALL), _row("b", "p1", {**ALL, "frontend": 0.5}), _row("c", "p1", {}, rate=0.25)]
    res, cl = elo_inputs(rows)
    assert set(res["a"]) == {f"p1/{d}" for d in ALL} and set(cl.values()) == {"p1"}
    assert res["b"]["p1/frontend"] == 0.5 and res["c"]["p1/auth"] == 0.25  # no by_domain -> project rate


def test_rates_rank_like_bools():
    # a beats b on one domain, draws the rest; b beats c everywhere
    rows = [_row("a", "p1", ALL), _row("b", "p1", {**ALL, "frontend": 0.5}),
            _row("c", "p1", dict.fromkeys(ALL, 0.0))]
    res, cl = elo_inputs(rows)
    r = E.elo(res, cl)
    assert r["a"] > r["b"] > r["c"] and sum(r.values()) / 3 == pytest.approx(1000)


def test_bool_results_unchanged():
    assert E.elo({"a": {"i": True}, "b": {"i": False}})["a"] > 1000


def test_table_renders():
    rows = [_row("a", p, ALL) for p in ("p1", "p2")] + [_row("b", p, {**ALL, "auth": 0.0}) for p in ("p1", "p2")]
    md = elo_table(rows)
    assert "| 1 | a |" in md and "mean domain pass" in md
