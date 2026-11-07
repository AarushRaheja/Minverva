# Plan

The goal is one command that takes a brief and produces a reviewable codebase, using the nested manager, the trained backend agents, FrontEndSLM's frontend architecture and an integrator. Current results are in [STATUS](STATUS.md).

| # | Milestone | Done when | Cost | State |
|---|---|---|---|---|
| M0 | Import both sources | Merged tests green, hashes match | $0 | **Done** |
| M1 | Offline path | Gold backend + reference UI run on a real stack, sign-up journey passes | $0 | **Done** |
| M2a | The audit can fail | The clean app passes and every defect is caught, locally | $0 | **Done** |
| M2b | The audit works in the sandbox | The same check passes in the Modal sandbox image | under $1 | Next |
| M3a | Architect on the new prompt | One saved real plan and backend, through the audit | about $0.50 | Not started |
| M3b | **First live end-to-end** | `minerva build` with every model; the user reviews the output | $1-2 | Not started |
| M4 | Development briefs | 3 dev briefs, prompt fixes, Instruct vs Thinking | $4-6 | Not started |
| M5 | Frozen evaluation | Briefs frozen before the first call; go/no-go gates below | $8-12 | Not started |

Costs are estimates. Treat $40 in total as a hard cap, and confirm each step with the user before spending.

## Proposed go/no-go gates for M5 (10 new create-and-list web briefs)

Set these before M5 runs, and do not move them afterwards. With n=10 these only catch gross failure.

| Gate | Threshold |
|---|---|
| Plan and backend preflight pass | at least 8/10 |
| Works after at most 1 repair | at least 7/10 |
| `verified` | at least 5/10 |
| False `verified` on human review | 0 |
| Median cost | at most $1.50 |
| 90th-percentile time | at most 30 min |

Also report, without gating: 10 real-world briefs from the webgen set, and the user's "would I keep this" score. Nothing from any evaluation brief enters training.

## After that, in order

1. Close the backend's biggest gap ([ISSUES](ISSUES.md) #3), since a nicer UI over a title-only app is still a title-only app.
2. Collect human pair reviews using FrontEndSLM's tooling.
3. Run the training pilot ([DECISIONS](DECISIONS.md) D3), if the data supports it.
4. Move serving to warm containers, if interactive latency matters.
