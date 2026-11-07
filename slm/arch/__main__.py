"""python -m slm.arch run | report : primary-agent architecture experiments on a local model ($0).

    uv run python -m slm.arch run --run a1 --arms mgr-G4,mono --per-template 1
    uv run python -m slm.arch report --run a1
    uv run python -m slm.arch run --run a1 --arms base-opus,base-codex    # hosted, uses your CLI logins
    uv run python -m slm.arch compare --run a1    # best architecture, then head to head with the baselines

Results are appended one JSON line per (arm, project) to out/arch/<run>/results.jsonl, so a run
can be stopped and resumed; finished pairs are skipped. Projects run one at a time (latency is
measured at concurrency 1); arms are interleaved per project so partial results stay paired.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import typer

from slm.arch.runner import ARMS, BASELINES, IMPORTED_ARMS, LOCAL_ARMS, run_arm

app = typer.Typer(no_args_is_help=True, help="Primary-agent architecture experiments.")
SEED = 20261103
MIN_PROJECTS_FOR_VERDICT = 5


def projects(per_template: int):
    from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES
    from slm.bench.projects import generate_balanced

    return (generate_balanced(per_template * len(TRAIN_TEMPLATES), "dev", SEED)
            + generate_balanced(per_template * len(HELDOUT_TEMPLATES), "test", SEED))


def _load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


REFUSED_NAME = "_refused_paths.json"


def save_files(folder: Path, files) -> None:
    """Keep what an arm produced, so it can be re-graded later without running the model again. Paths that would
    leave the folder aren't written; they are listed so the run check can still mark them as failures."""
    from slm.ui.workspace import safe_target

    refused = []
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        target = safe_target(folder, f.path)
        if target is None:
            refused.append(f.path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.content)
    if refused:
        (folder / REFUSED_NAME).write_text(json.dumps(refused))


def load_files(folder: Path) -> list:
    from slm.contracts import ArtifactFile

    files = []
    for f in sorted(folder.rglob("*")):
        if f.is_file() and not f.is_symlink() and f.name not in (REFUSED_NAME, "CONTRACT.md"):
            try:
                files.append(ArtifactFile(path=f.relative_to(folder).as_posix(), content=f.read_text()))
            except UnicodeDecodeError:
                continue
    refused = folder / REFUSED_NAME
    if refused.exists():
        files += [ArtifactFile(path=p, content="") for p in json.loads(refused.read_text())]
    return files


def with_run_scores(rows: list[dict], checks: list[dict]) -> list[dict]:
    """Result rows rescored by the run check, so every report and selection can use it unchanged. A row with no run
    check is left out rather than counted as a failure."""
    by_key = {(c["arm"], c["project_id"]): c for c in checks}
    out = []
    for r in rows:
        c = by_key.get((r["arm"], r["project_id"]))
        if c is not None:
            out.append({**r, "gold_task_rate": c["rate"], "gold_pass": c["passed"], "by_domain": c["by_group"],
                        "_spec": r["gold_task_rate"]})
    return out


def scored_rows(root: Path, score: str) -> list[dict]:
    if score not in ("run", "spec"):
        raise typer.BadParameter("score must be run or spec")
    rows = _load(root / "results.jsonl")
    return rows if score == "spec" else with_run_scores(rows, _load(root / "runchecks.jsonl"))


