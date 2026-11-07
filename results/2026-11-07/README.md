# Results, 2026-11-07

Each number below comes from a file in this folder, on branch `feat/arch-bench`. "Fully working" means every
real check, the integrator, Python and TypeScript all pass. Generated apps are simple create-and-list web apps
from fixed templates, so these numbers do not apply to arbitrary software.

## Baseline: manager SLM + four specialists, OAuth removed

| Test | Tasks fully completed | File |
|---|---|---|
| 90 clean dev briefs, not used for tuning | **81 of 90** | `baseline/report90.json` |
| 10 held-out briefs, new app ideas and phrasings | **10 of 10** | `baseline/report10.json` |
| 26 seed briefs for real systems, judged by reading the output | **0 of 26 usable** | `seed-26-briefs/` |

The 26-brief score is a judgment, made against a standard set before the run: the result must attempt the hard
part of the request. Of 24 plans that compiled, 16 passed the integrator, and 90% of files matched the generic template.

## Manager (100 dev briefs, H100)

| Measure | Result | File |
|---|---|---|
| Flat manager, plans exactly right | 81% | `manager-h100/flat-dev-raw.jsonl` |
| Nested manager, plans exactly right | 72% | `manager-h100/nested-dev.json` |
| Nested, with plural repair | 86% | Computed from the raw output |
| Nested, plural repair, OAuth removed (clean 90) | 89 of 90 | `baseline/report90.json` |
| Generated tests that pass on gold and catch a broken version | 84.1%, or 90.9% with the client content-type fix | `manager-tests/` |

An earlier L4 run scored 76% flat and 65% nested with repetition loops, which did not occur on the H100. The cause
is unknown, so serving setup can affect results.

## Team on the first 10 dev briefs, as fixes were added

These briefs were used for tuning, so treat them as an upper bound. Files are in `team-10-briefs/`.

| Stage | Checks passed | Fully working |
|---|---|---|
| First run | 198 of 240 | 0 of 10 |
| Route guard prompt fixed | 216 of 240 | 5 of 10, counted by the stricter verdict |
| Plural repair | 231 of 240 | 5 of 10 |
| Code-written shell and titles, form repair, retries | 239 of 240 | 9 of 10 |

## Other files

- `screenshots/`: real browser screenshots, unstyled
- `ollama-rewording/`: Qwen and Llama wording pilot, 20 briefs each
- `bench-speed-test/`: one-brief `slm.arch` speed test
- `baseline/team10-projects/`, `seed-26-briefs/projects/`: generated projects

## Not included

Trained model files stay on the `slm-vol` Modal volume, in `adapters/901/` and `manager/m-spec/`. The reduced
`slm.arch` comparison had not finished when this was written.
