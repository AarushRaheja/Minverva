# FrontEndSLM

Reproducible experiments for a 4B UI Architect and a 4B multimodal Design Critic, running on Modal. The paired baseline is complete. Experimental bounded revisions, design-intent interpretation and visual evaluation are also implemented. No fine-tuning has been performed; high reliability and human visual preference remain unproven.

The frozen paired comparison improved builds from **7/20 to 20/20**, Critic schema validity from **0/11 to 20/20**, and all original engineering gates from **5/20 to 7/20**. See [the comparison](reports/pilot-baseline-v2-comparison.md). Later expanded audits and repairs use separate protocols and must not be mixed into those paired scores.

The completed [prospective evaluation](reports/prospective-reliability-v1.md) on ten unused briefs passed **1/10 initially and 4/10 after up to three repairs**. All 31 attempts compiled and had valid measured critiques; none accepted a known failed audit. The blueprint's 95% target concerns builds, not this combined audit measure; overall reliability remains insufficient. The final two repair rounds added no passes. [Review the outputs](artifacts/prospective-review-v1/review.html).

The alternative [4B Thinking repair comparison](reports/thinking-repair-development-v1.md) fixed all three reused measured failures in one round and retained both controls: **5/5 measured acceptance**, versus 0/3 first-round repairs with the Instruct component controls. Checkpoint, decoding and token budget changed together. One quantity UI still has stale helper text; its source export is withheld in the [review packet](artifacts/thinking-repair-review-v1/review.html). Two [Critic evidence replays](reports/critic-content-consistency-v2.md) missed that contradiction despite valid schemas and complete measured evidence. These are development results, not independent accuracy or human beauty scores.

The [Thinking Critic comparison](reports/critic-thinking-development-v1.md) also failed its semantic gate: 4/6 outputs passed contract and measured-evidence validation, versus 6/6 for the Instruct control. It recommended an incompatible quantity cap and misread the form's required post-submission message as an initial-state requirement. It is not promoted. Separately, [audit 2.1](reports/exact-numeric-audit-v1.md) closes a verified false pass by checking quantity and cart-count text exactly and saving observed text. Historical 2.0 scores remain unchanged.

## Run

Prerequisites: Python 3.12, Node 22.14.0, uv, and a configured Modal workspace. No Hugging Face token is required for the public candidate checkpoints. Local Node tooling parses source for repair locations; generated applications still execute only in isolated Modal sandboxes.

```sh
uv sync --frozen
npm ci --prefix sandbox --ignore-scripts --no-audit --no-fund
uv run pytest
uv run modal run modal_app.py --mode smoke --count 1 --run-id harness-smoke
uv run modal run modal_app.py --mode references --count 20 --run-id harness-reference-20
uv run modal run modal_app.py --mode baseline --count 10 --baselines A0,A1 --run-id pilot-20
```

Use a unique run ID. `baseline` performs model caching, Architect inference, sandbox rendering, Critic inference, and reporting. `--mode render` and `--mode critic` resume those phases of an existing local run. The `cache` mode downloads the pinned checkpoints without running GPU inference.

New runs use the current pipeline and record its version. To reproduce a historical v2 run, use that run's archived source snapshot; the current code is not the original v2 protocol.

If an Architect phase stops at its time limit, wait for that job to stop, then run `uv run python -m scripts.resume_architect <run-id>`. It verifies the original source hashes and skips every saved generation, including failed ones. Continue with the `render` and `critic` modes. Do not run a recovery process concurrently with the original job.

The command above selects ten briefs across all ten categories and five styles, producing 20 interfaces (A0 and A1 for each brief). Case selection follows a fixed rotation independent of model outcomes. Increasing `--count` to 20 covers each category twice and produces 40 interfaces. A0 has a simple instruction and the shared output contract; A1 adds detailed design guidance. Neither uses trained adapters or repair retries. A smoke experiment can use `--count 1 --baselines A1` before the full batch.

## Compute and isolation

