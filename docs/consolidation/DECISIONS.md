# Decisions

Why the consolidated pipeline is built the way it is. Newest first within each section. Each entry says what would change it.

## Scope

**D1. Consolidate first, optimize later (user, 2026-11-07).** Nothing is tuned for quality or cost yet, and no training has been added. The first goal is a complete path that runs and tells the truth about what it produced.

**D2. Agentic web development is the target (user, 2026-11-07).** The 0 of 26 real-system briefs (CDN edge runtimes and so on) are out of scope. This does not remove the limit in [ISSUES](ISSUES.md) #3: web briefs can also ask for more than the backend can make.

**D3. Do not train the frontend on 2,000 examples yet (recommended to the user, 2026-11-07).** There is no preference model to generate from: FrontEndSLM has human A/B tooling with no results, and its rubric failed calibration. Audit passes alone would teach passing tests, not good design. The backend recipe outputs gold-identical code about 97-98% of the time because its data is templated, and the same recipe could collapse UI variety. Rough cost at 4/10 acceptance: 5,000 briefs, about $750 and 350 GPU-hours run serially. Every run directory keeps the brief, source, audit and verdict, so real data accumulates. **Would change with:** human pair-review results and a pilot of about 200 examples with a held-out test.

## Filling the gap between a short brief and a UI

**D0. Two prompts: "what do you want" and "how should it look" (user, 2026-11-07).** `minerva build "<what>" --look "<how>"`. What goes to the manager and backend. The look goes only to the frontend, through the design intent stage and the Architect, each phrase quotable as provenance. An empty look uses FrontEndSLM's stored preference, "Clean product UI, like Linear or Stripe". The manager was trained on one-line briefs about function, so style words there only add noise. **Two limits:** the frontend is a separate pipeline in what it reads, but it still runs after the backend, because it needs the real API. And the trained manager still emits a `frontend` section, because that is its schema: its pages are used only for routes and the entity list, not as frontend instructions. Removing it would mean retraining.

**D4. Code decides facts; the model decides presentation.** Entities, endpoints, fields, test IDs and tests come from the plan, by code. Layout, style, copy and empty states come from the Thinking Architect. `tsc` is the validator: `api.ts` is the only route to the server, so an invented field or endpoint fails the build (the `invented_field` mutant proves this). **Why not let the model infer it all:** an invented `cook_time` would call an API that does not exist.

**D5. Each test exists twice.** The model sees placeholders; the harness runs nonces that change every round, against seed rows that exist only in the database. Hardcoding cannot pass, and an example cannot be misread as a limit, which is the failure FrontEndSLM's own reports describe (1→2→1 read as a maximum of 2).

**D6. Tests are compiled, not chosen from FrontEndSLM's table.** `audit_case` knows 10 interaction patterns and raises `KeyError` otherwise. The compiled set is deliberately small: navigation and list, one create per entity, empty-title rejection, sign-out.

## Frontend agent

**D7. One whole-frontend call after the backend, not one call per page.** The Architect's proven contract is one raw TSX file; FrontEndSLM's multi-file JSON attempt caused truncations. The plan stays unchanged, because page tasks feed the route guard's prompt. `page`, `form`, `layout` and `client` tasks are never sent to a specialist. The `spec-frontend` adapter is retained in `models/` but is unused.

**D8. Thinking Architect by default, Instruct by flag.** Thinking has the best repair result (3/3 fixed), but only on reused cases, at 412.8 s for 3 repairs, with one stale-copy false accept. This is a bet the user chose to explore, not a measured win. `--architect instruct` is the comparison arm.

**D9. Instruct Critic, as a check rather than a designer.** The Thinking Critic was rejected by FrontEndSLM's own report (4/6 valid vs 6/6; 813.7 s vs 39.6 s). Neither Critic caught the known content contradiction. So the Critic can stop a page being called `verified`, but cannot fail a working one or drive repair. Component repair removes its suggestions anyway.

**D10. At most 1 repair round by default; stop early if a revision is unchanged.** On Instruct, rounds 2 and 3 added no passes.

**D11. Rejected, and left out:** Thinking Critic, composition example, visual rubric as a gate, repair sampling, unit and line patches.

## Audit

**D12. Audit the real assembled project, not a mock.** Postgres, the generated FastAPI app and the built frontend, served same-origin. A mock would be a second API implementation that drifts. The ban existed only because the frontend repo was siloed (user, 2026-11-07).

**D13. Backend preflight before any frontend spend.** A backend 500 would otherwise look like an Architect failure and burn repair rounds. Preflight is stricter than the older `runcheck`, which counted a 5xx as "refused".

**D14. The network stays blocked in the sandbox.** Everything is on localhost, so lifting the silo did not require opening egress. FrontEndSLM's blueprint asks for restricted egress and no API keys in the sandbox, and both still hold.

**D15. Generated code never runs on this machine.** `LocalAuditor` requires `trusted=True` and is used only for gold fixtures and the reference UI; `ModalEngine.audit` always uses the sandbox.

**D16. Audit tests start signed in.** The harness seeds a session cookie, so measurements and screenshots show the app rather than a login wall. The sign-up flow is tested separately by the journey.

## Integrator

**D17. A script, not an agent.** Everything missing is deterministic. A model here would add failures and weaken what "verified" means. It runs every round, so what is audited is what ships.

**D18. Real accounts, not a demo cookie.** Generated apps had no login route; the old preview injected `app_session=demo`. The integrator writes signup, login and logout with scrypt and an HttpOnly, SameSite=Lax cookie. This is more than the "dev-only sign-in" first described to the user, because a real one costs about the same and gives a real journey to test. It is still not production-hardened, and the generated README says so.

**D19. `api.ts` replaces the specialist's typed client.** That client covers one entity and has no error handling. The trained `spec-frontend` gold form also hardcodes `title: "new <x>"`, ignoring what the user types.

**D20. Reserved table names are renamed by code.** The manager emits `order`, `case` and `analysis`; `CREATE TABLE order` is a syntax error.

**D21. A labelled fallback, not a silent one.** If no generated UI works, the reference UI ships as status `fallback_ui`, exit code 20. `--no-fallback` turns this off. (Assumed acceptable; not yet confirmed by the user.)

## Serving and repo

**D22. Reuse the batch functions that were measured for real.** `plan_briefs` and `write_code`, each under its own `app.run()`, rather than the vLLM server. That server has never run the trained adapters and can't host the manager.

**D23. Import, do not merge histories.** Three unrelated histories, large blobs and other people's identities add nothing at runtime. `PROVENANCE.md` records the commits.

**D24. Adapter weights are not in git.** About 150 MB, with one 69.8 MB file. They live on the Modal volume `slm-vol` (hashes in `models/SHA256SUMS` were checked against the volume for the manager and the three backend adapters) and on `feat/arch-bench`. **Would change if:** that branch or volume could disappear; then publish a release asset.

**D26. Every project prepares its own database at startup (user, 2026-11-07).** Written by the integrator, so it applies to every run. With `DATABASE_URL`, it creates a missing database and applies the schema, and stops with a clear error if the server can't be reached. Without it, a private Postgres in `.data/`, using `pgserver` on Python 3.11-3.12 or system binaries otherwise. `APP_ENV=production` refuses that fallback. `verify` starts from a database that does not exist and runs no setup, so a project that can't do this fails.

**D25. Vendored as-is under `vendor/frontendslm/`.** Its modules are reached through `minerva/vendored.py`. Keeps the diff against upstream readable, at the cost of a `sys.path` entry.
