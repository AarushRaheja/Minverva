# Source-unit repair diagnostic v1

The declared test finished with **3/5** candidates accepted, up from **2/5** initially. This includes **one repaired failure out of three** and two unchanged passing controls. The prior greedy complete-component diagnostic repaired 0/3 of the same failures after two rounds. These are repeatedly used development cases, not a prospective accuracy estimate.

| Candidate | Initial | Final | What happened |
|---|---|---|---|
| A0/operations_01 | Fail | Pass, round 2 | First patch duplicated closing tags; full-component fallback restored syntax while retaining corrected contrast and target size. |
| A0/configuration_02 | Fail | Fail | First patch contained a no-op; second patch duplicated complete elements into opening-tag ranges and failed compilation. |
| A1/learning_01 | Fail | Fail | First patch broke JSX; fallback restored compilation and contrast, but aria-hidden/opacity did not make the closed answer visually hidden. |
| A1/planning_02 | Pass | Pass, unchanged | Stopped after initial acceptance. |
| A1/forms_03 | Pass | Pass, unchanged | Stopped after initial acceptance. |

Six revision attempts were retained. Five produced an assembled source manifest; only two compiled. All four structured-unit attempts failed acceptance; the one repaired case passed after an explicit full-component fallback. Do not attribute this to successful standalone AST patching. The ten critic calls all passed schema and measured-evidence validation. No failed audit was accepted; this is enforced reporting, not independent critic detection accuracy.

Initial source files and complete test plans match the earlier controls. Model locks, seed, audit and acceptance gate are unchanged. Prompts and repair format changed, so the result does not isolate localization alone. The TypeScript parser reads source as data and never runs the generated application locally; all builds and browser tests ran in network-blocked Modal sandboxes.

The observed failure suggests changing edit boundaries: small elements should be complete editable elements, with syntax rejection before browser execution and recovery of the exact base-source measurements. This is an engineering hypothesis, not a result. The protocol's expansion gate was **not met**: all three failures must be repaired before broader development testing or use of additional unused briefs.

The [Agentless project](https://github.com/OpenAutoCoder/Agentless) informs the localize–repair–validate structure. Its research results do not validate this model or experiment. No training was performed, and no beauty score was inferred. The separate [human review](human-review-v1.md) rates one original reference 4/5 and does not rate these model outputs.

[Review packet](../artifacts/unit-repair-review-v1/review.html) · [Machine-readable report](unit-repair-development-v1.json) · [Frozen protocol](unit-repair-development-protocol-v1.json). The Modal app completed and stopped with zero tasks; exact sources, runtimes, outputs and checksums are retained.
