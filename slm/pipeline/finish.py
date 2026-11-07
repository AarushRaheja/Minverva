"""What plain code does around the specialists: write the predictable parts and check the rest.

  - Shell.tsx comes straight from the plan's pages, so no model has to get it right.
  - A page's title is set from its entity.
  - A task that fails its contract goes back to its specialist with the failure, at most twice.
"""

from __future__ import annotations

import re

from slm.bench.catalog import gold_artifact
from slm.contracts import Artifact, ArtifactFile, ProjectPlan, Task
from slm.domains import canonical_path, pascal

MAX_REPAIRS = 2


def written_by_code(task: Task) -> bool:
    return task.kind == "layout"


def code_artifact(plan: ProjectPlan, task: Task) -> Artifact:
    return gold_artifact(plan, task)


def finish_artifact(task: Task, artifact: Artifact) -> Artifact:
    """Set the page title from the entity. Every other file is returned as written."""
    if task.kind != "page":
        return artifact
    path = canonical_path(task.domain, task.kind, task.target)
    title = f"<h1>{pascal(task.target)}</h1>"
    return artifact.model_copy(update={"files": [
        ArtifactFile(path=f.path, content=re.sub(r"<h1>.*?</h1>", title, f.content)) if f.path == path else f
        for f in artifact.files]})


def repair_prompt(prompt: str, previous: str, failure: str) -> str:
    return (f"{prompt}\n\nYour previous answer failed this check: {failure}\n"
            f"Previous answer:\n{previous}\n\nReturn the corrected file as JSON.")
