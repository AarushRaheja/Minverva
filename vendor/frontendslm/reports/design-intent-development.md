# Design-intent development observations

The preference is “Clean product UI, like Linear or Stripe.” It is recorded as a user statement in `design/preferences.json`. The implementation follows the linked research and evaluation distinctions in `docs/design-intent-and-quality.md`.

Five original descriptor probes cover calm/dense, warm/editorial, playful/professional, premium/light, and a deliberately undefined private word. They are diagnostic examples, not a representative user-language benchmark or training set.

## Initial Modal probe

`design-intent-probes-v1` failed during worker startup because a Python module was missing from the image; no inference results were produced. The packaging was corrected and the failed run retained.

`design-intent-probes-v2` produced five schema-valid results with valid quote provenance. Manual inspection found:

- The calm/dense probe selected a compact workspace and preserved the avoidance of playful decoration.
- The private word was preserved and left unresolved, with clarification questions.
- The warm/editorial, playful/professional, and premium/light probes asked unnecessary questions or classified familiar language as unresolved.
- One light-mode explanation suggested “minimal contrast,” which is not an acceptable interpretation of readable light styling.

Therefore, **5/5 schema validity does not mean 5/5 correct understanding**. The next revision limits questions to one blocking ambiguity, makes ordinary descriptor interpretations explicit, requires adequate text contrast, and keeps optional features out of the unresolved-descriptor field. The rerun is recorded separately as `design-intents-v3`, including two development UI briefs.

These observations are an engineering review of model outputs. They are not human preference scores, target-user interviews, or evidence that all unusual descriptors are understood correctly.

## Follow-up results

`design-intents-v3` removed the unnecessary questions on the ordinary probes, but it also wrongly treated the explicitly undefined private term as resolved. One structured benchmark brief produced decorated source quotations rather than exact quotes. These are retained as failures.

`design-intents-v4` constrained source quotes to real input phrases. Both development briefs passed provenance validation and had no unresolved descriptors. The private-term response identified the term as unresolved but omitted its question, so validation rejected it.

`design-ambiguity-guard-v5` added a narrow deterministic guard for language explicitly declaring that a term has no definition. Both the output schema and independent validator require clarification in that situation. Modal verified that the calm/dense brief was ready for generation and the private-term brief was blocked with one concrete question. This guard does not claim to detect every unfamiliar word.

Two new development UIs using these intents passed the complete functional gate after up to two repairs (`design-development-v6`), with one passing initially. Their visual quality remained weak on inspection. An added composition-example prompt experiment (`design-example-v7`) did not improve functional acceptance: neither candidate passed after its one allowed revision. The separate [visual-rubric pilot](visual-rubric-pilot.md) was not sufficiently discriminating to support automated beauty acceptance.
