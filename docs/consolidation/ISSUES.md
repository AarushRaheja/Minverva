# Open issues

Most important first. Close an issue by moving it to the end with the commit or result that closed it.

## Needs a decision from the user

1. **Licence.** `nova-hacks` has no licence file and has other contributors. This repo is private. Before it is made public or its root MIT `LICENSE` is treated as covering that code, its contributors need to agree.
2. **Fallback UI (D21).** Is shipping a labelled plain UI acceptable when the Architect fails? Currently yes by default.
3. **Every app is title-only: how far past that should this go?** The trained backend makes tables with a title, and list, create and fetch-one. No other fields, edit or delete. A recipe brief becomes a list of recipe titles. `REPORT.md` puts the brief beside what was built, but that is a mitigation, not a fix. Fixing it means retraining the backend agents or writing more of the backend by code, and it decides which briefs the pipeline can honestly serve.
4. **The unpushed `70ea35f`.** It is imported here, but still only local on `claude-3/r1-dispatch` in `nova-hacks`, because `NOVA-SLM` refused the push (403). Pushing to the `aggarwalaarush34-hash` fork is the open option.

## What it can't do yet

5. **Backends reproduce templates.** On the 26 real-system briefs, plans still built generic create-and-list apps. On web briefs, entities should fit better, but this is unmeasured on the consolidated path. A polished UI could make a brief that was ignored look fine, which is the biggest risk here.
6. **Shared data.** Generated list endpoints do not filter by owner, so all signed-in users see all rows. `get` on a missing id returns 200 `null`. Documented in each project's README.
7. **Not production-hardened.** No rate limiting, password reset or CSRF token, and one session per user. Documented in each project's README.
8. **No URL routing.** Navigation is in-page state. A signed-out direct hit on a guarded route gets JSON 401 rather than the sign-in page, and a signed-in direct hit on a route also goes through the guard to the app.

## Unmeasured

9. **No real model has run on this path, and `ModalEngine` has only been imported, never run.** Everything so far uses gold backend code and the reference UI. Passing says the plumbing works, not that the models do.
10. **The sandbox image has never been built or run.** Postgres as root (handled with `runuser`), `block_network` with loopback, the 900 s limit and the Postgres 15 path are all assumptions until M2b.
11. **Architect reliability on this prompt is unknown.** The 4/10 prior was on a different prompt, without real data or `./api`. Don't assume it carries over.
12. **Thinking on new briefs is unknown** (D8): only 3 repairs on reused cases, and the 10-brief follow-up has a protocol but no results.
13. **Time and cost per run.** About $0.50-1 and 15-25 minutes are estimates. Modal's L40S rate was read from its pricing page through a summarizer, and Architect model load time has never been reported. The ledger's figures are estimates, not billing. `SpendGuard` does not cover these functions, so the budget check is the only guard.

## Limits of the checks

15. **Tests can't see inert controls.** A button that does nothing, beyond the tested flows, passes. Only human review catches this.
16. **Nothing measures whether the design is good.** The rubric failed calibration and the Critic is not calibrated either.
17. **Test coverage is deliberately small (D6).** One validation on the primary entity, and create-by-title for each. Filters or sorting a model adds are untested.
18. **The frozen clock in the harness** (`2026-11-07T12:00Z`) can disagree with real server timestamps, so "3 minutes ago" text may look odd in screenshots. Harmless to the current tests.
19. **Audit ports.** Postgres uses a port derived from the process ID, and a collision between parallel runs would surface as a harness error.

## Upkeep

20. **Sources keep moving.** `nova-hacks` and FrontEndSLM will change. This is a one-way snapshot; `PROVENANCE.md` has the commits to diff from.
21. **Unused code is still here.** `spec-frontend`, `slm/ui`, `slm/arch`, `slm/serve` and the vLLM path are not used by `minerva build` (D22). Remove once the path has proved itself.
22. **Vendored tests are separate.** Run them with `cd vendor/frontendslm && npm ci --prefix sandbox --ignore-scripts && PYTHONPATH=src:. uv run --project ../.. python -m pytest tests --rootdir=.`.
23. **Package pins for generated projects** (`fastapi==0.115.12`, `uvicorn==0.34.3`, `asyncpg==0.30.0`, and the npm lockfile) work, but are not security-reviewed or on an update schedule.
24. **`results/2026-11-07/README.md` says models are not included**, which is stale; `models/README.md` is right.
25. **The wheel is not usable on its own.** It leaves out `vendor/`, `harness/` and `templates/`, so `minerva` only works from a checkout.
26. **Preview database trust.** The system-Postgres path listens on localhost with `trust` auth, so other local users could connect while it runs. Previews only.
