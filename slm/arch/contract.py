"""What agents must agree on, written down exactly and built only from the arm's own plan.

The swap experiment on saved projects found three separate blockers. The manager's one-line task text overrode the
required columns, the network agent wrote against columns it had never seen, and `Shell.tsx` imported paths that don't
exist. This module backs three arms that each add one fix: a shell written by code, a contract the plan can't override,
and each agent seeing the code it depends on. None of it reads the benchmark's reference code.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from slm.contracts import Artifact, ArtifactFile, ProjectPlan, Task, specialist_prompt
from slm.domains import api_base, canonical_path, detail_for

USER_COLUMNS = ("id", "email", "password_hash", "session_token", "created_at")
ENTITY_COLUMNS = ("id", "owner_id", "title", "created_at")
MAX_FILE_CHARS = 1800
MAX_CONTEXT_CHARS = 5000
FINAL_LINE = "Return only the files for your task."


def _surface(task: Task, prefix: str) -> str:
    return next(s.split(":", 1)[1] for s in task.provides() if s.startswith(prefix))


def generate_shell(plan: ProjectPlan, task: Task) -> Artifact:
    """The app shell follows directly from the plan's pages, so it needs no model."""
    pages = [t for t in plan.tasks if t.kind == "page"]
    path = canonical_path(task.domain, task.kind, task.target)
    named = [(_surface(t, "component:"), _surface(t, "route:"), PurePosixPath(canonical_path(t.domain, t.kind, t.target)).stem)
             for t in pages]
    imports = [f'import {{ {c} }} from "./{stem}";' for c, _, stem in named]
    links = [f'        <a href="{r}">{c.removesuffix("Page")}</a><br />' for c, r, _ in named]
    bodies = [f"        <{c} />" for c, _, _ in named]
    text = "\n".join([f"// {path}", *imports, "", "export function Shell() {", "  return (", "    <div>", "      <nav>",
                      *links, "      </nav>", "      <main>", *bodies, "      </main>", "    </div>", "  );", "}", ""])
    return Artifact(files=[ArtifactFile(path=path, content=text)], summary="App shell generated from the plan")


def contract_lines(task: Task) -> list[str]:
    """The exact shared facts for one task. These are the product's conventions, stated where they can't be missed."""
    target = task.target
    if task.kind == "schema":
        if target == "users":
            return ["Use exactly these columns, in this order, and no others:",
                    "id BIGSERIAL PRIMARY KEY", "email TEXT NOT NULL UNIQUE", "password_hash TEXT NOT NULL",
                    "session_token TEXT", "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"]
        return ["Use exactly these columns, in this order, and no others:",
                "id BIGSERIAL PRIMARY KEY", "owner_id BIGINT NOT NULL REFERENCES users (id)", "title TEXT NOT NULL",
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
                f"Then add: CREATE INDEX {target}_owner_idx ON {target} (owner_id);"]
    if task.kind == "rest":
        return [f"Table `{target}` has exactly these columns: {', '.join(ENTITY_COLUMNS)}. Use no others.",
                'The POST body is JSON with one field. Read it with payload.get("title") and require no other field.',
                f'POST inserts owner_id = user["id"] and title into `{target}`, with RETURNING *.',
                "Pass each SQL parameter as its own argument, such as db.fetchrow(sql, a, b), never as a tuple or list."]
    if task.kind == "session":
        return [f"Table `users` has exactly these columns: {', '.join(USER_COLUMNS)}. Use no others."]
    if task.kind in ("oauth", "guards"):
        return ["require_session(request) is async, so always await it."]
    if task.kind == "client":
        return [f'Rows from {api_base(target)} have the fields id and title. The create body is {{"title": string}}.']
    if task.kind == "page":
        return [f"Rows from {api_base(target)} have the fields id and title."]
    if task.kind == "form":
        return ['The create call sends {"title": string}, with no other field.']
    return []


def contract_prompt(plan: ProjectPlan, task: Task) -> str:
    """The specialist prompt, with the manager's free-text detail replaced so it can't contradict the contract."""
    fixed = task.model_copy(update={"detail": detail_for(task.domain, task.kind, task.target)})
    prompt = specialist_prompt(plan, fixed)
    lines = contract_lines(task)
    if not lines:
        return prompt
    block = "Contract. Follow it exactly. It overrides anything else in this prompt:\n" + "\n".join(f"- {x}" for x in lines)
    return prompt.replace(FINAL_LINE, f"{block}\n{FINAL_LINE}")


def _depends_on(plan: ProjectPlan, task: Task) -> list[str]:
    """Task ids whose code this task must fit: its plan dependencies, plus what its kind always reads."""
    reads = {"rest": (("schema", task.target), ("session", None)), "client": (("rest", task.target),),
             "form": (("client", task.target),), "page": (("rest", task.target),),
             "session": (("schema", "users"),), "oauth": (("session", None),), "guards": (("session", None),)}
    named = [t.id for t in plan.tasks for kind, target in reads.get(task.kind, ())
             if t.kind == kind and (target is None or t.target == target)]
    return list(dict.fromkeys([*named, *task.deps]))


def dependency_block(plan: ProjectPlan, task: Task, artifacts: dict[str, Artifact]) -> str:
    """The code already written that this task depends on, most relevant first, within a fixed budget."""
    parts: list[str] = []
    used = 0
    for task_id in _depends_on(plan, task):
        artifact = artifacts.get(task_id)
        for f in artifact.files if artifact else []:
            text = f.content[:MAX_FILE_CHARS]
            if used + len(text) > MAX_CONTEXT_CHARS:
                return _wrap(parts)
            used += len(text)
            parts.append(f"--- {f.path}\n{text}")
    return _wrap(parts)


def _wrap(parts: list[str]) -> str:
    return "Code your teammates already wrote. Match its names and columns exactly:\n" + "\n".join(parts) if parts else ""


def context_prompt(plan: ProjectPlan, task: Task, artifacts: dict[str, Artifact]) -> str:
    block = dependency_block(plan, task, artifacts)
    prompt = contract_prompt(plan, task)
    return prompt.replace(FINAL_LINE, f"{block}\n{FINAL_LINE}") if block else prompt
