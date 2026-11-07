# Pilot baseline v1 — executed November 7, 2026

The baseline ran on Modal in workspace `aarushagg12`, environment `main`, using an NVIDIA L40S. It produced 20 first-attempt Architect responses for 10 original briefs, followed by compilation/rendering for the 11 accepted source manifests and 11 Critic responses. No fine-tuning or source repairs were performed.

[Modal run and logs](https://modal.com/apps/aarushagg12/main/ap-QhEWt6VS34egsagTpxkotS)

Local visual comparison: `artifacts/pilot-baseline-v1/review.html`. Raw results, source exports, screenshots, runtime manifests, source snapshot and checksums are in the same directory. The experiment is also stored in the Modal volume `frontendslm-experiments` under `/pilot-baseline-v1`.

## Measured results

A0 uses a basic instruction and the shared output contract. A1 adds detailed design guidance. Both receive the same specifications, tests, seed, checkpoint, token allowance and tools.

| Outcome | A0 | A1 |
|---|---:|---:|
| Requested attempts | 10 | 10 |
| Accepted source manifests | 5/10 | 6/10 |
| Compiled and rendered at all five widths | 4/10 | 3/10 |
| Passed the specified desktop/mobile interactions | 4/10 | 3/10 |
| Passed all measured engineering gates | 4/10 | 1/10 |
| Critic schema validity, among actual Critic calls | 0/5 | 0/6 |

Seven interfaces compiled. All seven passed their specified interaction assertions, and none had measured horizontal overflow. Two had serious color-contrast violations, leaving five passing all measured engineering gates. These gates do not establish visual quality, full accessibility conformance or production readiness.

## Failure analysis

1. **Generation length and repetition:** seven responses reached the 6,144-token cap (five A0, two A1). Their manifests could not be parsed. Repeated CSS utility definitions are visible in the raw failed responses; the first robot-fleet response repeatedly emitted the same focus-ring rules.
2. **Output-boundary violations:** two additional A1 responses returned disallowed source manifests, including a generated `src/main.tsx`. The controller rejected them instead of allowing the model to replace the fixed entry point.
3. **Compilation:** three accepted manifests failed because generated Tailwind `@apply` rules introduced circular dependencies: A0/forms_03, A1/forms_03 and A1/configuration_02. A1/editorial_03 failed TypeScript/JSX parsing. These are model-output failures; the same fixed template passed all reference fixtures.
4. **Accessibility:** A1/catalog_05 and A1/collaboration_05 had serious `color-contrast` findings at every initial viewport. Both still passed the limited interaction tests.
5. **Critic contract:** every Critic response omitted the required `schema_version`. Other fields were parseable, but no missing field was silently filled in and no response was accepted as schema-valid.
6. **Critic evidence use:** the raw Critic responses accepted both contrast-failing candidates with empty issue lists despite receiving the measured violations. This is direct evidence of missed tool-reported defects on these two cases. It is not a general precision/recall estimate.

Detailed prompting reduced token-limit failures in this sample, but did not improve build success or the combined engineering gate. The experiment has only ten paired briefs and one fixed seed; it does not establish a statistically reliable overall ranking of prompting strategies or model capability.

## Execution measurements

- Architect: 59,522 generated tokens; 2,035.43 seconds of measured generation time; approximately 29 tokens/second median within each condition; maximum allocated GPU memory 8.49GiB.
- Critic: 1,328 generated tokens; 50.09 seconds of measured generation time; maximum allocated GPU memory 9.21GiB.
- These durations exclude model loading, image construction, cache downloads, CPU rendering and idle time. They are inference measurements, not training-cost estimates or the Modal invoice.
- Harness validation: 20 original reference fixtures, 100 initial viewport checks, 40 interaction checks, and three correctly detected intentional defects (overflow, broken filter, compilation error).
- Local validation: 16 contract tests passed; lint and Python compilation passed. A CI workflow is included but has not been run on GitHub from this uncommitted working tree.

## Next gate

The immediate bottlenecks are reliable bounded source output, valid Tailwind/JSX, and a Critic that obeys its contract and uses measured evidence. Future experiments can test constrained output and scoped file generation as separately versioned conditions. Do not change this frozen baseline or count repaired outputs as first-attempt successes.

Human visual preference, critique grounding precision/recall, confidence calibration and independent severity labels remain unmeasured. The `human-review.jsonl` queue is intentionally unlabeled. Training remains deferred until a separate licensed and human-reviewed dataset exists; the 50 benchmark prompts and all derived outputs must remain evaluation-only.
