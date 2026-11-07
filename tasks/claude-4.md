# claude-4 — Manager & baselines (round 1)

Read `tasks/PROTOCOL.md` first. You own `slm/manager/`, `slm/baselines/`, `slm/llm/hosted.py`,
`modal_apps/manager_app.py`, `tests/test_manager*.py`, `tests/test_baselines*.py`.

## What exists
- `slm/manager/manager.py`: `MANAGER_SYSTEM` (names the four specialists, their kinds, the rules),
  `user_prompt`, `plan`, `format_example`.
- `slm/manager/score.py`: `PlanScore(valid, deps_satisfied, domain_coverage, task_recall,
  task_precision, isomorphic)`, `score_plan`, `score_json`, `summarize`.
- `slm/manager/data.py`: `sft_rows` from the generated briefs (gold plans).
- `slm/manager/train_logic.py`: chat turns, label building (never truncate), length stats,
  `score_outputs`, `summarize_records`, `retry_prompt`, `plan_json_schema`.
- `modal_apps/manager_app.py`: `train_manager` (Qwen3-1.7B + LoRA), `eval_manager` (guided decoding,
  greedy + one retry, plan export for the pipeline).
- `slm/baselines/monolith.py`: one-call monolith graded through `integrate`, and `single_clients`
  for the single-generalist arm.

## Round 1 tasks
1. **Train and report.** `uv run modal run modal_apps/manager_app.py::train --run m1 --n-examples 4000
   --epochs 2`, then `::evaluate --run m1 --split dev` and `--split test`. Report plan validity,
   task recall/precision, `deps_satisfied`, and length stops. Cap: **$15**.
2. **Baselines on the same briefs.** Monolith and single-generalist arms over dev (limit 40). Report
   deliverable pass rate and the first failing check for each, plus calls/tokens per project.
3. **Failure attribution.** Extend scoring so a failed project is attributed to `manager` (invalid
   plan, or an interface the plan never wires: `deps_satisfied=False`), `specialist` (a task whose
   artifact failed its contract), or `integration` (all tasks fine, a seam check failed). One
   function, pure logic over the trace + plan, tested offline.
4. **Plan prompt hygiene.** Ensure the manager prompt and `plan_json_schema()` stay in sync with
   `slm/contracts.ProjectPlan` (a test that the schema lists every domain and kind from
   `slm/domains.py`).
5. **Export for the pipeline.** `eval_manager(export_plans=True)` must write
   `/vol/results/plans/{run}-{split}.jsonl` with one line per project; add a loader + test so
   claude-3 can dispatch exported plans without re-planning.

## Definition of done
- `uv run pytest -q` passes offline; the attribution function is unit-tested with a hand-built trace.
- PR body: manager eval table (dev + test), baseline table, attribution shares, $ spend.
- No new dependency without a one-line justification in `pyproject.toml`.
