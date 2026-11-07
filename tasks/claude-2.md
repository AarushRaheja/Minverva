# claude-2 — Specialist training factory (round 1)

Read `tasks/PROTOCOL.md` first. You own `slm/train/`, `modal_apps/train_app.py`,
`tests/test_train*.py`.

## What exists
- One adapter per domain, no atomicity sweep: `job_for(domain)`, `jobs(seed)`. Adapter names are
  `spec-database`, `spec-auth`, `spec-network`, `spec-frontend` (`slm/domains.py`).
- `slm/train/logic.py`: `load_examples` (reads `data/domains/{domain}.jsonl`, keeps its own domain),
  `check_counts` (fixed-budget guard against the manifest), `stratified_eval` (per kind),
  `per_kind_accuracy`, `needs_retry`, `is_done`, `registry_summary`.
- `modal_apps/train_app.py`: `train_domains` (all requested domains on one container, base model
  loaded once), gate = `bench.score.gate_ok` on generated artifacts, escalation = one retrain with
  +2 epochs below 0.90, `merge_registry`, `pending`.
- `slm/contracts.specialist_system` / `specialist_prompt` are the exact serving prompts; the trainer
  must use them unchanged (a specialist is always served with the prompt it was trained on).

## Round 1 tasks
1. **Measure the pilot.** `uv run modal run modal_apps/train_app.py::pilot` on ~200 examples/domain.
   Report per-domain: train seconds, gate, mask sanity (`masked_frac_first_batch`), max sequence
   length, $ spend. L4 only. Stop after the pilot if spend would exceed **$12**.
2. **Full sweep.** `::sweep` with the real data (all four adapters). Report gates per kind, the
   escalation count, and total GPU-seconds. Keep `min_containers=0`.
3. **Data-efficiency probe (HP2 subset).** For each domain, gate at {100, 400, 1600} examples
   (one adapter each, `max_train`). One table: gate vs examples per domain. This tells the team
   where more data actually buys accuracy.
4. **Registry discipline.** `merge_registry` must never publish pilot seeds by default; add a test
   that a registry entry is only current when `(adapter_name, seed, data_version)` match
   (`logic.is_done` already encodes this).
5. **Loss-mask test.** Add a pure-logic test proving `build_labels`-equivalent masking holds for the
   specialist dataset builder (the prompt tokens are masked, completion + eos are not, nothing is
   silently truncated — the `max_len` slice in `_build_dataset` must be removed or asserted).

## Definition of done
- `uv run pytest -q` passes offline (no torch import at module import time).
- Volume has `/vol/adapters/{seed}/spec-*` for the four domains plus `registry.json`.
- PR body: pilot + sweep tables (seconds, gate per domain, escalations, $), the HP2 table, and any
  recipe deviations.
- Spend cap this round: **$20**. At 80% of the cap, stop launching and report.
