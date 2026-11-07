# Plan: a manager SLM and four domain specialists vs. one LLM

Design and prior work: [`reports/Graph of specialized SLMs plan.md`](reports/Graph%20of%20specialized%20SLMs%20plan.md).

## The question

Does **one manager SLM that decomposes a project brief, plus four small domain specialists**, beat
(a) one generalist model of the same size served through the same pipeline and (b) a monolith that
writes the whole project in one call — on **deliverable pass rate** and **wall-clock latency** — and
which failures are the manager's (bad decomposition) versus a specialist's (bad artifact)?

## The system

```
brief ─► manager (Qwen3-1.7B + LoRA) ─► ProjectPlan
                                          tasks: database | auth | network | frontend
                                          deps: interface symbols, not just ordering
            dispatcher (parallel per dependency level, one adapter per domain)
                ├── spec-database  ─► src/database/<table>.sql
                ├── spec-auth      ─► src/auth/{session,oauth,guards}.py
                ├── spec-network   ─► src/network/<entity>_api.py · <entity>_client.ts
                └── spec-frontend  ─► src/frontend/<Entity>Page.tsx · <Entity>Form.tsx · Shell.tsx
            integrator: merge, glue, seam checks ─► Deliverable
```

- **Domains and kinds** (frozen in `slm/domains.py`): database `schema`; auth `session`, `oauth`,
  `guards`; network `rest`, `client`; frontend `page`, `form`, `layout`.
- **Interfaces are symbols, not prose.** A task provides e.g. `table:invoice`,
  `endpoint:GET /api/invoices`, `guard:session`, `route:/invoices`, `component:InvoicePage`; it
  requires the symbols it consumes. The dispatcher derives dependencies from the plan, and the
  integrator verifies each symbol in the produced code with an exact token.
- **Integration checks** (all must pass for a deliverable to count): every task delivered, no path
  conflicts, per-task layout + provided/consumed tokens, `requires_satisfied`,
  `frontend_endpoints_resolve`, `tables_defined`, `app_glue_present`, `imports_resolve`,
  `guards_wired`.

### Benchmark items

Our own generator (`slm/bench/variety.py`) produces distinct one-line briefs from 48 app concepts
(30 train, 8 dev, 10 test) with one to four entities and optional OAuth. Train, dev and test share no
concepts or entity names, and test also uses phrasings train never saw. Each brief names its entities,
its form entity and any OAuth requirement, and ships with a gold plan and a gold artifact per task, so
a perfect run and a perfect score are both well defined and the integration checks are exercised by
construction.

The nested manager output (`slm/manager/spec.py`) adds groups, steps and tests at each level on top of
`ProjectPlan`. `to_plan` compiles it to the same plan the dispatcher already runs, so specialist prompts
do not change. A teacher model may reword its prose only (`slm/manager/enrich.py`).

### Arms

| Arm | Manager | Specialists | What it isolates |
|---|---|---|---|
| `gold` | gold plan | gold artifacts | contract/integrator sanity, latency floor |
| `specialists` | trained manager | four domain adapters | **our architecture** |
| `single` | trained manager | one generalist adapter for all four | value of specialization |
| `monolith` | none | one call writes every file | value of decomposition |

## Metrics (pre-registered)

- **Primary:** deliverable pass rate (all checks green) with 95% CI clustered by template; p50/p95
  project wall clock at concurrency 1; throughput at a fixed request rate.
- **Secondary:** plan validity, task recall/precision, per-task pass rate by domain, first failing
  check, calls/tokens/GPU-seconds per project, critical path (per level, the slowest task).
- **Hypotheses:** H1 the four-specialist arm beats the single generalist on deliverable pass rate at
  equal data. H2 it matches or beats the monolith with strictly fewer tokens on the critical path.
  H3 integration failures, not in-domain failures, dominate the residual error of the monolith.
- **Tests:** paired bootstrap / McNemar on identical briefs, greedy decoding, 2 seeds on the two
  learned arms.

Secondary experiments are pre-registered in [`EXPERIMENTS.md`](EXPERIMENTS.md).

## Workstreams (each one is an agent on its own branch)

| Agent | Stream | Owns (only these paths) |
|---|---|---|
| claude-1 | Project data & metrics | `slm/bench/`, `modal_apps/data_app.py`, `tests/test_bench*.py`, `tests/test_domains*.py` |
| claude-2 | Specialist training factory | `slm/train/`, `modal_apps/train_app.py`, `tests/test_train*.py` |
| claude-3 | Serving & dispatcher | `slm/serve/`, `slm/pipeline/`, `slm/llm/vllm.py`, `modal_apps/serve_app.py`, `tests/test_pipeline*.py` |
| claude-4 | Manager & baselines | `slm/manager/`, `slm/baselines/`, `slm/llm/hosted.py`, `modal_apps/manager_app.py`, `tests/test_manager*.py`, `tests/test_baselines*.py` |
| orchestrator | Contracts, review, merge | `slm/domains.py`, `slm/contracts.py`, `slm/llm/base.py`, `slm/trace.py`, `slm/cli.py`, `PLAN.md`, `tasks/`, `README.md` |

They connect only through the frozen contracts (`Task`, `ProjectPlan`, `Artifact`, `Deliverable`,
`check_task`, `integrate`, specialist prompts, `TrainExample`, `RegistryEntry`, the Volume layout)
and the trace schema. Each stream develops against `FakeClient` and the oracle specialists, never
against another stream's unfinished code.

## Budget (revised 2026-11-02): $30 of Modal, held by one teammate

One teammate has already spent $30 out of pocket and spends **nothing more**. The other teammate's
$30 of Modal credit is the only paid compute, and it goes **only to things that need a deployed
server**. Everything that is just backprop runs on free GPUs.

| Work | Where | Cost |
|---|---|---|
| Build data (`python -m slm.train build-data`) | any CPU | $0 |
| Train the 4 specialists + manager (`python -m slm.train backprop`, `notebooks/train_free.ipynb`) | Kaggle (30 GPU-h/week) or Colab T4 | $0 |
| HP1/HP2 probes, AR3 `spec-general`, AR4 merges, AR6 manager sizes | Kaggle / Colab | $0 |
| Gate evals and plan evals (generate + score inside the training run) | Kaggle / Colab | $0 |
| vLLM multi-LoRA server: smoke, `evaluate` (4 arms × dev/test), latency window (AR2), AR5/AR8 | Modal L4 | ≤ $24 (80% of $30) |
| Demo (`slm ui`, demo backend, or the vLLM backend while the server is up) | laptop | $0 |

At data scale 1.0 the training sets are small (360 / 315 / 360 / 480 rows per specialist, 120 manager
rows; 80–120 optimizer steps per adapter at batch 8 × 2 epochs), so a T4 trains the whole team in
about an hour. Adapters are written in the Volume layout (`out/adapters/<seed>/spec-*`,
`out/manager/<run>`) and handed over with `modal volume put slm-vol out/adapters /adapters`.
Rules for the Modal holder: L4 only, `min_containers=0`, run `modal app stop slm-serve` after every
session, stop at $24, and a workspace spend limit set in the dashboard.