@app.command()
def run(
    run: str = "a1",
    arms: str = typer.Option(",".join(LOCAL_ARMS), help=f"comma-separated arms; hosted: {','.join(BASELINES)}"),
    per_template: int = 1,
    pick: str = typer.Option("", help="comma-separated project indexes, e.g. 0,1,2,5,8"),
    limit: int = 0,
    model: str = "qwen3.5:4b",
    opus_model: str = "claude-opus-5-5",
    codex_model: str = typer.Option("", help="codex model id; empty uses the CLI's default"),
    out: str = "out/arch",
):
    """Run every arm on every project (resumable). Manager plans are cached per project."""
    from slm.arch.runner import PlanStats, make_plan
    from slm.llm.cli import BackendUnavailable, ClaudeCLIClient, CodexCLIClient
    from slm.llm.ollama import OllamaClient
    from slm.trace import Tracer, load

    hosted = {"base-opus": lambda: ClaudeCLIClient(opus_model), "base-codex": lambda: CodexCLIClient(codex_model or None)}
    clis = {"base-opus": ClaudeCLIClient, "base-codex": CodexCLIClient}

    arm_list = [a.strip() for a in arms.split(",") if a.strip()]
    bad = [a for a in arm_list if a not in ARMS]
    if bad:
        raise typer.BadParameter(f"unknown arms {bad}; choose from {ARMS}")
    down = {a for a in arm_list if a in clis and not clis[a].available()}
    for a in sorted(down):
        typer.echo(f"skipping {a}: `{clis[a].binary}` is not installed")
    root = Path(out) / run
    root.mkdir(parents=True, exist_ok=True)
    results_p, plans_p = root / "results.jsonl", root / "plans.jsonl"
    done = {(r["arm"], r["project_id"]) for r in _load(results_p)}
    plans = {r["project_id"]: PlanStats.load(r["stats"]) for r in _load(plans_p)}
    ps_all = projects(per_template)
    ps = [ps_all[int(i)] for i in pick.split(",")] if pick else ps_all[: limit or None]
    (root / "config.json").write_text(json.dumps({"model": model, "arms": arm_list, "per_template": per_template,
                                                  "projects": [p.id for p in ps], "seed": SEED,
                                                  "ollama_version": OllamaClient(model).server_version()}, indent=1))
    # mgr-G4-repair also yields mgr-G4, so never run mgr-G4 on its own when both are asked for
    run_arms = [a for a in arm_list if not (a == "mgr-G4" and "mgr-G4-repair" in arm_list)]
    todo = [(p, a) for p in ps for a in run_arms if (a, p.id) not in done]
    typer.echo(f"{len(todo)} runs to do ({len(done)} results already) -> {results_p}")
    for i, (p, a) in enumerate(todo, 1):
        if a in down:
            continue
        whole_project = a in ("mono", "mgr-Nto1")  # one call writes every file
        client = hosted[a]() if a in hosted else OllamaClient(
            model, num_predict=6144 if whole_project else 1536, num_ctx=12288 if whole_project else 8192)
        plan_tracer = Tracer(run_id=f"plan--{p.id}", trace_dir=root / "traces")
        if a.startswith("mgr-") and p.id not in plans:
            try:
                st = asyncio.run(make_plan(p, client, plan_tracer))
            except BackendUnavailable as e:
                typer.echo(f"[{i}/{len(todo)}] {a} {p.template_id}: stopping this arm, no result recorded: {e}")
                down.add(a)
                continue
            plans[p.id] = st
            with plans_p.open("a") as f:
                f.write(json.dumps({"project_id": p.id, "stats": st.dump()}) + "\n")
            typer.echo(f"  plan {p.template_id}: valid={st.valid} recall={st.recall:.2f} "
                       f"tok_out={st.tok_out} {st.seconds:.0f}s" + (f" err={st.error[:80]}" if st.error else ""))
        plan_events = [e for e in load(plan_tracer.path) if e.kind == "llm"] if plan_tracer.path.exists() else []
        tracer = Tracer(run_id=f"{a}--{p.id}", trace_dir=root / "traces")
        t0 = time.time()
        try:
            results = asyncio.run(run_arm(a, p, client, tracer, plans.get(p.id), plan_events))
        except BackendUnavailable as e:  # not the model's fault: no result, and later runs can retry
            typer.echo(f"[{i}/{len(todo)}] {a} {p.template_id}: stopping this arm, no result recorded: {e}")
            down.add(a)
            continue
        with results_p.open("a") as f:
            for res in results:
                if (res.arm, p.id) not in done:
                    save_files(root / "files" / res.arm / p.id, res.files)
                    f.write(json.dumps(res.as_dict()) + "\n")
                    done.add((res.arm, p.id))
        for res in results:
            typer.echo(f"[{i}/{len(todo)}] {res.arm:14} {p.template_id:16} gold_pass={int(res.gold_pass)} "
                       f"tasks={res.gold_task_rate:.2f} calls={res.calls} tok_out={res.tok_out} "
                       f"crit_tok={res.crit_tok_out} wall={res.wall_s:.0f}s (this run {time.time() - t0:.0f}s)"
                       + (f" err={res.error[:80]}" if res.error else ""))