- Architect and Critic run sequentially on one NVIDIA L40S (48GB) per phase, using BF16 and SDPA. Each phase has a 60-minute function timeout and a 55-minute loop budget. No public endpoint or scheduled job is deployed.
- Model files persist in `frontendslm-model-cache`. Experiment files persist in `frontendslm-experiments`. Functions scale down after two idle seconds; no warm GPU minimum is set.
- Pipeline v2 generates only `src/App.tsx`; a trusted fixed stylesheet supplies Tailwind directives and base focus/reduced-motion rules. Build scripts, dependencies, configuration, and the test harness are fixed. The assembled source manifest marks generated versus supplied files.
- Each interface runs in a fresh Modal Sandbox with `block_network=True`, no secrets, no volume mounts, no public ports, a 300-second lifetime, 2 CPUs, and 4GiB RAM. Render concurrency defaults to 2, capped at 4.
- Dependency installation happens during trusted image construction. No generated application is executed on the developer machine.

These are resource/time bounds, not a dollar-level billing cap. Actual charges include image builds, startup, CPU, memory, GPU time and storage. Check Modal billing before increasing the case count or rerunning batches.

## Outputs

Local results live in `artifacts/<run-id>/` (gitignored):

```text
run.json                     # model, benchmark, source hashes and configuration
download.json                # pinned model cache paths
A0|A1/<case>/generation.json # prompt, raw model response, manifest, timing, errors
A0|A1/<case>/source/         # generated TypeScript and host-supplied CSS
A0|A1/<case>/render/         # evidence, screenshots and runner log
A0|A1/<case>/critique.json   # raw and parsed critique, reference validation
summary.json                # machine-readable measured outcomes
report.md                   # baseline results and limitations
```

GPU runtime manifests, including package versions, model configurations, and chat templates, are also stored in the experiment volume as `architect_runtime.json` and `critic_runtime.json`. Each generated case is committed to the volume immediately, preserving progress if a batch is interrupted.

Screenshots use 1440×900, 768×1024, 390×844, 320×800 and 1920×1080 viewports. The harness records build errors, exceptions, missing resources, overflow, accessibility snapshots, keyboard focus traces, axe violations, and state-changing interactions on desktop and mobile. It also saves final interaction-state screenshots and accessibility scans.

## Reproducibility and research boundaries

`configs/models.lock.json` pins the official Qwen repositories to immutable commits. `uv.lock` pins local dependencies and `sandbox/package-lock.json` pins browser/build dependencies. GPU runtime dependencies have explicit top-level versions and their complete installed package list is recorded per experiment; the remote dependency environment is not yet locked transitively. Source checksums distinguish dirty working trees from committed versions.

`benchmarks/pilot_v1.jsonl` contains 50 original, evaluation-only cases. Its SHA-256 is checked before every run. Cases and derived outputs must never enter training. This pilot covers small single-page applications with ten workflow patterns; it is not the final 300-case benchmark and is not independently human-reviewed.

All requested cases remain in metric denominators. Infrastructure errors are reported separately and never treated as passing outputs. Critique schema validity and evidence-reference validity do **not** establish factual grounding. Confidence is an uncalibrated model self-estimate. Human preference, critique precision/recall and calibration stay unmeasured until independently labeled.

Pipeline v2 uses XGrammar 0.2.8 to constrain Critic decoding to the published Critique schema. A measured-check ledger includes initial and post-interaction accessibility/overflow, exact interaction results, build logs, runtime failures and missing evidence. Independent validation checks failed-group coverage, citations and verdict consistency. `effective_verdict` fails closed without overwriting the raw model response. No automatic repair is counted in the first-attempt baseline.

Run `uv run python scripts/check_critic_regressions.py` to replay four saved v1 cases. After a paired rerun, `uv run python scripts/compare_runs.py pilot-baseline-v1 pilot-baseline-v2` checks benchmark/model/harness invariants and writes the comparison into the new run. The comparison is an engineering regression evaluation on reused prompts, not a fresh holdout or a claim of learned model improvement.

See [the implementation plan](docs/implementation.md) for the next research gates and [the supplied blueprint](docs/blueprint.txt) for the original scope.

