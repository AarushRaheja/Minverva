"""Turn trial records into the report. Families are reported apart, never merged into one leaderboard number. A censored
trial is shown beside the results, and never counted as a coding failure."""

from __future__ import annotations

import json
import statistics as st
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from evaluation.adapters.registry import CONFIGS
from evaluation.analysis import statistics as s
from evaluation.core import CENSORED
from evaluation.runner.orchestrator import RESULTS, load_trials


def load_prereg() -> dict:
    return tomllib.loads((CONFIGS / "preregistration.toml").read_text())


def all_trials(experiments: list[str] | None = None, split: str = "dev") -> list[dict]:
    """Held-out results stay out of a report unless it asks for that split."""
    rows = []
    if not RESULTS.exists():
        return rows
    for d in sorted(p for p in RESULTS.iterdir() if p.is_dir()):
        if experiments is None or d.name in experiments:
            rows += [{**r, "experiment": d.name} for r in load_trials(d / "trials.jsonl") if r.get("split", "dev") == split]
    return rows


def attempted(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["status"] not in CENSORED]


def by_task(rows: list[dict], agent: str) -> dict[str, list[bool]]:
    out = defaultdict(list)
    for r in sorted((r for r in rows if r["agent"] == agent), key=lambda r: r["repeat"]):
        out[r["task"]].append(r["resolved"])
    return dict(out)


def agent_summary(rows: list[dict]) -> list[dict]:
    out = []
    for agent in sorted({r["agent"] for r in rows}):
        mine = [r for r in rows if r["agent"] == agent]
        done = attempted(mine)
        first = [r for r in done if r["repeat"] == 0]
        k = sum(r["resolved"] for r in first)
        scores = [r["score"] for r in done if r["score"] is not None]
        walls = [r["wall_s"] for r in done if r["wall_s"] is not None]
        tasks = by_task(done, agent)
        repo = [r for r in done if r["family"] == "repo" and r["grade"]]
        out.append({
            "agent": agent, "attempted": len(done), "censored": Counter(r["status"] for r in mine if r["status"] in CENSORED),
            "resolved_at_1": k / len(first) if first else None, "resolved_n": k, "first_n": len(first),
            "ci": s.wilson(k, len(first)) if first else (None, None), "score": sum(scores) / len(scores) if scores else None,
            "pass_at_3": s.pass_at_k(tasks, 3), "success_all_3": s.success_all(tasks, 3),
            "regression_rate": sum(bool(r["grade"].get("regression")) for r in repo) / len(repo) if repo else None,
            "cost_per_resolved": s.cost_per_resolved([r["cost_usd"] for r in done], [r["resolved"] for r in done]),
            "total_cost": None if any(r["cost_usd"] is None for r in done) or not done else sum(r["cost_usd"] for r in done),
            "cost_basis": sorted({r.get("cost_basis") or "unknown" for r in done}),
            "median_wall_s": st.median(walls) if walls else None,
            "wall_sd": st.pstdev(walls) if len(walls) > 1 else None,
            "timeouts": sum(r["status"] == "budget_exhausted" for r in done),
            "crashes": sum(r["status"] == "crashed" for r in done),
            "tok_in": _mean([r["metrics"].get("tok_in") for r in done]), "tok_out": _mean([r["metrics"].get("tok_out") for r in done]),
            "model_calls": _mean([r["metrics"].get("model_calls") for r in done]),
            "tool_calls": _mean([r["metrics"].get("tool_calls") for r in done]),
            "ran_tests": _share([r["trace"].get("test_runs", 0) > 0 for r in done if r.get("trace") and r["provenance"] == "harness"]),
            "tested_after_edit": _share([r["trace"].get("tested_after_last_edit") for r in done if r.get("trace") and r["provenance"] == "harness"]),
        })
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _share(xs):
    return sum(bool(x) for x in xs) / len(xs) if xs else None


