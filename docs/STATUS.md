# Status

Last updated 2026-11-07, when the TUI started driving Minerva builds. Update this file in the PR that changes the
picture. The detailed record of the pipeline (what has been shown, decisions, open issues) is in
[`consolidation/STATUS.md`](consolidation/STATUS.md), [`consolidation/DECISIONS.md`](consolidation/DECISIONS.md)
and [`consolidation/ISSUES.md`](consolidation/ISSUES.md).

## Works today

- **The TUI drives Minerva builds.** `cd tui && cargo run --release`, then `r`: what you want, how it should look,
  engine, Architect, repairs, budget. Real-model builds show their estimate, the budget cap and where the data goes
  (from `uv run minerva engines`) and start only on `y`. The views follow the run live from its `events.jsonl` and show
  stages, frontend rounds, the journey, cost and time, `project/`, the screenshots and `REPORT.md`. `x` stops a build
  cleanly (Ctrl-C to its process group; it records `stopped`), `e` resumes it without paying again for finished
  stages. Checked end to end through a pseudo-terminal on offline builds; not yet with a Modal build.
- **`minerva build`, offline.** `uv run minerva build "Track invoices" --engine offline` plans with a gold
  template, writes the gold backend, audits the plain reference UI on real Postgres, FastAPI and a browser, runs
  the sign-up journey and writes `runs/<date>-<slug>/project/` plus `REPORT.md`
  (status `functional_with_defects`, correctly, since no Critic runs offline).
- **Tests.** `uv run pytest`: 537 passed, 27 skipped on macOS (Minverva's previous 403 tests are all still in the
  suite, unchanged or extended). `MINERVA_STACK=1 uv run pytest tests/test_minerva.py tests/test_minerva_events.py`
  runs the real-stack tests. `cd tui && cargo test`: 21 passed.
- **The old flow.** `uv run slm run --project 0`, `uv run slm ui`, `uv run slm code` and the `slm.arch` results.

## Shown once on real models (Modal)

- One full run ($0.58): the manager and backend worked; both generated UIs failed `tsc`, so it shipped the
  labelled fallback UI. One more run stopped at a false seam failure ($0.15). See
  [`consolidation/STATUS.md`](consolidation/STATUS.md).

## Not done yet

- **A generated UI that passes the audit** on a real run.
- **Apps beyond title-only rows** (consolidation ISSUES #3).
- **The headline comparison:** manager + specialists vs single generalist vs monolith (`PLAN.md`, H1-H3).

## Known caveats

- Gold artifacts are templates with the entity name swapped in; trained backend output is often byte-identical to
  them.
- `initdb` needs a UTF-8 locale; run the stack tests with `LANG=en_US.UTF-8` if your shell has none.

## Next

1. Self-test: build real things you need through the TUI (offline first, then Modal with your OK on each run), and
   record what you'd keep. Findings go in `docs/consolidation/ISSUES.md`.
2. Fix the Architect's `ApiError` compile failure (the one real run's frontend never built).
3. Opt-in, per brief: the same brief through Claude for a blind side-by-side, to test "matches LLM quality".
