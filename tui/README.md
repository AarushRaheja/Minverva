# nova-tui

Terminal UI for the NOVA pipeline (manager SLM → four specialists → integrator), built with
[ratatui](https://ratatui.rs). It reads the same traces every metric comes from
(`.slm/traces/*.jsonl`, see `slm/trace.py`), can start runs itself, and compares the architecture
arms recorded by `python -m slm.arch run` (`out/arch/<run>/results.jsonl`).

```
cd tui
cargo run --release -- --demo        # synthetic run, no python needed
cargo run --release                  # watch ../.slm/traces, press r to run a project
cargo run --release -- --trace ../.slm/traces/cli-dev-0000.jsonl
```

The repo root is auto-detected (walks up to the folder with `pyproject.toml` + `slm/`), or pass
`--root <path>`. Pressing `r` runs `uv run slm run --project N --split S --gold|--no-gold
--parallel|--no-parallel` in the root and jumps to the trace it prints.

## Views

| key | view | what it shows |
| --- | --- | --- |
| 1 | Pipeline | brief → manager → dispatch → integrator → deliverable, one lane per specialist with tasks grouped by dependency level, per-adapter calls/tokens/latency/pass gauge |
| 2 | Tasks | every routed task: level, domain, adapter, time, failure reason |
| 3 | Timeline | Gantt from `t_start`/`t_end`, specialists in flight, serial vs wall time (parallel speedup) |
| 4 | Deliverable | file tree under `out/deliverable/<project_id>/` with a code preview |
| 5 | Log | stdout/stderr of the run started with `r` |
| 6 | Arms | one row per architecture from `out/arch/<run>/results.jsonl`: deliverable pass, task pass, Δ task and wall-clock ratio paired against `mgr-G4`, plan recall, p50, critical-path tokens, calls; per-domain pass and most common first failing check for the selected arm. `o` switches to the run-check grade (`runchecks.jsonl`), `[`/`]` switch runs |

Traces from `slm.arch run` (`out/arch/<run>/traces/<arm>--<project>.jsonl`) show up in the runs list
next to `.slm/traces`, and their Deliverable view opens `out/arch/<run>/files/<arm>/<project>/`.

Keys: `r` run, `+/-` project, `g` gold plan, `p` parallel, `s` split, `x` stop, `tab`/`1-6`
views, `[`/`]` arch run, `o` arms grade, `h/l` focus runs/main, `j/k` move, `d` demo, `R` replay demo, `?` help, `q` quit.

## Code map

| file | job |
| --- | --- |
| `src/trace.rs` | parse JSONL `TraceEvent`s, derive tasks / verdict / per-adapter stats (tolerates a half-written last line) |
| `src/app.rs` | state + key handling, polls the selected trace every 120 ms |
| `src/runner.rs` | spawns `uv run slm run ...`, streams output, catches the `trace: <path>` line |
| `src/arch.rs` | `slm.arch` results: load, rescore with run checks, per-arm summary (mirrors `slm/arch/__main__.py::summarize` without the bootstrap CIs) |
| `src/demo.rs` | synthetic 12-task run that replays over ~9 s (the Arms view uses made-up rows in demo mode, labelled as such) |
| `src/ui/*.rs` | one file per view, `theme.rs` has the palette (one color per domain) |

`cargo test` renders every view against the demo run at 80x24 and 160x48. `NOVA_SHOTS=<dir> cargo test`
also writes each view as colored HTML, handy for screenshots.

## Ideas not done yet

- show the manager's actual plan (tasks + requires/provides) before dispatch, once the plan
  event carries it (today it only has the task count)
- bootstrap CIs and the Elo table in the Arms view (today: point estimates and paired means)
- integrator seam checks per file once they land in the trace

## Status

- Branch `tui/ratatui-ui`; everything lives under `tui/` (plus `.github/workflows/tui.yml`), so it
  merges cleanly into `main` and into `free-compute-ui`. The trace schema is identical on both.
- `cargo build` and `cargo test` are clean (Rust 1.97, ratatui 0.30, crossterm 0.29); CI runs them on
  every push that touches `tui/`. `Cargo.lock` is generated on first build.
- Tests: trace parsing (including pydantic's null-everywhere lines), task/verdict derivation,
  arms summary + paired deltas, run-check rescoring, arch trace → files mapping, and every view
  rendered at two sizes.
- Not yet tried by a human against a live `uv run slm run` / `slm.arch run`; parsing follows
  `slm/trace.py` and `slm/arch/runner.py::Result` field for field.
- Relation to `slm code` (Textual workbench on `free-compute-ui`): that one is for writing a brief
  and editing the files; this one is a read-only monitor for traces and experiment results. They
  don't share code.
