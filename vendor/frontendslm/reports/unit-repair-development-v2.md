# Source-unit repair diagnostic v2

The revised edit format again finished at **3/5 accepted**: two passing controls and **one repaired failure out of three**. It repaired the search case in one structured-patch round, compared with two rounds and a full-component fallback in v1. The total pass count did not improve, and the expansion gate remains unmet.

| Measure | Unit diagnostic v1 | Whole-element diagnostic v2 |
|---|---:|---:|
| Initial acceptance | 2/5 | 2/5 |
| Final acceptance | 3/5 | 3/5 |
| Known failures repaired | 1/3 | 1/3 |
| Revision attempts | 6 | 5 |
| Accepted direct unit patches | 0 | 1 |
| Assembled valid-source manifests | 5/6 | 1/5 |
| Executed revision builds passing | 2/5 | 1/1 |
| Critic responses valid against schema and measurements | 10/10 | 6/6 |
| Failed audits with effective accept verdict | 0 | 0 |

The different build denominators matter: four v2 attempts were rejected as no-ops before execution. They remain failed attempts, not missing observations to drop from the result. Neither version establishes general repair accuracy. The prior greedy whole-component experiment repaired 0/3 of these same failures after two rounds; all are repeatedly used development cases.

## What changed and what failed

The parser now captures small controls, text elements and test-target containers as complete JSX elements. The model receives explicit scope examples. A trusted local parser rejects malformed assembled TSX without executing it, preserves the rejected source, and recovers browser evidence only for the exact previous source version. Builds and browser interactions still run exclusively in isolated Modal sandboxes.

- **Search:** one patch fixed the measured footer contrast and clear-button target size. It compiled and passed the unchanged full interaction and intermediate-state audit. Unedited source bytes were preserved by the patch applicator.
- **Quantity:** both attempts repeated unchanged code. The reasoning incorrectly defended the existing limit even though the complete workflow required another increment. No repair was accepted or executed.
- **Accordion:** both attempts included an unchanged panel unit alongside a footer edit. The entire patch was rejected. The required visibility behavior remained unresolved.
- **Controls:** planning and forms passed initially and remained unchanged.

Both second-round failed candidates received the original failed interaction measurements; the accordion also retained its accessibility failures. Missing evidence after rejection did not erase those requirements. The six actual Critic responses were valid; rejected generations did not receive additional screenshot critiques. Enforced evidence reporting is not independent learned defect detection, and model recommendations remain unverified hypotheses.

The exact initial sources, full cases/tests, pinned models, seed and browser audit match v1. Edit boundaries, prompt wording and host syntax validation changed together; this experiment does not isolate any single factor. Its checksummed source snapshot, runtime manifests, raw output, failed attempts and measurements are retained. The app completed normally and stopped with zero tasks.

## Follow-up and scope

The current working controller (7.2) skips a GPU Critic launch when a round has no measurement files. This avoids the empty final phase observed here. No-op feedback now identifies the exact offending source unit. These two follow-ups passed local checks but were **not part of this Modal experiment**, whose frozen controller is 7.1. Review links also omit unavailable evidence for rejected generations. All 45 local tests and Ruff pass.

Do not expand to unused briefs based on this result. The next development work must address interpretation of required state transitions and unchanged-code retries; syntax correctness alone is insufficient. The separate prospective result remains **4/10**, and no high-accuracy or human-beauty target is established. No training was performed.

The user's [4/5 visual review](human-review-v1.md), with Clean, Functional, Minimal and Plain preserved, applies to the original notification-preferences reference. It does not rate these 4B outputs or manually verify their behavior.

[Review packet](../artifacts/unit-repair-review-v2/review.html) · [Machine-readable report](unit-repair-development-v2.json) · [Frozen protocol](unit-repair-development-protocol-v2.json) · [Prior diagnostic](unit-repair-development-v1.md).