def paired(rows: list[dict], a: str, b: str, min_diff_pp: float = 5.0) -> dict:
    """Paired on tasks both attempted, using each task's first attempt for McNemar and all attempts for the bootstrap."""
    rows = attempted(rows)
    ta, tb = by_task(rows, a), by_task(rows, b)
    shared = sorted(set(ta) & set(tb))
    groups = {r["task"]: r["group"] for r in rows}
    mc = s.mcnemar([ta[t][0] for t in shared], [tb[t][0] for t in shared])
    boot = s.paired_difference_ci({t: [float(x) for x in ta[t]] for t in shared}, {t: [float(x) for x in tb[t]] for t in shared}, groups)
    needed = s.min_discordant_for_significance()
    n_disc = mc["a_only"] + mc["b_only"]
    disagreement = n_disc / len(shared) if shared else 0
    if not shared:
        verdict = "no shared tasks"
    elif len(shared) < needed:
        verdict = f"too few tasks: {len(shared)} shared, and at least {needed} disagreements are needed to reach p<0.05"
    elif mc["p"] > 0.05:
        verdict = "no significant difference"
    else:
        ahead = a if mc["a_only"] > mc["b_only"] else b
        verdict = f"{ahead} is ahead" + ("" if abs(boot["diff"]) * 100 >= min_diff_pp else f", but below the {min_diff_pp:.0f} point threshold")
    return {"a": a, "b": b, "n": len(shared), **mc, **{f"boot_{k}": v for k, v in boot.items()}, "verdict": verdict,
            "disagreement": disagreement,
            "tasks_for_5pp": s.paired_tasks_needed(disagreement, min_diff_pp / 100) if shared else None}


def factorial(rows: list[dict], cells: dict[str, str]) -> dict:
    means = {}
    for cell, agent in cells.items():
        done = [r["resolved"] for r in attempted(rows) if r["agent"] == agent]
        means[cell] = sum(done) / len(done) if done else None
    missing = [c for c in ("00", "01", "10", "11") if means.get(c) is None]
    return {"cells": means, "agents": cells, "missing": missing,
            "interaction": None if missing else s.interaction(means["11"], means["10"], means["01"], means["00"])}


def scaling(rows: list[dict]) -> list[dict]:
    out = defaultdict(lambda: {"k": 0, "n": 0})
    for r in attempted(rows):
        c = out[(r["agent"], r["budget"], r["family"])]
        c["k"] += r["resolved"]
        c["n"] += 1
    return [{"agent": a, "budget": b, "family": f, **v} for (a, b, f), v in sorted(out.items())]


def robustness(rows: list[dict]) -> list[dict]:
    done = attempted(rows)
    out = []
    for perturbed in sorted({r["task"] for r in done if r.get("control_of")}):
        control = next(r["control_of"] for r in done if r["task"] == perturbed)
        for agent in sorted({r["agent"] for r in done if r["task"] == perturbed}):
            p = [r["resolved"] for r in done if r["agent"] == agent and r["task"] == perturbed]
            c = [r["resolved"] for r in done if r["agent"] == agent and r["task"] == control]
            out.append({"agent": agent, "task": perturbed, "control": control, "n": len(p), "delta": s.robustness_delta(p, c)})
    return out


def failures(rows: list[dict]) -> dict[str, Counter]:
    out = defaultdict(Counter)
    for r in rows:
        if r.get("failure"):
            out[r["agent"]][r["failure"]["primary"]] += 1
    return dict(out)


def safety(rows: list[dict]) -> list[dict]:
    out = []
    for r in attempted(rows):
        sf = (r.get("grade") or {}).get("safety") or {}
        if r["task_class"] == "adversarial" or sf.get("canaries_tripped") or sf.get("edited_existing_tests"):
            out.append({"agent": r["agent"], "task": r["task"], "resolved": r["resolved"], "canaries_tripped": sf.get("canaries_tripped", []),
                        "out_of_scope": sf.get("out_of_scope", []), "edited_existing_tests": sf.get("edited_existing_tests", [])})
    return out


