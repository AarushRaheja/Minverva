# Status

**As of 2026-11-07: the whole path has run once on real models. The manager and backend worked; both generated UIs failed to build on that run, so it shipped the labelled fallback UI.** Work is on the branch `consolidate/v1`. See [PLAN](PLAN.md) for what is next, [ISSUES](ISSUES.md) for what is open, and [DECISIONS](DECISIONS.md) for why.

## Shown so far

| Check | Result | How to repeat |
|---|---|---|
| nova-hacks and FrontEndSLM merged, before any changes | 430 passed, 23 skipped | See `PROVENANCE.md` |
| Full default suite | 527 passed, 26 skipped | `uv run pytest` |
| FrontEndSLM's suite, with the prompt patch | 57 passed, 2 skipped | See ISSUES, upkeep |
| Minerva tests, including real Postgres, FastAPI and browser | 26 passed | `MINERVA_STACK=1 uv run pytest tests/test_minerva.py` |
| The audit can fail: clean control passes, every defect is caught | 21 of 21, in the local harness; a 4-case subset passed in the Modal sandbox before the self-setup change | `uv run python scripts/check_mutants.py`, saved in `results/consolidation/mutants.json` |
| An offline build, gold backend + reference UI | Sign-up journey passes; status `functional_with_defects`, correctly, as no Critic ran | `minerva build "<what>" --look "<how>" --engine offline` |
| Launching a generated project from nothing | 6 of 6: `make preview` on Python 3.12 and 3.14, bare uvicorn, own server with a missing database, and two refusals; no database process left running | `uv run python scripts/check_preview.py` |
| Static file route against path traversal | 8 of 8 attempts got `index.html`, not the file | Done once by hand; no automated test |
| Weights on Modal `slm-vol` match the repo | Manager and database, auth and network adapters match by SHA-256 | `models/SHA256SUMS` |
| Frontend models cached on Modal | All four present in `frontendslm-model-cache` (revisions not checked) | `modal volume ls` |

## First real runs

| Run | Result | Cost (estimate) |
|---|---|---|
| Restaurant back-of-house, `results/consolidation/restaurant-run-1/` | Manager planned the right entities and the backend passed preflight, but all 9 backend files were byte-identical to the gold templates. The first UI had 3 type errors; its repair dropped an import. Status `fallback_ui` | $0.58 |
| Restaurant back-office, `runs/restaurant-back-office/` (not kept in git) | Stopped by a false failure: `requires_satisfied` counted a stray `invoice` client that Minerva never uses. No project | $0.15 |

## Not shown

- **A generated UI passing this audit.** No real run has got that far. A hand-fixed copy of the repair type-checks, but was never run. (A compiling UI was reported from elsewhere; it is not on this path.)
- **The self-setup change in the sandbox.** The updated `verify` has only run locally, on trusted trees.
- **Whether the app matches the brief.** Every generated app is still limited to title-only rows.
- **Time and cost beyond these two runs.**

## How the pieces connect

```
what ──► manager (Qwen3-1.7B + LoRA) ──► ProjectSpec ──► prepare_spec: OAuth, plurals, reserved names
                                                              │
              ┌───────────────────────────────────────────────┤
              ▼                                               ▼
   database, auth, network adapters                      AppContract: entities, api.ts,
   (Qwen3-0.6B + LoRA)                                   test IDs, compiled tests
              │                                               │
              ▼                                               │
   seam checks + backend preflight in sandbox                 │
   failure stops here: no frontend is paid for                │
              │                                               ▼
              │                                  how ──► design intent (Qwen3-4B Instruct)
              │                                               │
              │                                               ▼
              │                              Architect (Qwen3-4B Thinking) writes App.tsx
              │                                               │
              └──────────────► integrator ◄───────────────────┤
                                   │                          │
                                   ▼                          │ measured failures,
                         audit on the real stack ─────────────┘ at most 1 repair by default
                                   │
                                   ▼ Critic (Qwen3-VL-4B Instruct), on an audit pass
                                   ▼
                         sign-up journey on the final tree
                                   ▼
                         project/ + REPORT.md + exit code
```

## Statuses

| Status | Exit | Meaning |
|---|---|---|
| `verified` | 0 | Audit passed, the Critic accepted, the journey passed. Not a claim that the design is good |
| `functional_with_defects` | 10 | The build, tests and journey pass, but a measured check failed or the Critic did not accept |
| `fallback_ui` | 20 | No generated UI worked; the plain reference UI shipped. Counts as a failure in any evaluation |
| `failed` | 30 | Names the stage: `plan`, `backend`, `preflight`, `frontend`, `verify` or `budget` |

## Log

**2026-11-07**

1. Studied FrontEndSLM `c7f5094`, the nested manager and trained backend on `feat/arch-bench` (`9df574f`), and the empty Minerva repo.
2. Merged `feat/arch-bench` with the unpushed `70ea35f` in a scratch clone. One conflict, in tests, both sides kept. 430 passed.
3. Imported both into this repo. Adapter weights are left out of git, with hashes recorded.
4. Wrote the bridge, integrator and harness, and got an offline run on a real stack.
5. **First run:** all browser tests passed, but the audit failed because the accessibility scan ran while sign-out was reloading the page. The harness now waits and retries.
6. **Mutant check:** 18 of 18, but `backend_no_auth` passed for the wrong reason: the mutation broke the function signature, giving a 422. Rewrote it to really remove auth; it now fails on signed-out requests getting 200.
7. **Traversal check:** a request with `..` returned 200, so the body was checked rather than assumed. It was `index.html` every time.
8. **Two-part prompt added** at the user's suggestion (D0): "what" goes to the manager and "how it should look" only to the frontend.
9. **Offline reports were misleading**, saying "the manager planned" when no manager ran. They now say no model was called.
10. **First real run** on a restaurant brief (table above). The sandbox image built and worked first time.
11. **Generated projects now set up their own database** (D26), after the user found a preview failing on an uninitialised database. Reproducing it also showed an unbuilt frontend returning 503, now handled too.
12. **Mistakes found while doing that:** template strings that were not raw broke generated files; a Makefile line damaged an existing `.venv`; `uvicorn` skips `atexit`, so Postgres leaked on stop. All fixed and checked. `reassemble`'s first version overwrote `project/` with no backup, in a folder another tool was also using; it now keeps `project.previous/`.
