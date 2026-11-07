# Prospective reliability evaluation v1

**The 95% target was not met.** Ten previously unused briefs produced 1/10 passing first attempts and 4/10 passing candidates after at most three repairs each. All 31 generated attempts compiled. The 21 repairs improved three cases during the first round; the next two rounds added no passes.

| Round | New attempts | Cumulative full passes | Cumulative interaction verification passes |
|---|---:|---:|---:|
| 0 | 10 | 1/10 | 6/10 |
| 1 | 9 | 4/10 | 7/10 |
| 2 | 6 | 4/10 | 7/10 |
| 3 | 6 | 4/10 | 7/10 |

## Critic and test evidence

All 31 critiques passed schema and measured-evidence validation. No critique accepted a known failed audit. Required observations, references and acceptance workflows are constrained from actual browser results; these numbers measure protocol compliance, not independently learned defect detection or human grounding accuracy.

The final passing cases are forms_04, catalog_01, configuration_03 and directories_05. Each passed the complete saved audit. No human visual preference is established.

| Remaining case | Measured reason for rejection |
|---|---|
| operations_02 | Clear-search button has insufficient target size in populated-search states. |
| planning_03 | Required task-toggle target is missing; click and keyboard verification cannot complete. |
| analytics_05 | Required panel content/target verification fails; invalid ARIA attributes remain. |
| learning_02 | A tab role lacks its required tablist parent. |
| editorial_04 | Night-theme text contrast fails during the intermediate state. |
| collaboration_01 | The expected saved-note target is absent after save. |

Missing test targets are failed contract/verification results; they do not by themselves prove that a visible control is unusable. No test was weakened to turn these failures into passes. Three final revisions returned source identical to the previous attempt (planning, analytics, collaboration).

## Protocol and provenance

The [declaration](prospective-protocol-v1.json) was frozen before observing these UI generations. All declared files were unchanged at completion, and the archived runtime source matches the run manifest. These ten briefs do not overlap the original paired baseline briefs. A1 used validated design intents, pinned Qwen 4B checkpoints, and the expanded browser audit. Passing candidates stopped receiving repairs. Every rejected attempt remains available.

The expanded audit includes intermediate-state accessibility and overflow, boundary states and selected keyboard workflows. It is still a small authored frontend benchmark, not exhaustive testing, production integration verification, complete accessibility conformance or a representative sample of all user requests. The 40% result must not be mixed into the original unchanged-harness baseline comparison.

## Original paired comparison remains unchanged

The original v1 → v2 comparison improved source validity 11/20 → 20/20, builds 7/20 → 20/20, interaction verification 7/20 → 15/20, critic schema validity 0/11 → 20/20, and all original gates 5/20 → 7/20. [Detailed paired comparison](pilot-baseline-v2-comparison.md).

## Design and next dependency

NN/g and design-school guidance informed the intent contract and rubric, but the separate [visual score pilot](visual-rubric-pilot.md) failed calibration. It cannot substantiate attractiveness or supply human preference labels. [Research and implementation](../docs/design-intent-and-quality.md).

No training occurred. The [original review packet](../artifacts/original-review-pilot-v1/review.html) is independent of evaluation data and remains unreviewed. The supplied blueprint requires human verification and correction before accepting a versioned training dataset; zero training examples have been accepted.

[Screenshot gallery and passing source exports](../artifacts/prospective-review-v1/review.html) · [Machine-readable analysis](prospective-reliability-v1.json) · [Raw run summary](../artifacts/prospective-reliability-v1/summary.json).

The Modal app completed and stopped with zero tasks. Local checks: 33 tests passed; Ruff passed. Runtime manifests, controller log, exact source snapshot and artifact checksums are retained.
