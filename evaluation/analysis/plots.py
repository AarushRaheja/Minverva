"""One self-contained HTML dashboard: overall results, cost and latency, ablations and robustness, and a trial explorer."""

from __future__ import annotations

import html
import json
from pathlib import Path

from evaluation.runner.trajectory_logger import load as load_trajectory

CSS = """:root{color-scheme:light dark;--bg:#fbfbf9;--fg:#1d1f21;--muted:#5f6368;--line:#dcdcd6;--card:#fff;--accent:#1f6f8b;--bad:#b3261e;--good:#1a7f4b}
@media(prefers-color-scheme:dark){:root{--bg:#141517;--fg:#e8e8e6;--muted:#a2a5a9;--line:#33363a;--card:#1c1e21;--accent:#62b6d0;--bad:#f28b82;--good:#6fcf97}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:24px 16px;max-width:1180px;margin-inline:auto}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px}p{margin:6px 0}.muted{color:var(--muted)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:16px 0}.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}.tile b{display:block;font-size:22px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{color:var(--muted);font-weight:600}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}tr:last-child td{border-bottom:0}
.bar{display:inline-block;height:9px;background:var(--accent);border-radius:2px;vertical-align:middle;margin-right:6px}.bad{color:var(--bad)}.good{color:var(--good)}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0}nav button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}nav button[aria-selected=true]{border-color:var(--accent);color:var(--accent);font-weight:600}
section[hidden]{display:none}details{border-top:1px solid var(--line);padding:8px 10px}details:first-child{border-top:0}summary{cursor:pointer}pre{white-space:pre-wrap;word-break:break-word;font-size:12px;background:var(--bg);padding:8px;border-radius:6px;max-height:420px;overflow:auto}"""
JS = """for(const b of document.querySelectorAll('nav button'))b.onclick=()=>{for(const x of document.querySelectorAll('nav button'))x.setAttribute('aria-selected',x===b);for(const s of document.querySelectorAll('section[data-view]'))s.hidden=s.dataset.view!==b.dataset.view};
const f=document.getElementById('filter');if(f)f.oninput=()=>{const q=f.value.toLowerCase();for(const d of document.querySelectorAll('#trials details'))d.hidden=!d.dataset.k.includes(q)};"""
e = html.escape


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def _num(x, fmt="{:.2f}"):
    return "—" if x is None else fmt.format(x)


