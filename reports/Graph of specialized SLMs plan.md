# Architecture: one manager SLM, four domain specialists, one integrator

This note replaces the earlier arithmetic-DAG design. The research question is unchanged in spirit —
do small specialists beat a bigger monolith? — but the system is now a concrete software team
instead of a graph over eight arithmetic ops.

## The system

```
project brief
   │
   ▼
manager SLM (Qwen3-1.7B + LoRA)
   │  ProjectPlan: tasks tagged database | auth | network | frontend,
   │  with dependencies derived from interface symbols
   ▼
dispatcher — per dependency level, all ready tasks in parallel
   ├── spec-database   schemas        src/database/<table>.sql
   ├── spec-auth       sessions/OAuth/guards  src/auth/*.py
   ├── spec-network    routers/clients        src/network/*.py, *.ts
   └── spec-frontend   pages/forms/shell      src/frontend/*.tsx
   ▼
integrator — merge, generate glue, check seams
   ▼
Deliverable: one file tree + README + pass/fail per check
```

The four specialists are LoRA adapters on one Qwen3-0.6B base, served by a single vLLM multi-LoRA
deployment, so a whole project runs against one server and one GPU pool.

## Why interfaces are symbols

The previous design routed arithmetic nodes by a deterministic rule over operand shapes. A software
team cannot be routed that way — the split is the manager's job — so the contract moves down a level:
each task declares the **symbols** it exports (`table:orders`, `endpoint:GET /api/orders`,
`guard:session`, `route:/orders`, `component:OrdersPage`) and the symbols it consumes. This gives us
three things at once:

1. **Dependencies are computed, not guessed.** A task's `deps` are the tasks that provide its
   `requires`, which is why the dispatcher can parallelize safely.
2. **The grader does not need a reference implementation.** `check_task` looks for the exact token
   each symbol must appear as (`CREATE TABLE orders`, `@router.get("/api/orders")`, …). A task either
   honors its contract or it does not.
3. **Integration is measurable.** The integrator's seam checks (`frontend_endpoints_resolve`,
   `tables_defined`, `imports_resolve`, `guards_wired`, `requires_satisfied`) are exactly the failures
   that a single-model monolith makes and a decomposed team can localize.

## Data

Ten project templates (eight train, two held out), each producing a brief, a gold plan (10–13 tasks
over four dependency levels) and a gold artifact per task. Training data is per domain: an auth
adapter never sees a SQL schema. The manager trains on (brief → plan) pairs. Held-out test briefs use
entities and wording absent from training.

## Metrics

- **Deliverable pass rate** — every integration check green. Primary.
- **Task pass rate** by domain — which specialist is the bottleneck.
- **Plan validity / task recall / precision** — is the manager's decomposition the problem?
- **Wall clock** at concurrency 1, parallel vs serial dispatch, and calls/tokens per project to
  price the architecture against one bigger model.

## Prior work this builds on

Management hierarchies of models ("manager → workers") and role-specialized code agents are well
explored; the empirical finding that drives this design is that **coordination, not in-stream
quality, is where multi-agent systems lose** (parallel agents fail at integration). Our answer is to
make integration a first-class, deterministic, fully checked step rather than one more model call,
and to measure the residual error by blame: manager, specialist, or seam.

Relevant threads: mixture-of-experts routing (Why do we need experts at all — Arrow's ~10-expert
point), LoRA-per-task specialists (cheap, swappable, one base), plan-then-execute decomposition, and
role-specialized agents for coding. The earlier version of this project tested the same hypothesis on
exact arithmetic, where a graph of 256 op-specialists is easy to grade but says little about software
work; the domains here — network, security/auth, frontend design, database — are the ones a real
project actually splits along.

## Risks

- **Gate ceilings.** A 0.6B adapter may not write a correct FastAPI router reliably. HP1/HP2 (recipe
  and data-efficiency sweeps) decide whether to move specialists to 1.7B (AR1).
- **Manager fragility.** A plan that omits a task makes the product fail for a non-specialist reason;
  the attribution function separates those cases so the comparison stays honest.
- **Contract gaming.** A specialist could emit the required tokens without real content. The seam
  checks plus the gold-artifact tests bound how much that can hide; AR8's verifier arm is the
  mitigation if it shows up.
