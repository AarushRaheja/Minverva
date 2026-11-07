"""Project generator: a brief for the manager plus the gold decomposition for one project.

Deterministic per (seed, split, i): project i does not depend on n. Train/dev draw from the eight
training templates; split="test" draws only from the two held-out templates, so test items use
entities and wording the manager and the specialists never saw.
"""

from __future__ import annotations

import random

from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES, Template_, build_plan, render_description
from slm.contracts import Project


def templates_for(split: str) -> list[Template_]:
    return HELDOUT_TEMPLATES if split == "test" else TRAIN_TEMPLATES


def make_project(tpl: Template_, split: str, seed: int, i: int) -> Project:
    plan = build_plan(tpl)
    return Project(
        id=f"proj-{split}-{tpl.id}-s{seed}-{i}",
        source="synthetic",
        split=split,  # type: ignore[arg-type]
        description=render_description(tpl),
        plan=plan,
        n_tasks=len(plan.tasks),
        depth=len(plan.levels()),
        template_id=tpl.id,
    )


def generate(n: int, split: str, seed: int) -> list[Project]:
    """n projects; template choice is shuffled by seed so ordering does not leak the template."""
    pool = templates_for(split)
    out = []
    for i in range(n):
        rng = random.Random(f"proj:{seed}:{split}:{i}")
        out.append(make_project(rng.choice(pool), split, seed, i))
    return out


def generate_balanced(n: int, split: str, seed: int) -> list[Project]:
    """n projects with a (near-)equal share per template - one of each before any repeats."""
    pool = templates_for(split)
    out: list[Project] = []
    for i in range(n):
        tpl = pool[i % len(pool)]
        out.append(make_project(tpl, split, seed, i))
    return out