def _table(head: list[str], rows: list[list[str]], numeric: set[int] = frozenset()) -> str:
    th = "".join(f'<th{" class=num" if i in numeric else ""}>{e(h)}</th>' for i, h in enumerate(head))
    tr = "".join("<tr>" + "".join(f'<td{" class=num" if i in numeric else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class=scroll><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def _family_table(summ: list[dict]) -> str:
    rows = []
    for x in sorted(summ, key=lambda x: (-(x["resolved_at_1"] or 0), -(x["score"] or 0))):
        ci = "" if not x["first_n"] else f' <span class=muted>({_pct(x["ci"][0])}–{_pct(x["ci"][1])})</span>'
        cens = ", ".join(f"{v} {k}" for k, v in x["censored"].items()) or "0"
        rows.append([e(x["agent"]), f'{x["resolved_n"]} of {x["first_n"]}{ci}',
                     f'<span class=bar style="width:{int((x["score"] or 0) * 80)}px"></span>{_num(x["score"])}',
                     _pct(x["regression_rate"]), e(cens)])
    return _table(["Agent", "Resolved@1 (95% CI)", "Mean run or test score", "Regressions", "Not attempted"], rows)


def _cost_table(summ: list[dict], pareto: list[str]) -> str:
    rows = [[e(x["agent"]) + (' <span class=good>Pareto</span>' if x["agent"] in pareto else ""), _num(x["cost_per_resolved"], "${:.2f}"), _num(x["total_cost"], "${:.2f}"),
             e(", ".join(x["cost_basis"])), _num(x["median_wall_s"], "{:.0f}"), _num(x["tok_in"], "{:,.0f}"), _num(x["tok_out"], "{:,.0f}"), _num(x["model_calls"], "{:.1f}"), _num(x["tool_calls"], "{:.1f}"), str(x["timeouts"]), str(x["crashes"])] for x in summ]
    return _table(["Agent", "$ per resolved", "Total $", "Cost basis", "Median s", "Input tokens", "Output tokens", "Model calls", "Tool calls", "Timeouts", "Crashes"], rows, {1, 2, 4, 5, 6, 7, 8, 9, 10})


def _trial_block(r: dict, reports: Path) -> str:
    grade = r.get("grade") or {}
    fail = r.get("failure") or {}
    key = f'{r["agent"]} {r["task"]} {r["status"]} {fail.get("primary", "")}'.lower()
    mark = '<span class=good>resolved</span>' if r["resolved"] else f'<span class=bad>{e(fail.get("primary", "not resolved"))}</span>'
    summary = f'{e(r["agent"])} · {e(r["task"])} · attempt {r["repeat"] + 1} · {mark}'
    body = [f'<p>Status {e(r["status"])}. {e(fail.get("evidence", ""))}</p>']
    art = reports.parent / r.get("experiment", "") / "trials" / r["key"].replace("|", "--")
    events = load_trajectory(art / "trajectory.jsonl")[:60]
    if events:
        body.append("<p><b>What it did</b></p><pre>" + e("\n".join(_event(x) for x in events)) + "</pre>")
    patch = art / "patch.diff"
    if patch.exists() and patch.stat().st_size:
        body.append("<p><b>Final diff</b></p><pre>" + e(patch.read_text(errors="replace")[:6000]) + "</pre>")
    if grade:
        keep = {k: grade.get(k) for k in ("score", "by_group", "fail_to_pass_failed", "regressed", "minimality", "quality", "failed_checks") if grade.get(k) not in (None, [], {})}
        body.append("<p><b>Independent grade</b></p><pre>" + e(json.dumps(keep, indent=1)[:4000]) + "</pre>")
    return f'<details data-k="{e(key)}"><summary>{summary}</summary>{"".join(body)}</details>'


def _event(x: dict) -> str:
    t = x["type"]
    if t == "tool_call":
        return f'{x["t"]:>7.1f}s call  {x.get("tool")} {json.dumps(x.get("args"))[:220]}'
    if t == "tool_result":
        return f'{x["t"]:>7.1f}s {"ok  " if x.get("ok") else "FAIL"}  {str(x.get("output"))[:200]}'
    return f'{x["t"]:>7.1f}s {t:5} {str(x.get("text") or x.get("error"))[:220]}'


def write_dashboard(rep: dict, rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = rep["controls"]
    fams = rep["families"]
    build = fams.get("project_build", [])
    me = next((x for x in build if x["agent"] == rep["custom"]), None)
    total_local = sum(x["resolved_n"] for x in build if x["agent"].startswith("slm-"))
    n_local = sum(x["first_n"] for x in build if x["agent"].startswith("slm-"))
    tiles = [("Evidence level", f'{rep["evidence"]["level"]}', rep["evidence"]["name"]),
             ("Custom agent, Resolved@1", "—" if me is None else f'{me["resolved_n"]} of {me["first_n"]}', "best arm, project builds"),
             ("All custom arms", f"{total_local} of {n_local}", "working project builds"),
             ("Harness controls", "valid" if c["valid"] else "NOT VALID", f'null {c["null_resolved"]}/{c["null_n"]}, oracle {c["oracle_resolved"]}/{c["oracle_n"]}')]
    overview = "".join(f"<h2>{e(f.replace('_', ' ').capitalize())}</h2>" + _family_table(s) for f, s in fams.items())
    if rep["comparisons"]:
        overview += "<h2>Paired comparisons</h2>" + _table(["Family", "A vs B", "Tasks", "A only", "B only", "Both", "Neither", "McNemar p", "Verdict"],
            [[e(p["family"]), e(f'{p["a"]} vs {p["b"]}'), str(p["n"]), str(p["a_only"]), str(p["b_only"]), str(p["both"]), str(p["neither"]), f'{p["p"]:.3f}', e(p["verdict"])] for p in rep["comparisons"]], {2, 3, 4, 5, 6, 7})
    costs = "".join(f"<h2>{e(f.replace('_', ' ').capitalize())}</h2>" + _cost_table(s, rep["pareto"]) for f, s in fams.items())
    costs += "<p class=muted>Local cost is an assumed machine rate per hour from the agent manifests, not a measured price. Saved runs have no recorded cost, so they show a dash.</p>"
    arch = "<h2>Robustness</h2>" + (_table(["Agent", "Perturbed task", "Control", "Attempts", "Change in success"], [[e(r["agent"]), e(r["task"]), e(r["control"]), str(r["n"]), _num(r["delta"], "{:+.2f}")] for r in rep["robustness"]], {3, 4}) if rep["robustness"] else "<p class=muted>No perturbed tasks attempted yet.</p>")
    if rep["scaling"]:
        arch += "<h2>Budget</h2>" + _table(["Agent", "Family", "Budget", "Resolved", "Attempts"], [[e(x["agent"]), e(x["family"]), e(x["budget"]), str(x["k"]), str(x["n"])] for x in rep["scaling"]], {3, 4})
    arch += "<h2>Failure categories</h2>" + _table(["Agent", "Primary failure"], [[e(a), e(", ".join(f"{k} {v}" for k, v in sorted(cs.items(), key=lambda kv: -kv[1])))] for a, cs in sorted(rep["failures"].items())])
    if rep["safety"]:
        arch += "<h2>Safety</h2><p class=muted>Kept apart from the coding scores.</p>" + _table(["Agent", "Task", "Resolved", "Injected action taken", "Outside scope"], [[e(x["agent"]), e(x["task"]), "yes" if x["resolved"] else "no", e(", ".join(x["canaries_tripped"]) or "none"), e(", ".join(x["out_of_scope"]) or "none")] for x in rep["safety"]])
    trials = '<input id=filter placeholder="Filter by agent, task or failure" style="width:100%;padding:8px;font:inherit;margin-bottom:8px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px" aria-label="Filter trials"><div id=trials class=scroll style="white-space:normal">' + "".join(_trial_block(r, path.parent) for r in sorted(rows, key=lambda r: (r["provenance"] != "harness", r["agent"], r["task"]))) + "</div>"
    doc = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Agent Evaluation</title><style>{CSS}</style></head><body>
<h1>Agent evaluation</h1><p class=muted>{rep["n_trials"]} recorded trials on development tasks. {e(rep["evidence"]["why"])}.</p>
<div class=tiles>{"".join(f'<div class=tile><span class=muted>{e(a)}</span><b>{e(b)}</b><span class=muted>{e(d)}</span></div>' for a, b, d in tiles)}</div>
<nav role=tablist><button role=tab data-view=overview aria-selected=true>Overall</button><button role=tab data-view=costs aria-selected=false>Cost and latency</button><button role=tab data-view=arch aria-selected=false>Architecture</button><button role=tab data-view=trials aria-selected=false>Trials</button></nav>
<section data-view=overview>{overview}</section><section data-view=costs hidden>{costs}</section><section data-view=arch hidden>{arch}</section><section data-view=trials hidden>{trials}</section><script>{JS}</script></body></html>"""
    path.write_text(doc)
    return path
