# Design intent and visual quality

The system must translate what a user means into visible decisions, while keeping working behavior as a hard requirement. The current preference is **“Clean product UI, like Linear or Stripe.”** That is a default direction; more specific briefs can override it.

## Research translated into implementation

| Source | Project interpretation |
|---|---|
| [NN/g visual design study guide](https://www.nngroup.com/articles/visual-design-in-ux-study-guide/) and [visual design principles](https://www.nngroup.com/articles/principles-visual-design/) | Review hierarchy, scale, grouping, contrast, and balance, alongside accessibility and interaction results. |
| [RISD visual communication](https://artsandlanguage.risd.edu/visual-communication) | Make typography, grids, hierarchy, color, audience, and purpose explicit design decisions. |
| [Stanford d.school Design Thinking Bootleg](https://dschool.stanford.edu/tools/design-thinking-bootleg) | Start with the user's goal and context; make assumptions visible and test prototypes instead of inventing user needs. |
| [CMU HCII experience design](https://hcii.cmu.edu/research-areas/experience-design) | Evaluate the task journey and state changes as well as the initial screen. |
| [Linear's 2026 design refresh](https://linear.app/now/behind-the-latest-design-refresh) and [Stripe Apps design guidance](https://docs.stripe.com/stripe-apps/design) | Use quiet navigation, coherent controls, deliberate density, restrained emphasis, and readable text. These references inspire principles, not copied product screens. |
| [NN/g testing visual design](https://www.nngroup.com/articles/testing-visual-design/) and [desirability testing](https://www.nngroup.com/articles/microsoft-desirability-toolkit/) | Separate observed task behavior, model-estimated visual quality, and actual user preference. Retain the user's words and compare intended versus perceived descriptors. |

These are project interpretations, not endorsements or a validated beauty formula. The sources inform prompts and evaluation criteria; their pages, images, and exercises are not training data.

## Intent contract

`design/contracts.py` records the goal, audience, primary action, hierarchy, UX priorities, and free-text descriptor interpretations. Every interpretation includes its source quote, whether it is explicit/inferred/default, whether the user prefers or avoids it, its meaning in context, and concrete decisions. The compact layout/color/type options are implementation defaults; the original wording and free-text decisions remain authoritative.

Examples of intended behavior, tested with original probes:

- **Calm but dense:** compact aligned rows, quiet separators, restrained status color; avoid oversized cards. “Calm” does not imply empty.
- **Warm and editorial:** comfortable reading measure, deliberate typography, warm neutral surfaces; avoid adding a dashboard shell.
- **Playful but professional:** controlled color and friendly copy with readable controls and predictable form feedback.
- **Premium and light:** spacious composition and material detail; do not automatically infer black and gold.
- **An undefined private term:** preserve the exact term and ask what it means. Do not manufacture confidence.

The model cannot establish that its interpretation matches a real user's intent without user review. Provenance validation checks quotes and missing clarification, not the truth of every semantic interpretation.

## Separate quality signals

1. **Measured functionality:** TypeScript/build, browser workflows, keyboard actions, boundary states, initial/intermediate/final accessibility scans, overflow, and runtime errors. Any failed required measurement blocks acceptance.
2. **Visual quality proxy:** A separate screenshot review scores seven dimensions from 0–5 with visible evidence. Its weighted 0–100 value is an uncalibrated model estimate. It must not be described as human beauty accuracy or override failed functionality.
3. **Human preference:** One user has rated one original assistant-authored reference **4/5**, describing it as **Clean, Functional, Minimal, Plain**, with a clear primary action and no manual interaction testing. [Review and scope](../reports/human-review-v1.md). Generated 4B outputs still lack human ratings. A broader evaluation should show two or three anonymized variants in randomized order, collect independent task completion before aesthetic questions, ask for spontaneous descriptors, and record preference and descriptor alignment.

All inference runs retain raw responses, exact prompts, model revisions, source/image hashes, schema validation, and failed attempts. The original paired baseline remains frozen; design-intent and repair experiments use separate run IDs.

## Observed limits and human review

The [visual-rubric pilot](../reports/visual-rubric-pilot.md) failed calibration: the judge awarded perfect scores to several weak compositions and returned an invalid assessment for another candidate. Its numeric scores must not select examples, approve releases, or serve as preference-training labels.

The original [notification-preferences review packet](../artifacts/original-review-pilot-v1/review.html) collects spontaneous descriptors before showing the intended direction. It keeps screenshot impressions separate from personally tested interactions. Its working candidate passes measured checks, and three deliberate defects fail their intended groups, but all four candidates remain excluded from training pending actual human verification. The source family is independent of the evaluation briefs and is assistant-authored, not a 4B-model result.

The first visual submission is recorded in `artifacts/human-reviews` without altering that historical packet. Human rating labels are excluded from the visual judge's prompt. Candidate-specific descriptors can inform later intent interpretation, but are not silently promoted to universal style requirements or measured behavior claims.

[Public data discovery](public-data-review.md) records why the external resources checked so far do not yet provide a verified replacement for those missing human labels.

## Running

Use `scripts/run_design_evaluation.py --mode intent --input design/intent-probes.json --run-id <new-id>` for the intent probes. A visual job file provides `blind_id`, `brief`, optional `intent`, and `images` mapping view names to verified relative PNG paths in the Modal results volume. Use `--mode visual` for that file. Both phases run the pinned models on Modal L40S compute.