## Design intent and experimental revisions

The [design research and intent contract](docs/design-intent-and-quality.md) translates NN/g, RISD, Stanford d.school, CMU HCII, Linear and Stripe guidance into explicit design decisions and a review rubric. The user's general preference is recorded in `design/preferences.json`. Brief-specific descriptors and avoided qualities remain authoritative; quote provenance, assumptions and unresolved language are retained. Explicitly undefined private descriptors block generation and request clarification.

```sh
uv run python scripts/run_design_evaluation.py --mode intent --input design/intent-probes.json --run-id intent-example
uv run python scripts/run_reliability.py --source-run pilot-baseline-v2 --run-id repair-example --max-revisions 2
uv run python scripts/run_reliability.py --offset 10 --count 10 --baselines A1 --design-run YOUR_INTENT_RUN --run-id new-evaluation --max-revisions 3
```

Use a new run ID for each changed protocol. `run_reliability.py` saves every round and uses the expanded audit, including intermediate states. A complete required test plan accompanies measured results so failures before later assertions cannot erase the intended behavior. Required measured observations and acceptance workflows are supplied by the tools; model recommendations remain untrusted until rerun. Passing tests cannot support a claim of broken interaction; they can support a content-consistency finding when paired with screenshot evidence of contradictory instructions. Manual-review accessibility items are not confirmed violations. Readable initial screen text and executed assertions include explicit measurement limits; substring assertions do not establish exact numeric equality.

Text-patch, line-patch, conversational repair, and composition-example diagnostics are retained, including unsuccessful attempts. The current experimental default uses conversational component revisions; none of these experiments establishes reliable general-purpose repair.

The optional `--repair-strategy units` uses a trusted TypeScript parser to locate exact source units, applies bounded edits, and rejects malformed TSX before browser execution. Rejected edits retain the original source measurements. The [whole-element repair comparison](reports/unit-repair-development-v2.md) repaired one of three reused failures and retained two passing controls: 3/5 overall, unchanged from the earlier unit diagnostic. It is not promoted to the default. The current controller also skips Critic initialization for rounds with no measurements; that follow-up has local validation only.

The optional `--architect-profile thinking --repair-strategy component` uses the separately pinned Thinking checkpoint, its recommended sampling and a 16,384-token cap. Add `--prepare-models` when caching that checkpoint for the first time. The default Architect profile is unchanged. `scripts/check_content_consistency.py --run-id UNIQUE_ID` replays six frozen evidence sets; `--explicit-content-review` enables the experimental per-workflow comparison schema. Neither replay improved semantic detection in the recorded runs. All experiments retain exact source snapshots for historical reproduction.

The same replay script supports `--critic-profile thinking --prepare-models` for the experimental Thinking Critic. It activates schema constraints after the tokenizer's reasoning boundary and preserves both reasoning and final output. This option is not the default Critic or a demonstrated reliability improvement. Use `scripts/check_exact_numeric_audit.py --run-id UNIQUE_ID` to reproduce the isolated numeric-assertion mutation check.

The separate [visual-rubric pilot](reports/visual-rubric-pilot.md) failed calibration and is **not an acceptance gate**. A 0–100 model score is not human beauty accuracy. [Intent development observations](reports/design-intent-development.md) document both improvements and semantic failures. Human-reviewed training examples must be separate from all benchmark prompts and derived outputs.

An original [human-review packet](artifacts/original-review-pilot-v1/review.html) and [portable ZIP](artifacts/original-review-pilot-v1.zip) are ready. The working example and three controlled defects are assistant-authored and independent of the benchmark. The working reference has received a [4/5 human visual review](reports/human-review-v1.md), with manual functionality explicitly not tested. The controlled defects remain unreviewed, and all candidates remain excluded from training.

[Original repair candidates](artifacts/original-revision-candidates-v1/review.html) add exact code changes and before/after measurements for those defects. The three records share one design family. A separate [repair sampling comparison](reports/repair-sampling-v1.md) found no full-audit improvement over greedy decoding on three reused development failures.
