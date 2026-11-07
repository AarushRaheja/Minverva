# Baseline comparison: pilot-baseline-v1 → pilot-baseline-v2

Same ten briefs, A0/A1 conditions, pinned model revisions, seed 42, token limits, L40S and browser harness. One generation per candidate; no repair retries or training.

| Metric | Before | After |
|---|---:|---:|
| source valid | 11/20 | 20/20 |
| build pass | 7/20 | 20/20 |
| interaction pass | 7/20 | 15/20 |
| no overflow | 7/20 | 20/20 |
| no serious a11y | 5/20 | 8/20 |
| release eligible | 5/20 | 7/20 |
| Critic schema validity (attempted only) | 0/11 | 20/20 |
| Truncated generations | 7 | 0 |
| Raw critic false acceptances on measured failures | 2 | 0 |

## Changes and interpretation

- raw component output and host-supplied CSS
- shared code contract
- Architect repetition_penalty 1.0 → 1.05
- Critic XGrammar schema-constrained decoding
- Critic measured-check ledger including after-interaction evidence
- independent fail-closed measurement/reference validation

Same small evaluation set reused to assess engineering fixes; not a fresh holdout, model training gain, or human quality assessment.

Source-manifest validity is protocol-specific: v1 required model-generated JSON and CSS; v2 validates a generated component assembled with fixed CSS. Build and browser pass rates are directly comparable on the unchanged harness.

Critic schema correctness is now constrained at decoding, not learned. Raw model issues/verdicts remain separate from the independent gate. Measurement validation checks coverage and references; it does not prove every sentence or visual claim true.

## A0 and A1

| Condition | Builds before → after | All gates before → after |
|---|---|---|
| A0 | 4/10 → 10/10 | 4/10 → 3/10 |
| A1 | 3/10 → 10/10 | 1/10 → 4/10 |

## Paired outcomes

| Candidate | Build before → after | All gates before → after |
|---|---|---|
| A0/operations_01 | fail → pass | fail → fail |
| A0/planning_02 | fail → pass | fail → pass |
| A0/forms_03 | fail → pass | fail → fail |
| A0/analytics_04 | fail → pass | fail → fail |
| A0/catalog_05 | fail → pass | fail → fail |
| A0/learning_01 | pass → pass | pass → fail |
| A0/configuration_02 | pass → pass | pass → fail |
| A0/editorial_03 | fail → pass | fail → pass |
| A0/directories_04 | pass → pass | pass → pass |
| A0/collaboration_05 | pass → pass | pass → fail |
| A1/operations_01 | pass → pass | pass → fail |
| A1/planning_02 | fail → pass | fail → pass |
| A1/forms_03 | fail → pass | fail → pass |
| A1/analytics_04 | fail → pass | fail → fail |
| A1/catalog_05 | pass → pass | fail → fail |
| A1/learning_01 | fail → pass | fail → fail |
| A1/configuration_02 | fail → pass | fail → fail |
| A1/editorial_03 | fail → pass | fail → pass |
| A1/directories_04 | fail → pass | fail → pass |
| A1/collaboration_05 | pass → pass | fail → fail |

## Inference usage

Architect output tokens: 59,522 → 22,030.

Measured Architect generation time: 33.9 → 12.6 minutes; Critic: 0.8 → 4.2 minutes.

These timings exclude startup, image building, model loading and idle time. They are not billed GPU duration or dollar costs.

See comparison.json for every measured-failure verdict, and review.html for screenshots and source exports. Human visual preference and critique grounding remain unmeasured.