def summarize(rows: list[dict], ref: str = "mgr-G4") -> list[dict]:
    from slm.bench.stats import _boot, accuracy_ci, percentile

    by_arm: dict[str, list[dict]] = {}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)
    ref_rows = {r["project_id"]: r for r in by_arm.get(ref, [])}
    out = []
    for arm in [a for a in (*ARMS, *IMPORTED_ARMS) if a in by_arm]:
        rs = by_arm[arm]
        cl = [r["template_id"] or r["project_id"] for r in rs]
        acc, lo, hi = accuracy_ci([r["gold_pass"] for r in rs], cl)
        task, tlo, thi = _boot([r["gold_task_rate"] for r in rs], cl, 2000, 0)
        walls = [r["wall_s"] for r in rs]
        row = {
            "arm": arm, "n": len(rs), "gold_pass": acc, "gold_pass_ci": (lo, hi),
            "task_rate": task, "task_rate_ci": (tlo, thi),
            "own_pass": sum(r["own_pass"] for r in rs) / len(rs),
            "plan_recall": _mean([r["plan_recall"] for r in rs if r["plan_recall"] is not None]),
            "plan_valid": _mean([float(r["plan_valid"]) for r in rs if r["plan_valid"] is not None]),
            "p50_s": percentile(walls, 50), "p90_s": percentile(walls, 90),
            "crit_tok": _mean([r.get("crit_tok_out", 0) for r in rs]),
            "crit_s": _mean([r.get("crit_s", 0.0) for r in rs]),
            "calls": _mean([r["calls"] for r in rs]),
            "tok_out": _mean([r["tok_out"] for r in rs]), "tok_in": _mean([r["tok_in"] for r in rs]),
            "errors": sum(1 for r in rs if r["error"]),
        }
        paired = [(r, ref_rows[r["project_id"]]) for r in rs if r["project_id"] in ref_rows]
        if arm != ref and len(paired) >= 2:
            pcl = [a["template_id"] or a["project_id"] for a, _ in paired]
            row["d_task_vs_ref"] = _boot([a["gold_task_rate"] - b["gold_task_rate"] for a, b in paired], pcl, 2000, 0)
            row["d_wall_vs_ref"] = _mean([a["wall_s"] / max(b["wall_s"], 1e-6) for a, b in paired])
            row["d_crit_vs_ref"] = _mean([a.get("crit_tok_out", 0) / max(b.get("crit_tok_out", 0), 1) for a, b in paired])
        out.append(row)
    return out


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def _f(x) -> str:
    return "—" if x is None else f"{x:.2f}"


