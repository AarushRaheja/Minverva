"""The existing project catalog as tasks: an empty folder, a brief, and the run check as the independent grade.
This and the matching grader and adapter are the only modules that import the agent's repo package."""

from __future__ import annotations

from evaluation.benchmarks.task_registry import TaskSpec

SEED = 20261103
DEV_TEMPLATES = ("invoice_tracker", "issue_board", "stock_room")  # the dev projects every recorded arm finished


def catalog() -> list:
    from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES
    from slm.bench.projects import generate_balanced

    return generate_balanced(len(TRAIN_TEMPLATES), "dev", SEED) + generate_balanced(len(HELDOUT_TEMPLATES), "test", SEED)


def instruction_for(project) -> str:
    """The same rules the one-call baseline gets, so every agent is held to the same contract."""
    from slm.arch.runner import MONO_RULES

    return (f"Build this whole project as files in the current folder.\n\nProject brief:\n{project.description}\n\n"
            f"{MONO_RULES.strip()}\n\nWrite real files. Don't start long-running servers. Finish when the project is complete.\n")


def project_tasks() -> list[TaskSpec]:
    out = []
    for p in catalog():
        if p.template_id not in DEV_TEMPLATES and p.split != "test":
            continue
        out.append(TaskSpec(id=f"build-{p.template_id}", family="project_build", benchmark="project-build",
                            task_class="greenfield", capability="code_generation", difficulty="medium",
                            split="test" if p.split == "test" else "dev", group=p.template_id,
                            instruction=instruction_for(p), project_id=p.id, author="catalog",
                            revision=p.id))
    return out


def project_index(project_id: str) -> int:
    from slm.arch.__main__ import projects

    return [p.id for p in projects(1)].index(project_id)