def controls_status(rows: list[dict]) -> dict:
    null = [r for r in rows if r["agent"] == "null" and r["status"] not in CENSORED]
    oracle = [r for r in rows if r["agent"] == "oracle" and r["status"] not in CENSORED]
    ok = bool(null) and bool(oracle) and not any(r["resolved"] for r in null) and all(r["resolved"] for r in oracle)
    return {"valid": ok, "null_resolved": sum(r["resolved"] for r in null), "null_n": len(null),
            "oracle_resolved": sum(r["resolved"] for r in oracle), "oracle_n": len(oracle)}


LADDER = {0: "No level reached", 1: "Functional", 2: "Competitive", 3: "Advantageous", 4: "Architecturally substantiated", 5: "Independently validated"}


def evidence_level(summary: list[dict], agent: str, comparisons: list[dict]) -> dict:
    """The highest rung the data supports. Only levels 1 and 2 can be read off this data; 3 to 5 need the study."""
    me = next((x for x in summary if x["agent"] == agent), None)
    if me is None or not me["resolved_n"]:
        return {"level": 0, "name": LADDER[0], "why": "The agent hasn't resolved a task"}
    if (me["resolved_at_1"] or 0) < 0.5 or me["first_n"] < 10:
        return {"level": 1, "name": LADDER[1], "why": "It resolves tasks, but not yet reliably over enough of them to compare"}
    return {"level": 1, "name": LADDER[1], "why": "Higher levels need the preregistered comparison on external benchmarks"}


def build_report(rows: list[dict], custom: str = "slm-mgr-G4-promptfix") -> dict:
    prereg = load_prereg()
    controls = controls_status(rows)
    measured = [r for r in rows if r["agent"] not in ("null", "oracle")]
    families = {}
    for fam in sorted({r["family"] for r in measured}):
        fam_rows = [r for r in measured if r["family"] == fam]
        families[fam] = agent_summary(fam_rows)
    summary_all = agent_summary(measured)
    comps = []
    for fam, _ in families.items():
        fam_rows = [r for r in measured if r["family"] == fam]
        agents = sorted({r["agent"] for r in attempted(fam_rows)})
        if custom in agents:
            comps += [{**paired(fam_rows, custom, b, prereg["min_resolve_gain_pp"]), "family": fam} for b in agents if b != custom]
        elif "claude-code" in agents:
            comps += [{**paired(fam_rows, "tool-loop-qwen", "claude-code", prereg["min_resolve_gain_pp"]), "family": fam}] if "tool-loop-qwen" in agents else []
    frontier_points = [{"name": x["agent"], "cost": x["cost_per_resolved"], "resolve": x["resolved_at_1"]} for x in summary_all]
    return {"controls": controls, "families": families, "comparisons": comps, "scaling": scaling(measured),
            "robustness": robustness(measured), "failures": {k: dict(v) for k, v in failures(measured).items()},
            "safety": safety(measured), "pareto": s.pareto_frontier(frontier_points),
            "evidence": evidence_level(summary_all, custom, comps), "custom": custom, "prereg": prereg,
            "public": tomllib.loads((CONFIGS / "benchmarks/public.toml").read_text()), "n_trials": len(rows)}


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def _num(x, fmt="{:.2f}"):
    return "—" if x is None else fmt.format(x)


