"""The contract every agent meets. The evaluator only needs standard inputs, observable actions and final outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

COMPLETED = "completed"
BUDGET_EXHAUSTED = "budget_exhausted"
CRASHED = "crashed"
UNSUPPORTED = "unsupported"  # the agent cannot attempt this kind of task: reported, never scored as a coding failure
ENVIRONMENT_FAILURE = "environment_failure"  # the backend or harness failed: censored and retryable
CENSORED = (UNSUPPORTED, ENVIRONMENT_FAILURE)


@dataclass
class Task:
    task_id: str
    instruction: str
    workspace_path: str
    artifacts_path: str  # where the adapter writes its trajectory and metrics; outside the workspace
    family: str = "repo"  # repo | project_build
    project_id: str | None = None
    reference_path: str | None = None  # only the oracle control ever reads this


@dataclass
class Budget:
    name: str
    max_steps: int
    wall_time_seconds: int
    max_cost_usd: float | None = None


@dataclass
class AgentResult:
    task_id: str
    patch_path: str | None  # the orchestrator fills this in: agents don't report their own submission
    status: str
    trajectory_path: str
    metrics_path: str
    detail: str = ""


class CodingAgent(Protocol):
    def run(self, task: Task, budget: Budget) -> AgentResult: ...
