# nova-tui

The terminal UI for Minerva: it starts `minerva build` runs, follows them live, and shows everything they produced.
It also still watches the older four-specialist pipeline (`slm run` traces) and compares the architecture arms recorded
by `python -m slm.arch run`. Built with [ratatui](https://ratatui.rs).

```
cd tui
cargo run --release                          # r: new build, then type what you want and how it should look
cargo run --release -- --build ../runs/<dir> # open one Minerva run
cargo run --release -- --demo                # synthetic slm run, no python needed
cargo run --release -- --print all --size 80x24 --build ../runs/<dir>   # render every view as text and exit
```

The repo root is auto-detected (walks up to the folder with `pyproject.toml` + `slm/`), or pass `--root <path>`.

## Minerva builds

`r` opens the new-build dialog: **What** (goes to the manager and backend), **Look** (goes only to the frontend),
**Engine**, **Architect** (thinking or instruct), **Repairs** (0-3) and **Budget**. Engines, their prices and where they
send data come from `uv run minerva engines --json`, so the TUI hard-codes none of them. An offline build starts on
Enter. A build that costs money or sends data off the machine first shows the estimate, the budget cap (the pipeline's
hard stop) and where the data goes, and starts only on `y`.

The TUI runs `uv run minerva build ...` in its own process group and follows the run directory it prints first
(`run: runs/<date>-<slug>`): `events.jsonl` (stage start and end, $ and seconds, reused stages, the final status),
`ledger.jsonl`, `status.json`, the stage files, `project/`, the screenshots and `REPORT.md`. Files are re-read only when
they change. `x` sends Ctrl-C to the whole build: it saves what finished, records `stopped`, closes Modal's ephemeral
apps, and anything that ignores Ctrl-C gets SIGTERM, then SIGKILL. `e` resumes the selected build with `--out`, so
finished stages are reused rather than paid for again. Quitting while a build runs asks first, then stops it the
same way.

## Views

| key | view | a Minerva build | an `slm run` trace |
| --- | --- | --- | --- |
| 1 | Pipeline | the brief, every stage and frontend round with state, time, $ and detail; a run card with engine, where the data went, spend against budget | brief → manager → dispatch → integrator → deliverable, one lane per specialist, per-adapter cards |
| 2 | Tasks | the backend tasks each specialist wrote (files, the manager's domain summary), each frontend round (build errors, failed gates and tests, critic), the sign-up journey | every routed task: level, domain, adapter, time, failure reason |
| 3 | Timeline | one bar per stage from the events, reused stages dimmed; wall, model and audit time, $ spent | Gantt of tasks, specialists in flight, parallel speedup |
| 4 | Deliverable | `REPORT.md`, `project/` and the screenshots (`O` opens one in your viewer) | `out/deliverable/<project_id>/` |
| 5 | Log | output of the job started from the TUI | same |
| 6 | Arms | `slm.arch` results | same |
| 7 | Report | `REPORT.md`, scrollable | (builds only) |

Traces from `slm.arch run` (`out/arch/<run>/traces/<arm>--<project>.jsonl`) show up in the runs list
next to `.slm/traces`, and their Deliverable view opens `out/arch/<run>/files/<arm>/<project>/`.

Keys: `r` new build, `e` resume the selected build, `x` stop, `O` open the selected file, `J`/`K` scroll the preview
or report, `tab`/`1-7` views, `h/l` focus runs/main, `j/k` move, `T` run the older `slm run` with the footer's options
(`+/-` project, `g` gold, `p` parallel, `s` split), `[`/`]` arch run, `o` arms grade, `d` demo, `R` replay demo, `?`
help, `q` quit.

## Code map

| file | job |
| --- | --- |
| `src/build.rs` | a Minerva run directory: events (only the latest attempt), stage rows in pipeline order, rounds, backend tasks, journey, files; runs from before events.jsonl are read from their stage files |
| `src/form.rs` | the new-build dialog: text inputs, engine list from `minerva engines --json`, validation, the cost and privacy confirmation |
| `src/ui/build.rs` | the Pipeline, Tasks, Timeline and Report views for a build |
| `src/trace.rs` | parse JSONL `TraceEvent`s, derive tasks / verdict / per-adapter stats (tolerates a half-written last line) |
| `src/app.rs` | state + key handling, polls the selected trace every 120 ms |
| `src/runner.rs` | spawns `uv run minerva build ...` or `uv run slm run ...` in its own process group, streams output, catches the `run:` and `trace:` lines, stops with SIGINT then escalates |
| `src/arch.rs` | `slm.arch` results: load, rescore with run checks, per-arm summary (mirrors `slm/arch/__main__.py::summarize` without the bootstrap CIs) |
| `src/demo.rs` | synthetic 12-task run that replays over ~9 s (the Arms view uses made-up rows in demo mode, labelled as such) |
| `src/ui/*.rs` | one file per view, `theme.rs` has the palette (one color per domain) |

`cargo test` renders every view against the demo run and two Minerva build fixtures (`tests/fixtures/`: a finished
real-model run and a resumed one still running) at 80x24 and 160x48, and checks the dialog, the parser and that a stop
reaches the whole process group. `NOVA_SHOTS=<dir> cargo test`
also writes each view as colored HTML, handy for screenshots.

## Ideas not done yet

- show the manager's actual plan (tasks + requires/provides) before dispatch, once the plan
  event carries it (today it only has the task count)
- bootstrap CIs and the Elo table in the Arms view (today: point estimates and paired means)
- integrator seam checks per file once they land in the trace

## Status

- Minerva builds (2026-11-07, branch `tui/minerva-builds`): driven end to end through a pseudo-terminal against
  real offline builds. `r` with what and look started a build that the views followed live to
  `functional_with_defects`; `x` during the frontend audit recorded `stopped` and left no process behind; `q` during
  a build asked first, then stopped it; `e` on the stopped build reused plan, backend, intent and the Architect and
  re-ran only the interrupted audit onwards. Not yet tried with a real-model (Modal) build from the TUI.
- `cargo build` and `cargo test` are clean (Rust 1.98, ratatui 0.30, crossterm 0.29, no new crates); CI runs them on
  every push that touches `tui/`, against the committed `Cargo.lock`.
- Tests: trace parsing (including pydantic's null-everywhere lines), task/verdict derivation,
  arms summary + paired deltas, run-check rescoring, arch trace → files mapping, and every view
  rendered at two sizes.
- Checked against real output: traces from `uv run slm run --project 0` and `--project 2 --no-parallel`,
  and `results.jsonl` rows produced by `slm.arch.__main__.grade_tree` (8 rows, gold-G4 vs a mono arm with
  the network files removed). Not yet tried against a full `slm.arch run` with a live model.
- Real plans name tasks `t1..tN`; the views label them with their kind (`t4 session`) and show the spec,
  read from the integrator's `README.md` in the deliverable.
- Works down to 80x24: narrower sidebar, one-line stage list instead of boxes, no timings in lanes.
- Relation to `slm code` (Textual workbench): that one is for writing a brief and editing the files of an `slm run`;
  this one drives Minerva builds and monitors traces and experiment results. They don't share code.
