"""Plan scoring: is the manager's split usable, and how close is it to the reference split?

A plan is *usable* when it uses all four specialists with valid domains/kinds/targets, every
dependency exists and points backwards, and every task's required interface is provided by an
earlier task. Closeness to gold is measured by task recall over (domain, kind, target).
"""

from __future__ import annotations

from pydantic import BaseModel

from slm.contracts import DOMAINS, ProjectPlan, Task


class PlanScore(BaseModel):
    valid: bool  # parsed and structurally valid (all four domains, deps, kinds)
    deps_satisfied: bool  # every task's requires is provided by an earlier task
    domain_coverage: float  # share of the four specialists the plan uses (1.0 for a valid plan)
    task_recall: float  # share of gold (domain, kind, target) triples the prediction contains
    task_precision: float  # share of predicted triples that are in the gold plan
    isomorphic: bool  # same task set by (domain, kind, target)


def _key(t: Task) -> tuple[str, str, str]:
    return (t.domain, t.kind, t.target)


def deps_satisfied(plan: ProjectPlan) -> bool:
    provided: set[str] = set()
    for t in plan.tasks:
        if any(s not in provided for s in plan.requires(t)):
            return False
        provided |= set(t.provides())
    return True


def score_plan(pred: ProjectPlan | None, gold: ProjectPlan) -> PlanScore:
    if pred is None:
        return PlanScore(valid=False, deps_satisfied=False, domain_coverage=0.0, task_recall=0.0,
                         task_precision=0.0, isomorphic=False)
    pred_keys = {_key(t) for t in pred.tasks}
    gold_keys = {_key(t) for t in gold.tasks}
    hit = len(pred_keys & gold_keys)
    return PlanScore(
        valid=True,
        deps_satisfied=deps_satisfied(pred),
        domain_coverage=len({t.domain for t in pred.tasks}) / len(DOMAINS),
        task_recall=hit / len(gold_keys) if gold_keys else 0.0,
        task_precision=hit / len(pred_keys) if pred_keys else 0.0,
        isomorphic=pred_keys == gold_keys,
    )


def score_json(text: str, gold: ProjectPlan) -> PlanScore:
    """Score raw model text; unparseable text is invalid."""
    try:
        pred = ProjectPlan.model_validate_json(text)
    except ValueError:
        pred = None
    return score_plan(pred, gold)


def summarize(scores: list[PlanScore]) -> dict[str, float]:
    n = max(len(scores), 1)
    return {
        "n": len(scores),
        "valid": sum(s.valid for s in scores) / n,
        "deps_satisfied": sum(s.deps_satisfied for s in scores) / n,
        "domain_coverage": sum(s.domain_coverage for s in scores) / n,
        "task_recall": sum(s.task_recall for s in scores) / n,
        "task_precision": sum(s.task_precision for s in scores) / n,
        "isomorphic": sum(s.isomorphic for s in scores) / n,
    }
