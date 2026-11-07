# Frontend reliability acceptance protocol

The active objective is to reliably generate fully functional frontends, supported by measured data. This means implementing the stated local frontend requirements; unspecified backends, authentication and payment integrations remain outside the benchmark.

The paired v1/v2 baseline completed using identical browser tests. Additional testing is a separate functional audit and must not retroactively change those scores.

Acceptance targets for the tested domain:

- All requested outputs compile and complete the required frontend workflows in a bounded generation/revision pipeline. Report first attempts and repaired results separately; retain every unsuccessful attempt.
- At least 95% of candidates pass every engineering gate on an evaluation wave whose prompts have not previously been used for generation or repair diagnosis, with no falsely accepted known failures. Remaining failures block a claim of failure-free output.
- Every delivered candidate has a valid critic response, complete measured evidence and no failed engineering gate. Unresolved cases must be explicitly rejected, never silently treated as successful.
- Critic replay covers known build, interaction, accessibility, overflow and incomplete-evidence conditions. Critic schema success and measured failure coverage are not human grounding precision/recall.

The functional audit will exercise requirements under-tested in the initial pilot: case-insensitive and empty-result search; round-trip state changes; cart lower bounds; accordion aria-expanded and keyboard activation; actual palette changes and intermediate-state accessibility; directory initial order and cleared filters; dialog Escape, focus restoration and keyboard behavior. It will scan relevant intermediate interaction states so opening a dialog or switching to Night cannot hide violations by returning to the initial state before scanning.

The first ten paired briefs are a regression set. The next ten briefs in the frozen selection order were evaluated under a protocol fixed before their UI generations. This is still a small synthetic workflow benchmark; report its limits and do not claim universal frontend correctness or independently measured visual design quality.

No benchmark prompt, generated source, test evidence or critique may enter model training. Repairs consume the measured evidence at inference time only. Bounded retries must not be described as first-attempt success.

## Measured issue enforcement and audit corrections

The v2 paired baseline finished with 20/20 builds, 20/20 schema-valid and measurement-valid critiques, and 7/20 candidates passing the original engineering gate. Its source snapshot and 292-file artifact manifest are frozen separately. The extended audit initially passed 5/20 candidates, revealing intermediate-state failures hidden by final-state-only scans.

The extended audit now accepts a disabled quantity decrement at the minimum, while still checking that decrement works above the minimum. A valid disabled-boundary fixture passes; an always-disabled decrement fixture fails. This correction does not alter either paired baseline's original scores. Measurement-instrumentation errors are recorded as harness errors rather than incorrectly labeling an application interaction as broken.

A four-case Critic regression covered missing Escape support, a label-only theme toggle, intermediate low contrast and intermediate overflow. The prompt-only measured ledger covered three of four with actionable issues; the overflow response correctly said revise and described the failure in its summary but omitted an issue. The failed observation remains in `critic-state-regression-v3`.

The v3 decoder now derives a required issue prefix from measured failed groups. It constrains each required issue's ID, category, severity and permitted evidence references, and prohibits accept on measured failures. The model supplies explanations and repair recommendations and may add visual issues. This is tool-enforced reporting, not independent model detection accuracy. Raw output, exact per-case decoding schema, original measurements and post-decoding validation are retained. Missing or inconsistent evidence continues to fail closed.

Repairs are limited to two rounds by default (the CLI hard limit is three), keep every prior attempt, and re-run the complete functional audit and critic. The pipeline never silently publishes a rejected candidate. The prospective evaluation used three rounds under its separately frozen declaration.

## Repair and critic diagnostics after v3

The v3 full-file repair experiment was stopped after its first revision failed to make useful progress. Its artifacts remain intact. A focused v4 exact-text patch experiment also failed to repair its three selected failures; it retained the two passing candidates. Invalid edits were rejected, not approximately matched or silently applied.

That diagnostic also exposed why measured evidence must include the **complete required test plan**, not only steps that executed before a failure. A disabled button on the second increment was misinterpreted as a first-increment failure, and the critic recommended preserving an incorrect maximum. The subsequent protocol includes all expected steps and treats the raw measured ledger as authoritative. Critic repair advice remains model-generated and is not a validated fact.

The v5 repair protocol requests bounded edits by original source line range. Overlapping, out-of-bounds, and no-op edits fail validation; every applied change must compile and pass the full browser audit. Passing tool references cannot support defect claims, and a revise verdict needs an actionable issue. Axe manual-review items are labeled unconfirmed and cannot be promoted to measured violations.

Visual and intent evaluation is a separate signal, described in `design-intent-and-quality.md`. Visual scores cannot offset a failed functional measurement. No current result establishes human beauty preference.

## Completed v6 prospective result

The conversational component-repair protocol supplies measured failures and complete test plans while retaining the previous component in context. The v6 Critic schema additionally constrains required observations and acceptance workflows to text derived from measured results, preventing those fields from inventing limits or changing the expected behavior. Recommendations are still model output and require a successful rerun.

The frozen ten-brief evaluation passed 1/10 initially and 4/10 after 21 repair attempts. All 31 generations compiled and all 31 critiques passed schema and measured-evidence validation. No known failed audit was accepted. Repair rounds two and three added no passes, and three last-round revisions returned identical source. The 95% target was not met. See [the complete report](../reports/prospective-reliability-v1.md), including failures, provenance and limits.

The original review pilot supplies candidate material for human verification; it does not constitute an accepted training dataset. No fine-tuning or human preference calibration has occurred.

## Repair sampling diagnostic

The three previously studied repair failures were also evaluated using Qwen's recommended sampling parameters, with exact matching repair prompt hashes and initial sources. Both greedy and sampled decoding passed 0/3 after one repair. This did not justify changing the default or consuming another prospective wave. [Comparison and remaining failures](../reports/repair-sampling-v1.md).
