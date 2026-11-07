# Visual-rubric pilot: not suitable for automatic acceptance

Five desktop/mobile screenshot pairs were reviewed in a seeded shuffled order with condition names hidden from the model. The pinned Qwen3-VL-4B model received the task, intent and research-informed rubric. This was a diagnostic pilot, not a human-labeled aesthetic benchmark.

| Source | Model proxy | Output validity |
|---|---:|---|
| Design-development form, after two repairs | 78/100 | Valid schema and references |
| Design-development checklist | 100/100 | Valid schema and references |
| Original v2 form | 100/100 | Valid schema and references |
| Original assistant-authored composition reference | Unavailable | Rejected: zero-area evidence boxes |
| Original v2 checklist | 100/100 | Valid schema and references |

The perfect checklist scores are not persuasive evidence of visual excellence. Inspection found a sparse composition and, in the new checklist, a control with no visible action label. The model described these as exceptional across every dimension and cited the whole screenshot. It also emitted `[1,1,1,1]` evidence regions for the composition reference; the independent validator correctly rejected them. The raw response remains unchanged.

**Decision:** Do not use this visual score as an acceptance gate or advertise it as beauty accuracy. Keep measured functional checks separate. Use the rubric to structure human ratings and collect intended/perceived descriptors; calibrate a future visual critic on independent human labels before trusting its scores.

The composition reference was authored by the Codex assistant, not the 4B Architect. It passed its own Modal build, browser interaction, responsive and accessibility audit, but it is not evidence of small-model performance or human preference. It was used explicitly in a separate prompt experiment, which failed the functional gate for both development briefs after one revision. Those failures are retained in `design-example-v7`.

Artifacts: `artifacts/visual-rubric-pilot-v1`, blind mapping `design/visual-pilot-key.json`, composition reference `artifacts/design-composition-reference`. No training was performed.