def to_markdown(rep: dict) -> str:
    c = rep["controls"]
    lines = ["# Agent evaluation report", "",
             f"**Evidence level for `{rep['custom']}`: {rep['evidence']['level']}, {rep['evidence']['name']}.** {rep['evidence']['why']}.", "",
             "## Harness validity", "",
             f"Controls: nothing-submitted agent resolved {c['null_resolved']} of {c['null_n']}, reference solution resolved "
             f"{c['oracle_resolved']} of {c['oracle_n']}. " + ("**Valid.**" if c["valid"] else "**NOT VALID: don't trust anything below.**"), ""]
    for fam, summ in rep["families"].items():
        lines += [f"## Results: {fam}", "",
                  "| agent | Resolved@1 (95% CI) | run/test score | Pass@3 | Success@3-All | regressions | $/resolved | total $ | median s | timeouts | crashes | not attempted |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in sorted(summ, key=lambda x: -(x["resolved_at_1"] or 0)):
            ci = f"{x['resolved_n']} of {x['first_n']}, {_pct(x['resolved_at_1'])} ({_pct(x['ci'][0])}–{_pct(x['ci'][1])})" if x["first_n"] else "—"
            cens = ", ".join(f"{v} {k}" for k, v in x["censored"].items()) or "0"
            lines.append(f"| {x['agent']} | {ci} | {_num(x['score'])} | {_pct(x['pass_at_3'])} | {_pct(x['success_all_3'])} | {_pct(x['regression_rate'])} "
                         f"| {_num(x['cost_per_resolved'], '${:.2f}')} | {_num(x['total_cost'], '${:.2f}')} | {_num(x['median_wall_s'], '{:.0f}')} | {x['timeouts']} | {x['crashes']} | {cens} |")
        lines.append("")
    if rep["comparisons"]:
        lines += ["## Paired comparisons", "", "| family | a vs b | tasks | a only | b only | both | neither | McNemar p | a−b (95% CI, resamples task groups) | verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
        for p in rep["comparisons"]:
            d = "—" if p.get("boot_diff") is None else f"{p['boot_diff']:+.2f} ({p['boot_lo']:+.2f} to {p['boot_hi']:+.2f})"
            lines.append(f"| {p['family']} | {p['a']} vs {p['b']} | {p['n']} | {p['a_only']} | {p['b_only']} | {p['both']} | {p['neither']} | {p['p']:.3f} | {d} | {p['verdict']} |")
        lines.append("")
    if rep["robustness"]:
        lines += ["## Robustness", "", "| agent | perturbed task | control | attempts | change in success |", "|---|---|---|---|---|"]
        lines += [f"| {r['agent']} | {r['task']} | {r['control']} | {r['n']} | {_num(r['delta'], '{:+.2f}')} |" for r in rep["robustness"]]
        lines.append("")
    if rep["failures"]:
        lines += ["## Failure categories", "", "| agent | categories |", "|---|---|"]
        lines += [f"| {a} | {', '.join(f'{k} {v}' for k, v in sorted(cs.items(), key=lambda kv: -kv[1]))} |" for a, cs in sorted(rep["failures"].items())]
        lines.append("")
    if rep["safety"]:
        lines += ["## Safety (kept out of the coding scores)", "", "| agent | task | resolved | injected action taken | outside scope | edited existing tests |", "|---|---|---|---|---|---|"]
        lines += [f"| {x['agent']} | {x['task']} | {'yes' if x['resolved'] else 'no'} | {', '.join(x['canaries_tripped']) or 'none'} | {', '.join(x['out_of_scope']) or 'none'} | {', '.join(x['edited_existing_tests']) or 'none'} |" for x in rep["safety"]]
        lines.append("")
    lines += ["## External benchmarks", "", "| benchmark | checked | status | needs |", "|---|---|---|---|"]
    lines += [f"| {k} | {v.get('checked', '')} | {v.get('status', '')} | {', '.join(v.get('requires', []))} |" for k, v in rep["public"].items()]
    return "\n".join(lines) + "\n"


def write_report(rows: list[dict], out: Path, custom: str = "slm-mgr-G4-promptfix") -> dict:
    rep = build_report(rows, custom)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(to_markdown(rep))
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=lambda x: dict(x) if isinstance(x, Counter) else str(x)))
    return rep
