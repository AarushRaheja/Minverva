# Pilot baseline v1 protocol

This run compares prompting on one untouched Architect checkpoint. It does not test fine-tuning, preference training, revision quality, or human aesthetic preference.

- Run ID: `pilot-baseline-v1`.
- Ten briefs, twenty requested generations: A0 and A1 receive the same brief and interaction tests.
- The fixed sample rotates through ten categories and five style briefs, independent of model results: operations_01, planning_02, forms_03, analytics_04, catalog_05, learning_01, configuration_02, editorial_03, directories_04, collaboration_05.
- A0 receives the basic role and shared source contract. A1 adds the design guidance in `src/frontendslm/prompts.py`.
- Architect generation: seed 42, temperature 0.2, top-p 0.9, 6,144 maximum new tokens, one attempt. No JSON repairs, code repairs or retries. Truncation and malformed manifests remain failures.
- Critic: the official untouched Qwen3-VL-4B checkpoint, greedy generation, 2,500 maximum new tokens, separately processed desktop and mobile screenshots plus measurements. No schema repair or post-hoc filling of required fields.
- Pinned model revisions and source hashes are in `run.json`; `source_snapshot.zip` preserves the exact hashed runtime sources.
- Generated code executes only in network-blocked Modal Sandboxes. Both prompt conditions use the same fixed React/TypeScript/Tailwind template, package lock, browser and tests.
- All requested attempts appear in generation/build/interaction success denominators. Missing render or critique is never counted as a pass. Critic schema rates over all requested candidates describe end-to-end coverage; calculate conditional rates over actual Critic calls separately.
- The engineering gate requires compilation, complete rendering at five widths, the specified desktop/mobile interactions, no observed overflow, no serious/critical axe violations, no browser/resource failures and nonempty content. Passing it does not establish visual excellence or complete accessibility conformance.
- Evidence reference validity checks identifiers and required evidence types. It does not validate the truth of visual observations, severity, or recommendations.
- Human visual preference, grounded critique precision/recall, confidence calibration and inter-rater agreement remain unmeasured.

The pipeline was checked on twenty reference fixtures and three deliberately broken fixtures before the comparison. One compatibility smoke example was run first; it exposed missing Torchvision and an image-processor enum transfer issue, both fixed before the baseline. It also exposed a missing `schema_version` in the Critic response; that model failure was retained, and the Critic prompt was not changed in response.

The separate smoke result is not added to the twenty-generation comparison. The evaluation prompts and all derived artifacts remain excluded from training.

## Pipeline v2 paired regression protocol

Run `pilot-baseline-v2` reuses exactly the ten v1 briefs and both prompt conditions. Model revisions, seed, token limits, L40S hardware, the sandbox image template, browser tests and engineering score remain unchanged. Each candidate gets one attempt; no failure is retried or removed from the denominator.

The generator outputs a single raw TSX component. The host supplies a fixed stylesheet rather than asking the model to emit JSON-escaped CSS. Both A0 and A1 receive the same revised output contract and repetition penalty of 1.05. Placeholder manifest planning metadata is explicitly host-supplied. Source-manifest validity therefore has a different protocol; build and browser outcomes use the unchanged tests.

The Critic uses XGrammar 0.2.8 for schema-constrained decoding, with the same 2,500-token ceiling. It sees a measured-check ledger, including after-interaction scans. Independent validation rejects acceptance on measured failures or missing evidence and requires cited issues covering each failed check group. The model's raw response and the independent effective verdict are both retained. No missing fields are inserted after decoding.

Before the rerun, four saved v1 cases were replayed: a passing page, a build failure and the two previously missed contrast failures. All four raw replies matched the schema; both contrast failures produced revise verdicts and measured citations. The validator initially rejected a contrast issue categorized as color; allowing color for exclusively color-contrast failures corrected that taxonomy mismatch without changing the model output. Raw and revalidation records remain separate.

This is a regression test on prompts used to diagnose the original failures, not a fresh holdout or evidence of learned improvement. Additional reliability work must report bounded revision results separately from first attempts and must use unseen briefs before claiming generalization. Automated engineering checks do not establish universal failure freedom, aesthetic quality or full WCAG conformance.
