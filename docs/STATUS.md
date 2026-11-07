# Status

Last updated 2026-11-07, at the import into Minverva. Update this file in the PR that changes the
picture.

## Works today

- **Pipeline end to end, no model needed.** `uv run slm run --project 0` plans with the gold plan,
  dispatches 13 tasks over 5 dependency levels to oracle specialists, and the integrator passes every
  seam check (18 files written).
- **Tests.** `uv run pytest`: 378 pass, 18 skip on Linux. `evaluation/tests/test_grading.py` needs macOS
  `sandbox-exec` and only runs on a Mac.
- **Three ways to watch it:** web workbench (`uv run slm ui`), Textual workbench (`uv run slm code`),
  terminal monitor (`cd tui && cargo run --release`). The `tui` monitor was checked against real
  `slm run` traces and real `slm.arch` result rows.
- **Evaluation harness** (`evaluation/`): private benchmark tasks, controls, sandboxed grading, Modal
  spend limit ($20.85 counted from 2026-11-01).

## Not done yet

- **No trained specialists for the web-project task.** The repo's own checklist (README) still has
  data, adapters, manager SFT and results unchecked. L4 added a free-GPU training loop
  (`slm/train/backprop.py`, `notebooks/train_free.ipynb`), but no adapter registry is in the repo.
- **No committed results.** `docs/LAYERS.md` points at `docs/ARCHITECTURE_RESULTS.md`, which was never
  committed. The code refers to recorded `slm.arch` runs (local `qwen3.5:4b` via Ollama), but none of
  their `out/arch` results are in the repo.
- **The headline comparison is open:** manager + specialists vs single generalist vs monolith on
  deliverable pass rate and latency (`PLAN.md`, H1-H3).

## Known caveats (from docs/LAYERS.md)

- Gold artifacts are templates with the entity name swapped in, so specialist training gates will look
  better than the model is.
- `VLLMLoRAClient` defaults to `max_tokens=128`; callers must pass about 1024.

## Next, in order

1. Whoever has the recorded `slm.arch` runs: commit them as `docs/results/` write-ups.
2. Train the four `spec-*` adapters and the manager; publish the registry.
3. Run `evaluation run functional-gate`, then `final-heldout`, and fill in PLAN.md's table.
