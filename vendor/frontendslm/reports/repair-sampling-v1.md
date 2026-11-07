# Repair decoding comparison

**Recommended sampling did not improve full-audit acceptance in this diagnostic: 0/3 versus greedy 0/3 after one repair.** This is a negative result on reused development cases, not an independent estimate of general repair accuracy.

The experiment used Qwen's recommended temperature 0.7, top-p 0.8, top-k 20 and min-p 0. It retained the existing 6,144-token budget, repetition penalty 1.05, seed 42, model revision, initial sources, prompts, full browser tests and Critic protocol. All three sampled repair prompt hashes exactly match the corresponding greedy round-one prompts. [Official model guidance](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507#best-practices).

| Development case | Greedy full pass | Sampled full pass | Sampled remaining failure |
|---|---|---|---|
| A0/operations_01 | No | No | Intermediate-state accessibility |
| A0/configuration_02 | No | No | Quantity interaction verification |
| A1/learning_01 | No | No | Accordion visibility verification |

All three sampled revisions compiled and changed their source. Some initial contrast failures disappeared, but the complete workflows still failed. Six Critic calls (three initial and three revised) were schema-valid and measurement-valid, with zero accept verdicts on known failed audits.

Structured validity still does not validate recommendation semantics. For example, the initial quantity critique mentions a maximum of two even though the required workflow reaches three. The forced measured observation and acceptance workflow are correct; the model's proposed advice remains contradictory. That advice was not used as authoritative repair instructions.

The default remains greedy. The optional `--repair-decoding qwen-recommended` switch records its settings and is retained for reproducibility; it is not a demonstrated improvement. No untouched briefs were consumed, and no training occurred.

[Protocol declaration](repair-sampling-protocol-v1.json) · [Exact comparison data](repair-sampling-v1.json) · [Screenshots and measurements](../artifacts/repair-sampling-review-v1/review.html).

The experiment completed and its Modal app stopped with zero tasks. A source snapshot, runtime records, raw output and checksum manifest are retained. Local validation: 34 tests passed and Ruff passed.
