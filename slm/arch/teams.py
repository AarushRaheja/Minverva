"""Team shapes: how many primary agents split the work, and each agent's system prompt.

All prompts are rendered from slm/specialists.py, so every team sees the same conventions; only the
split differs. G4 is exactly the production specialists (contracts.specialist_system).

  G1  one generalist does every task
  G2  backend (database + auth + network) and frontend
  G4  database, auth, network, frontend      (the current architecture)
  G9  one agent per task kind                (schema, session, oauth, guards, rest, client, page, form, layout)
"""

from __future__ import annotations

from functools import cache

from slm.contracts import DOMAINS, Task, specialist_system
from slm.specialists import REPLY_FORMAT, SPECIALISTS, _generic

TEAMS = ("G1", "G2", "G4", "G9")
BACKEND = ("database", "auth", "network")


def agent_for(team: str, task: Task) -> str:
    if team == "G1":
        return "generalist"
    if team == "G2":
        return "backend" if task.domain in BACKEND else "frontend"
    if team == "G4":
        return task.domain
    if team == "G9":
        return f"{task.domain}-{task.kind}"
    raise ValueError(f"unknown team {team!r}")


def agents(team: str) -> list[str]:
    if team == "G1":
        return ["generalist"]
    if team == "G2":
        return ["backend", "frontend"]
    if team == "G4":
        return list(DOMAINS)
    return [f"{d}-{k.kind}" for d in DOMAINS for k in SPECIALISTS[d].kinds]


def _scope(team: str, agent: str) -> list[tuple[str, str]]:
    """(domain, kind) pairs an agent owns."""
    every = [(d, k.kind) for d in DOMAINS for k in SPECIALISTS[d].kinds]
    if team == "G1":
        return every
    if team == "G2":
        doms = BACKEND if agent == "backend" else ("frontend",)
        return [(d, k) for d, k in every if d in doms]
    if team == "G4":
        return [(d, k) for d, k in every if d == agent]
    d, k = agent.split("-", 1)
    return [(d, k)]


def minimal_system(domain: str, kind: str) -> str:
    """Only what one kind of task needs. No reply format, so this suits schema-constrained backends only."""
    s = SPECIALISTS[domain]
    k = next(x for x in s.kinds if x.kind == kind)
    imports = f" May import: {'; '.join(s.shared)}." if s.shared else ""
    conv = "; ".join(_generic(c) for c in k.conventions)
    return f"Write {s.language}: {k.builds}.{imports} {conv}. Use every token listed, in the file at the path given."


@cache
def system_for(team: str, agent: str) -> str:
    """System prompt for one agent of a team. G4 returns the production specialist prompt verbatim."""
    if team == "G4":
        return specialist_system(agent)
    scope = _scope(team, agent)
    doms = [d for d in DOMAINS if any(sd == d for sd, _ in scope)]
    name = {"G1": "the only engineer", "G2": f"the {agent} engineer"}.get(team, f"the {agent} specialist")
    others = [d for d in DOMAINS if d not in doms]
    lines = [f"You are {name} on a software team building fastapi+react+postgres projects."]
    for d in doms:
        s = SPECIALISTS[d]
        lines.append(f"{d}: {s.mission} You write {s.language}.")
        if s.shared:
            lines.append(f"{d} code may import: " + "; ".join(s.shared) + ".")
        for k in s.kinds:
            if (d, k.kind) in scope:
                conv = "; ".join(_generic(c) for c in k.conventions)
                lines.append(f"[{d}/{k.kind}] {k.builds}. Reads {_generic(k.reads)}; exports "
                             f"{_generic(k.writes)}. {conv}.")
    if others:
        lines.append("Teammates own: " + ", ".join(others) + ". Do not write their files.")
    lines.append("Build exactly the task(s) you are given, at the paths given, using every interface "
                 "token listed. " + REPLY_FORMAT)
    return "\n".join(lines)