def table(summary: list[dict], ref: str = "mgr-G4") -> str:
    head = ("| arm | n | gold pass (95% CI) | task pass (95% CI) | Δ task vs " + ref
            + " | plan recall | wall p50 s | wall ×ref | crit-path tok | crit ×ref | calls | out tok |\n"
            + "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    lines = []
    for r in summary:
        d = r.get("d_task_vs_ref")
        lines.append(
            f"| {r['arm']} | {r['n']} | {r['gold_pass']:.2f} ({r['gold_pass_ci'][0]:.2f}–{r['gold_pass_ci'][1]:.2f}) "
            f"| {r['task_rate']:.2f} ({r['task_rate_ci'][0]:.2f}–{r['task_rate_ci'][1]:.2f}) "
            f"| {'—' if d is None else f'{d[0]:+.2f} ({d[1]:+.2f}…{d[2]:+.2f})'} "
            f"| {_f(r['plan_recall'])} | {r['p50_s']:.0f} "
            f"| {_f(r.get('d_wall_vs_ref'))} "
            f"| {r['crit_tok']:.0f} | {_f(r.get('d_crit_vs_ref'))} "
            f"| {r['calls']:.1f} | {r['tok_out']:.0f} |")
    return head + "\n".join(lines)


def elo_inputs(rows: list[dict]) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """Arm -> item -> score, and item -> project. An item is one (project, domain): the arm with the
    higher domain task-pass rate on that project wins, equal rates draw. Domains an arm has no rate for
    (e.g. `mono`, which plans nothing) score its project-level gold_task_rate."""
    results: dict[str, dict[str, float]] = {}
    clusters: dict[str, str] = {}
    domains = sorted({d for r in rows for d in (r.get("by_domain") or {})})
    for r in rows:
        bd = r.get("by_domain") or {}
        for d in domains:
            item = f"{r['project_id']}/{d}"
            results.setdefault(r["arm"], {})[item] = bd.get(d, r["gold_task_rate"])
            clusters[item] = r["project_id"]
    return results, clusters


def elo_table(rows: list[dict]) -> str:
    from slm.bench.elo import elo_ci, to_markdown

    results, clusters = elo_inputs(rows)
    return to_markdown(elo_ci(results, clusters), results).replace("accuracy (%)", "mean domain pass (%)")


@app.command()
def report(run: str = "a1", out: str = "out/arch", ref: str = "mgr-G4"):
    """Per-arm table: gold pass, task pass, paired deltas vs the reference arm, latency, calls, tokens;
    then Bradley-Terry Elo over (project, domain) matches."""
    rows = _load(Path(out) / run / "results.jsonl")
    if not rows:
        raise typer.Exit("no results yet")
    s = summarize(rows, ref)
    typer.echo(table(s, ref))
    typer.echo("\nElo (one match per project x domain, higher pass rate wins; 95% CI resamples projects)\n")
    typer.echo(elo_table(rows))
    (Path(out) / run / "summary.json").write_text(json.dumps(s, indent=1))


# --- which architecture is best, and how does it do against hosted models ---------


def _split(project_id: str) -> str:
    return "test" if project_id.startswith("proj-test-") else "dev"


def _paired(rows: list[dict], arms: list[str], split: str | None = None) -> list[dict]:
    """Rows of `arms` on the projects (of one split, if given) that every one of those arms finished."""
    rows = [r for r in rows if r["arm"] in arms and (split is None or _split(r["project_id"]) == split)]
    ran = [{r["project_id"] for r in rows if r["arm"] == a} for a in arms]
    common = set.intersection(*ran) if ran else set()
    return [r for r in rows if r["project_id"] in common]


def select_best(rows: list[dict]) -> tuple[str, list[dict]]:
    """The deployable architecture with the top Elo, chosen on dev projects only (EXPERIMENTS.md), so the
    held-out briefs stay fair for the comparison afterwards. gold-* is left out: it is handed the perfect plan.

    Arms that haven't finished the dev projects the others share would shrink the pairing, so it uses the
    largest set of arms that reaches the most projects. Returns (best arm, the rows it was chosen on)."""
    from slm.bench.elo import elo

    dev = [r for r in rows if _split(r["project_id"]) == "dev" and r["arm"] in LOCAL_ARMS
           and not r["arm"].startswith("gold-")]
    count: dict[str, set[str]] = {}
    for r in dev:
        count.setdefault(r["arm"], set()).add(r["project_id"])
    if not count:
        raise ValueError("no architecture has dev results yet")
    most = max(len(v) for v in count.values())
    paired = _paired(dev, [a for a, v in count.items() if len(v) == most])
    results, clusters = elo_inputs(paired)
    ratings = elo(results, clusters)
    return max(sorted(ratings), key=lambda a: ratings[a]), paired


def _h2h_line(label: str, h: dict) -> str:
    if h["n_clusters"] < MIN_PROJECTS_FOR_VERDICT:  # too few projects for the bootstrap CI to mean anything
        verdict = f"too few projects to call (needs {MIN_PROJECTS_FOR_VERDICT})"
    elif h["lo"] <= 0 <= h["hi"]:
        verdict = "no clear winner"
    else:
        verdict = f"{h['a'] if h['diff'] > 0 else h['b']} is ahead"
    return (f"| {label} | {h['b']} | {h['wins']}-{h['draws']}-{h['losses']} | {h['n_clusters']} "
            f"| {h['diff']:+.0f} ({h['lo']:+.0f} to {h['hi']:+.0f}) | {verdict} |")


def compare_report(rows: list[dict]) -> tuple[str, dict]:
    from slm.bench.elo import head_to_head

    best, chosen_on = select_best(rows)
    parts = [f"## Best architecture: `{best}`\n",
             f"Chosen on {len({r['project_id'] for r in chosen_on})} dev projects with Elo. "
             "One match per project x domain; the 95% CI resamples projects.\n", elo_table(chosen_on), ""]

    results, clusters = elo_inputs(chosen_on)
    rivals = sorted(a for a in results if a != best)
    parts += [f"\nIs `{best}` separated from the other architectures on those projects?\n",
              "| split | vs | W-D-L | projects | Elo gap (95% CI) | verdict |", "|---|---|---|---|---|---|"]
    parts += [_h2h_line("dev", head_to_head(results, best, a, clusters)) for a in rivals]
    out = {"best": best, "dev_projects": sorted({r["project_id"] for r in chosen_on}), "vs_baselines": []}

    present = sorted({r["arm"] for r in rows} & {*BASELINES, *IMPORTED_ARMS})
    parts += [f"\n## `{best}` vs hosted baselines\n"]
    if not present:
        parts.append("No baseline results yet. Run `python -m slm.arch run --arms base-opus,base-codex` first.")
    else:
        parts += ["Elo gap is the local system minus the baseline, so a negative gap means the baseline is ahead. "
                  "`dev` includes the projects the best arm was chosen on, so it flatters that arm; "
                  "`test` is held out.\n",
                  "| split | vs | W-D-L | projects | Elo gap (95% CI) | verdict |", "|---|---|---|---|---|---|"]
        for b in present:
            for split in ("test", "dev"):
                paired = _paired(rows, [best, b], split)
                if not paired:
                    parts.append(f"| {split} | {b} | no shared projects | 0 | — | — |")
                    continue
                res, cl = elo_inputs(paired)
                h = head_to_head(res, best, b, cl)
                parts.append(_h2h_line(split, h))
                out["vs_baselines"].append({"split": split, **h})
        shared = _paired(rows, [best, *present])
        if shared:
            parts += ["\nWhole deliverable and cost, on the projects they all finished:\n", table(summarize(shared, best), best)]
    return "\n".join(parts), out


def grade_tree(project, arm: str, folder: Path, calls: int = 0, seconds: float = 0.0):
    """Grade a project written to disk exactly as run_mono grades a one-call reply. Only regular files inside the
    folder count, at the paths relative to it."""
    from slm.arch.runner import Result, gold_grade

    files = load_files(folder)
    res = Result(arm=arm, project_id=project.id, template_id=project.template_id, calls=calls, wall_s=seconds)
    gold_grade(project, files, res)
    res.own_pass = res.gold_pass
    return res


@app.command("grade-dir")
def grade_dir(
    folder: str = typer.Argument(..., help="holds one sub-folder per project id"),
    run: str = "a1",
    arm: str = "opus-multiagent",
    out: str = "out/arch",
    calls: int = typer.Option(0, help="agents per project, for the report"),
):
    """Grade projects built outside the harness and record them, skipping projects already recorded."""
    if arm not in IMPORTED_ARMS:
        raise typer.BadParameter(f"choose from {IMPORTED_ARMS}")
    results_p = Path(out) / run / "results.jsonl"
    done = {(r["arm"], r["project_id"]) for r in _load(results_p)}
    for p in projects(1):
        tree = Path(folder) / p.id
        if not tree.is_dir() or (arm, p.id) in done:
            continue
        res = grade_tree(p, arm, tree, calls=calls)
        save_files(Path(out) / run / "files" / arm / p.id, res.files)
        with results_p.open("a") as f:
            f.write(json.dumps(res.as_dict()) + "\n")
        typer.echo(f"{arm} {p.template_id:16} gold_pass={int(res.gold_pass)} tasks={res.gold_task_rate:.2f} "
                   f"first_fail={res.first_fail} by_domain={ {k: round(v, 2) for k, v in res.by_domain.items()} }")


def slim_losses(row: dict, base: dict) -> list[str]:
    """Where a slim result is worse than the baseline on the same project."""
    worse = [row["template_id"]] if row["gold_task_rate"] < base["gold_task_rate"] or (
        base["gold_pass"] and not row["gold_pass"]) else []
    return worse + [f"{row['template_id']}/{d}" for d, v in row["by_domain"].items() if v < base["by_domain"].get(d, 0)]


def pick_combo_arm(rows: list[dict], baseline: str = "mgr-G4") -> str:
    """The combined arm at the smallest prompt level that finished every baseline project and lost nothing;
    the full prompt if none did."""
    base = {r["project_id"]: r for r in rows if r["arm"] == baseline}
    for level in (3, 2, 1):
        mine = [r for r in rows if r["arm"] == f"mgr-slim{level}" and r["project_id"] in base]
        if base and len(mine) == len(base) and not any(slim_losses(r, base[r["project_id"]]) for r in mine):
            return f"mgr-combo-s{level}"
    return "mgr-combo-s0"


@app.command("pick-combo")
def pick_combo(run: str = "a1", out: str = "out/arch", baseline: str = "mgr-G4", score: str = "run"):
    """Print the combined arm to run, from the slim results so far."""
    typer.echo(pick_combo_arm(scored_rows(Path(out) / run, score), baseline))


@app.command("pick-best")
def pick_best(run: str = "a1", out: str = "out/arch", score: str = "run"):
    """Print the best architecture on the dev projects."""
    typer.echo(select_best(scored_rows(Path(out) / run, score))[0])


@app.command("setup-grader")
def setup_grader():
    """Install the run check's own toolchain under out/grader: embedded Postgres, FastAPI, esbuild and React."""
    from slm.bench.runcheck import setup

    setup()


@app.command("check")
def check(run: str = "a1", out: str = "out/arch", arm: str = typer.Option("", help="only this arm")):
    """Parse and really run every saved project that has no run check yet. Safe to repeat."""
    from slm.bench.runcheck import GraderUnavailable, check_project

    root = Path(out) / run
    by_id = {p.id: p for p in projects(1)}
    done = {(c["arm"], c["project_id"]) for c in _load(root / "runchecks.jsonl")}
    n = 0
    for folder in sorted((root / "files").glob("*/*")):
        a, pid = folder.parent.name, folder.name
        if (arm and a != arm) or (a, pid) in done or pid not in by_id:
            continue
        try:
            rep = check_project(load_files(folder), by_id[pid].plan)
        except GraderUnavailable as e:  # the toolchain failed, not the project
            typer.echo(f"{a} {pid}: stopping, no result recorded: {e}")
            raise typer.Exit(1) from e
        with (root / "runchecks.jsonl").open("a") as f:
            f.write(json.dumps({"arm": a, "project_id": pid, **rep}) + "\n")
        n += 1
        typer.echo(f"{a:15} {by_id[pid].template_id:16} passed={int(rep['passed'])} rate={rep['rate']:.2f} "
                   f"{ {k: round(v, 2) for k, v in rep['by_group'].items()} }")
    typer.echo(f"{n} projects checked")


def run_table(rows: list[dict], checks: list[dict]) -> str:
    """Spec conformance next to whether the code works, for the projects every listed arm finished."""
    from slm.bench.elo import elo_ci

    merged = with_run_scores(rows, checks)
    if not merged:
        return "No run checks yet."
    arms = sorted({r["arm"] for r in merged})
    most = max(sum(r["arm"] == a for r in merged) for a in arms)
    arms = [a for a in arms if sum(r["arm"] == a for r in merged) == most]
    paired = _paired(merged, arms)
    if not paired:
        return "No projects are shared by the arms checked so far."
    results, clusters = elo_inputs(paired)
    cis = elo_ci(results, clusters)
    lines = ["| rank | arm | Elo (run) | 95% CI | run score | fully works | parse | database | api | auth | frontend | spec task pass |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    by_arm: dict[str, list[dict]] = {}
    for r in paired:
        by_arm.setdefault(r["arm"], []).append(r)
    for i, (a, (r, lo, hi)) in enumerate(sorted(cis.items(), key=lambda kv: -kv[1][0]), 1):
        rs = by_arm[a]
        n = len(rs)
        group = lambda g: sum(x["by_domain"].get(g, 0) for x in rs) / n  # noqa: E731
        sp = sum(x["_spec"] for x in rs) / n
        lines.append(f"| {i} | {a} | {r:.0f} | {lo:.0f}-{hi:.0f} | {sum(x['gold_task_rate'] for x in rs) / n:.2f} "
                     f"| {sum(x['gold_pass'] for x in rs)} of {n} | {group('parse'):.2f} | {group('database'):.2f} "
                     f"| {group('api'):.2f} | {group('auth'):.2f} | {group('frontend'):.2f} | {sp:.2f} |")
    return f"{most} shared projects\n\n" + "\n".join(lines)


@app.command("run-report")
def run_report(run: str = "a1", out: str = "out/arch"):
    """Elo on whether projects really work, beside the old string-based score."""
    root = Path(out) / run
    typer.echo(run_table(_load(root / "results.jsonl"), _load(root / "runchecks.jsonl")))


def slim_report(rows: list[dict], baseline: str = "mgr-G4") -> str:
    """Each slim level against the baseline on shared projects. A level passes only if no project or domain got
    worse: a higher score elsewhere can't buy back a lost task."""
    base = {r["project_id"]: r for r in rows if r["arm"] == baseline}
    lines = [f"| level | projects | input tokens vs {baseline} | task pass | vs {baseline} | calls | worse on | verdict |",
             "|---|---|---|---|---|---|---|---|"]
    for arm in sorted(a for a in {r["arm"] for r in rows} if a.startswith("mgr-slim")):
        mine = [r for r in rows if r["arm"] == arm and r["project_id"] in base]
        if not mine:
            lines.append(f"| {arm} | 0 | — | — | — | — | — | no shared projects |")
            continue
        worse = [x for r in mine for x in slim_losses(r, base[r["project_id"]])]
        n = len(mine)
        tok = sum(r["tok_in"] for r in mine) / sum(base[r["project_id"]]["tok_in"] for r in mine)
        rate = sum(r["gold_task_rate"] for r in mine) / n
        delta = rate - sum(base[r["project_id"]]["gold_task_rate"] for r in mine) / n
        lines.append(f"| {arm} | {n} | {tok - 1:+.0%} | {rate:.3f} | {delta:+.3f} | {sum(r['calls'] for r in mine) / n:.1f} "
                     f"| {', '.join(sorted(set(worse))) or 'none'} | {'fails' if worse else 'holds so far'} |")
    return "\n".join(lines)


@app.command("slim")
def slim(run: str = "a1", out: str = "out/arch", baseline: str = "mgr-G4", score: str = "run"):
    """How far each prompt-size level cut input tokens, and whether anything got worse."""
    rows = scored_rows(Path(out) / run, score)
    if not rows:
        raise typer.Exit("no results yet")
    typer.echo(slim_report(rows, baseline))


@app.command()
def compare(run: str = "a1", out: str = "out/arch", score: str = "run"):
    """Pick the best architecture on dev projects, then compare its Elo with the hosted baselines."""
    root = Path(out) / run
    rows = scored_rows(root, score)
    if not rows:
        raise typer.Exit("no results yet")
    text, data = compare_report(rows)
    typer.echo(text)
    (root / "compare.md").write_text(text + "\n")
    (root / "compare.json").write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    app()
