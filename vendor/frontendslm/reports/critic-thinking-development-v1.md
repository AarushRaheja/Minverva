# Thinking Critic development comparison

The alternative 4B Thinking Critic failed the semantic development gate and is not promoted. It noticed the quantity mismatch but proposed a change that conflicts with the required workflow. It also introduced an unsupported initial-form-state finding. Independent validators prevented both responses from being accepted.

| Measure, six frozen cases | Instruct control | Thinking alternative |
|---|---:|---:|
| Valid JSON syntax | 6/6 | 6/6 |
| Valid critique contract, including regions | 6/6 | 5/6 |
| Valid measured-evidence coverage and use | 6/6 | 4/6 |
| Passing controls retained | 4/4 | 3/4 |
| Known copy contradiction correctly reported | 0/1 | 0/1 |
| Output tokens, including reasoning | 948 | 35,974 |
| Inference seconds | 39.6 | 813.7 |

All six system instructions, structured input payloads, schemas, screenshot hashes and browser-evidence hashes match exactly between runs. The checkpoint, template, sampling and total output budget changed together; this is not a pure checkpoint causal comparison. Each run records its exact source snapshot and runtime.

The Thinking quantity response labels the passing edge-case workflow an interaction failure and asks to prevent values above 2. Independent validation rejects passing-test evidence for broken interaction. For the original failed UI, the mandatory measured issue is present, but the recommendation still retains the disabled maximum of 2. Measurement coverage alone does not verify advice.

The Thinking form response treats a required post-submission validation message as an initial-state requirement. It also emits two zero-area screenshot regions; contract validation rejects them. Three other controls remain accepted. No response exhausted its token budget.

The adapter permits reasoning until the actual tokenizer closing token, then enables the JSON grammar. Six syntactically valid final answers verify that routing on this batch. The [official model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Thinking) provides the checkpoint family and recommended sampling values. The run used a declared 16,384-token limit, below the card's 40,960 VL recommendation. Routing follows the first-call behavior in [XGrammar 0.2.8](https://raw.githubusercontent.com/mlc-ai/xgrammar/v0.2.8/python/xgrammar/contrib/hf.py).

These are repeated development cases, not independently human-labeled accuracy measurements. The quantity brief describes a 1→2→1 example and a minimum of 1; it does not state a maximum. The expanded workflow explicitly tests beyond 2. A future requirements representation should distinguish example transitions, actual bounds and derived test requirements. Historical evidence and scores remain unchanged.

Separately, [audit 2.1](exact-numeric-audit-v1.md) now checks numeric targets exactly and records observed text. Its controlled mutation test closes a demonstrated substring false pass. It does not retroactively strengthen these six frozen inputs.

Both comparison apps are stopped with zero tasks. No training occurred. Broad functional reliability, learned Critic grounding and human preference for the generated interfaces remain unproven. Local validation: 57 tests and Ruff pass.
