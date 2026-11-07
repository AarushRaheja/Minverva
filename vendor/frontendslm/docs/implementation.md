# Implementation boundaries and next gates

The paired baseline sprint is complete. Subsequent experiments implement design-intent interpretation, expanded functional audits, and bounded repairs. They do not establish production reliability or human visual preference.

## Implemented

- Python package, dependency locks, CI, typed specification/source/critique schemas and rejection tests.
- Fifty original evaluation prompts across ten categories, frozen before inference.
- React/TypeScript/Tailwind template with a fixed dependency allowlist.
- Modal CPU sandbox renderer with five viewports, initial/final-state axe scans, interaction assertions, errors, DOM/accessibility snapshots, and keyboard traces.
- Twenty reference fixture configurations covering ten interaction patterns and two visual themes. They validate the harness; they are not twenty independent design families or accepted training examples.
- Official Qwen checkpoint revision locks and untouched Architect/Critic adapters.
- A0/A1 comparison with equal specifications, tools, seeds, token limits and evaluation tests.
- Persistent artifacts, raw outputs, resource measurements, source hashes, denominator-aware summary and report.
- Expanded browser workflows with accessibility and overflow measurements during intermediate states, plus controlled fault and boundary fixtures.
- A bounded revision controller (at most three repair rounds) that retains failed attempts and rejects candidates with failed or missing measurements.
- Optional statically localized source-unit edits with exact UTF-8 ranges, source checksums, syntax rejection and recovery of matching measured evidence. Two diagnostic runs repaired only one of three known failures; reliable repair remains unestablished.
- Schema-constrained Critic output using actual measured failures and complete required workflows. This is enforced reporting, not independently measured defect-detection accuracy.
- Design-intent interpretation with traceable descriptors, explicit assumptions, and a clarification gate for explicitly undefined private terms.
- A separate visual-rubric experiment, which failed calibration, and an original human-review pilot with three verified controlled defects. One submitted 4/5 visual review is now bound to the original working source; it is not an accepted training example or a rating of the 4B model's output.

## Not yet established

- The natural-language requirements compiler: pilot specifications are authored and validated directly. Missing backend/auth/payment requirements remain explicit.
- Accepted training datasets with provenance, permissions, human quality labels, deduplication and separate project/family splits.
- Human-labeled critique benchmark, blind pairwise preference collection, inter-rater agreement and calibrated confidence.
- Independent evidence that the Critic is reliable enough to drive revisions.
- QLoRA/LoRA SFT, DPO, joint revision training, model adapters or trained checkpoints.
- Reliable general-purpose repair, production inference services and interactive studio.

## Promotion gates

1. Inspect the completed baseline, including failed generations. A failed build remains part of the first-attempt score. Record infrastructure fixes separately from changes in model behavior.
2. Independently label critique issues and abstentions. Reference existence alone cannot validate visual claims. Test-grounded interaction assertions and human-grounded visual judgments need separate precision/recall metrics.
3. Curate 300–500 independent Architect examples and 500–1,000 Critic examples with appropriate source permissions. Never reuse pilot evaluation prompts or their outputs as training data.
4. Benchmark 25–50 representative optimizer steps on Modal before forecasting training cost. Pin the GPU training dependency environment and save resumable optimizer, scheduler, RNG and adapter state.
5. Train Architect and Critic separately; retain untouched baselines and SFT-only adapters. Advance only on measured gains or a documented negative result.
6. Enable scoped revisions with an allowlist, at most three iterations, regression gates and independent review. Keep the best validated candidate.

## Sources checked during implementation

- [Modal Sandboxes](https://modal.com/docs/guide/sandboxes)
- [Sandbox network isolation](https://modal.com/docs/guide/sandbox-networking)
- [Sandbox filesystem API](https://modal.com/docs/guide/sandbox-files)
- [Modal pricing](https://modal.com/pricing)
- [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
- [Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct)

The two model cards list Apache-2.0 licensing. That does not establish permissions for any third-party UI dataset; none is ingested by this pilot.
