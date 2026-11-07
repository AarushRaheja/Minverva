# claude-1 — Project data & metrics (round 1)

Read `tasks/PROTOCOL.md` first. You own `slm/bench/`, `modal_apps/data_app.py`,
`tests/test_bench*.py`, `tests/test_domains*.py`.

## What exists
- `slm/domains.py` (frozen): four domains, task kinds, interface symbols, canonical paths, and the
  provide/use tokens the checker looks for.
- `slm/contracts.py` (frozen): `Task`, `ProjectPlan`, `Artifact`, `Deliverable`, `check_task`,
  `integrate`, `TrainExample`, `Project`, `PATHS`.
- `slm/bench/catalog.py`: ten templates (eight train, two held out), `build_plan`, `gold_artifact`,
  `gold_artifacts`. `slm/bench/projects.py`: `generate`, `generate_balanced`.
- `slm/bench/build.py`: writes `data/projects/{split}.jsonl`, `data/manager/{split}.jsonl`,
  `data/domains/{domain}.jsonl`, `data/manifest.json`.
- `slm/bench/score.py`: metrics from traces (deliverable pass rate, task accuracy by domain, plan
  validity, latency, calls/tokens) and `gate_ok` (the trainer's gate).

## Round 1 tasks
1. **Scale the data.** Raise `SETS` to 400 train / 40 dev / 80 test briefs. Keep the fixed-budget
   rule: every domain gets the same *number of tasks* as its share of the plans, and report that
   share in the manifest (`domains_meta.tasks`).
2. **Held-out discipline.** Add at least two more held-out templates with entities that share no
   stem with the training entities. Assert in a test that train and test templates are disjoint and
   that test entity names never appear in training descriptions.
3. **Harder briefs.** Add a difficulty knob to the generator: `easy` (as today), `hard` = extra
   entity, plus one optional "reports" requirement that becomes a `network/rest` task on a computed
   resource (still one canonical path per task). Do not change `slm/domains.py`; if a new kind is
   genuinely needed, file a contract request.
4. **Negative fixtures.** Build a `tests/test_bench_negatives.py` with one deliberately broken
   deliverable per integration check (`all_tasks_delivered`, `no_path_conflicts`,
   `requires_satisfied`, `frontend_endpoints_resolve`, `tables_defined`, `imports_resolve`,
   `guards_wired`) and assert exactly that check fails.
5. **Report numbers.** `uv run python -m slm.bench build --out out/data` (scale 0.1 is enough) and
   paste the manifest counters, plus the distribution of tasks per domain and dependency depth, into
   your PR.

## Definition of done
- `uv run pytest -q` passes; new tests cover every negative fixture and the disjointness rule.
- `build_all(scale=1.0)` runs in under ~10 minutes on CPU and is deterministic (same seed, same
  bytes).
- The manifest records: data_version, seed, git sha, per-split totals, per-template counts,
  tasks-per-project, depth, per-domain train/eval counts.
- Your PR body includes the numbers above and the Modal spend (this round should be **$0**; the
  build is CPU-only, so run it locally or on Modal's CPU function).
