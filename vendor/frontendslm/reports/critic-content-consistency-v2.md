# Critic content consistency v2

The replay **missed the known content contradiction (0/1)**. All six outputs were schema-valid and measurement-valid, four passing controls remained accepted, and the original measured interaction failure was reported. Those structural checks did not prevent a semantically wrong verdict or recommendation.

The model, images, raw browser evidence, source and complete required workflows were unchanged. The first replay added readable initial screen text, explicit executed assertion semantics, and a narrowly permitted content-consistency category backed by both screenshot and test evidence. The second additionally required per-workflow comparisons before the verdict, exact screen quotations and consistency between reported contradictions and the verdict.

The second replay quoted the stale quantity instruction exactly but incorrectly labeled it consistent. It inferred that an unchanged instruction demonstrated an enforced constraint; no such measurement exists. In both replays, the original failed-case recommendation still suggested an upper bound of two, despite the workflow requiring a later assertion containing three. The raw responses are preserved, not corrected after generation.

Expected development roles were written before inference in `run.json` and were not passed to the model. This is a regression diagnostic on six reused cases, not a precision/recall estimate or human labeling. Reference validation checks existence and coverage, not factual meaning. `expect_text` checks substring containment; no exact numeric observation is implied.

The experiment is complete and the Modal app is stopped with zero tasks. The semantic detection gate failed. Explicit content-review generation is now opt-in; readable evidence and the narrow validation exception remain available. The quantity source export stays withheld. There was no training.

See `run.json`, `source_snapshot.zip`, `report.json`, individual `critique.json` files and the original immutable screenshot/test evidence. To reproduce these exact historical prompts, use the source snapshot; current code includes the opt-in routing change.
