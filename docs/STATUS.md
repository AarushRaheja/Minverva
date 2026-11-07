# Status

Last updated 2026-11-07, at the import of the Minerva pipeline. Update this file in the PR that changes the
picture. The detailed record of the pipeline (what has been shown, decisions, open issues) is in
[`consolidation/STATUS.md`](consolidation/STATUS.md), [`consolidation/DECISIONS.md`](consolidation/DECISIONS.md)
and [`consolidation/ISSUES.md`](consolidation/ISSUES.md).

## Works today

- **`minerva build`, offline.** `uv run minerva build "Track invoices" --engine offline` plans with a gold
  template, writes the gold backend, audits the plain reference UI on real Postgres, FastAPI and a browser, runs
  the sign-up journey and writes `runs/<date>-<slug>/project/` plus `REPORT.md`
  (status `functional_with_defects`, correctly, since no Critic runs offline).
- **Tests.** `uv run pytest`: 527 passed, 26 skipped on macOS after the import (Minverva's previous 403 tests are
  all still in the suite, unchanged or extended). `MINERVA_STACK=1 uv run pytest tests/test_minerva.py` runs the
  real-stack tests.
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
