"""Pure-logic pieces of manager training/eval (no torch). Imported by modal_apps/manager_app.py."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from slm.contracts import Project, ProjectPlan
from slm.manager.score import PlanScore, score_json, summarize
from slm.manager.spec import ProjectSpec, SpecScore, score_spec_json, summarize_specs, to_plan

IGNORE = -100
DEPTH_BINS = (3, 4, 5, 6)


def chat_messages(row: dict) -> list[dict]:
    """Prompt-side messages from an sft_rows() row. The ONLY place a row becomes chat turns."""
    return [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["prompt"]}]


def build_labels(prompt_ids: list[int], completion_ids: list[int], eos_id: int,
                 max_len: int = 3072) -> tuple[list[int], list[int]]:
    """(input_ids, labels): loss on completion + eos only. NEVER truncates: raises TooLong instead
    (callers drop such rows), because a clipped completion teaches the model never to finish."""
    ids = prompt_ids + completion_ids + [eos_id]
    if len(ids) > max_len:
        raise TooLong(len(ids))
    labels = [IGNORE] * len(prompt_ids) + completion_ids + [eos_id]
    return ids, labels


class TooLong(ValueError):
    pass


def length_stats(lengths: list[int]) -> dict:
    """Token-length distribution for the training log."""
    if not lengths:
        return {"n": 0}
    s = sorted(lengths)
    q = lambda f: s[min(len(s) - 1, int(f * len(s)))]  # noqa: E731
    return {"n": len(s), "mean": round(sum(s) / len(s), 1), "p50": q(0.5), "p90": q(0.9),
            "p99": q(0.99), "max": s[-1]}


def depth_bin(depth: int | None) -> str:
    if depth is None:
        return "none"
    for b in DEPTH_BINS:
        if depth <= b:
            return f"<={b}"
    return f">{DEPTH_BINS[-1]}"


class EvalRecord(BaseModel):
    project_id: str
    depth: int | None
    output: str  # raw model text
    score: PlanScore


def score_outputs(projects: list[Project], outputs: list[str]) -> list[EvalRecord]:
    return [
        EvalRecord(project_id=p.id, depth=p.depth, output=o, score=score_json(o, p.plan))
        for p, o in zip(projects, outputs, strict=True)
        if p.plan is not None
    ]


def summarize_records(records: list[EvalRecord], n_failures: int = 10) -> dict:
    """Overall + per-depth-bin summary and a few failure examples (invalid first, then low recall)."""
    by_bin: dict[str, list[PlanScore]] = defaultdict(list)
    for r in records:
        by_bin[depth_bin(r.depth)].append(r.score)
    fails = sorted((r for r in records if not r.score.isomorphic), key=lambda r: (r.score.valid,
                                                                                -r.score.task_recall))
    return {
        "overall": summarize([r.score for r in records]),
        "by_depth": {k: summarize(v) for k, v in sorted(by_bin.items())},
        "failures": [
            {"project_id": r.project_id, "depth": r.depth, "valid": r.score.valid,
             "task_recall": round(r.score.task_recall, 3), "output": r.output[:600]}
            for r in fails[:n_failures]
        ],
    }


def plan_json_schema() -> dict:
    return ProjectPlan.model_json_schema()


def parse_plan(text: str) -> tuple[ProjectPlan | None, str | None]:
    try:
        return ProjectPlan.model_validate_json(text), None
    except ValueError as e:
        return None, str(e)


def spec_json_schema() -> dict:
    return ProjectSpec.model_json_schema()


def parse_spec_plan(text: str) -> tuple[ProjectPlan | None, str | None]:
    """The plan a nested reply compiles to, or the reason it does not compile."""
    try:
        return to_plan(ProjectSpec.model_validate_json(text)), None
    except ValueError as e:
        return None, str(e)


class SpecEvalRecord(BaseModel):
    project_id: str
    output: str  # raw model text
    score: SpecScore


def score_spec_outputs(projects: list[Project], outputs: list[str]) -> list[SpecEvalRecord]:
    return [
        SpecEvalRecord(project_id=p.id, output=o, score=score_spec_json(o, p.plan))
        for p, o in zip(projects, outputs, strict=True)
        if p.plan is not None
    ]


def summarize_spec_records(records: list[SpecEvalRecord], n_failures: int = 10) -> dict:
    """Overall summary and a few failures: the ones that did not compile first, then by low recall."""
    fails = sorted((r for r in records if not r.score.plan.isomorphic),
                   key=lambda r: (r.score.compiled, r.score.plan.task_recall))
    return {
        "overall": summarize_specs([r.score for r in records]),
        "failures": [
            {"project_id": r.project_id, "parsed": r.score.parsed, "compiled": r.score.compiled,
             "task_recall": round(r.score.plan.task_recall, 3), "output": r.output[:600]}
            for r in fails[:n_failures]
        ],
    }


def retry_prompt(user: str, previous: str, error: str) -> str:
    """Same wording as LLMClient.complete's retry, so the eval retry matches production semantics."""
    return (
        f"{user}\n\nYour previous response failed validation:\n{error}\n\n"
        f"Previous response:\n{previous}\n\n"
        "Return ONLY a JSON object that matches the schema."
    )
