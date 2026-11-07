"""What each engine is, where it sends data, what it costs, and whether it can run here.

UIs read this through `minerva engines --json` instead of hard-coding engines or prices, so a new engine (for
example a fully local one) appears in them without UI changes. Availability is checked from this machine only:
no network call is made.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Estimated $ per stage call on Modal (GPU time at list price). The budget check in pipeline.Ledger uses these
# before each call; modal_apps/pipeline_app.ModalEngine reads them from here.
MODAL_STAGE_USD = {"plan": 0.35, "backend": 0.05, "intent": 0.06, "critic": 0.06, "audit": 0.02}
MODAL_ARCHITECT_USD = {"thinking": 0.30, "instruct": 0.08}


@dataclass
class EngineInfo:
    name: str
    label: str
    data_goes_to: str  # one line a person can read before starting a run
    leaves_machine: bool
    costs_money: bool
    available: bool
    why: str  # why it is unavailable, or what it needs
    stage_usd: dict = field(default_factory=dict)

    def estimate_total(self, max_repairs: int = 1, architect: str = "thinking") -> float:
        """Upper estimate for one build: every frontend round runs, and the Critic runs once.

        Includes the preflight and verify sandbox audits, which the Ledger does not count against the budget.
        """
        if not self.costs_money:
            return 0.0
        s = self.stage_usd
        rounds = max_repairs + 1
        architect_usd = s.get(f"architect:{architect}", 0.0)
        return round(s["plan"] + s["backend"] + s["intent"] + rounds * (architect_usd + s["audit"]) + s["critic"]
                     + 2 * s["audit"], 2)


def _missing_offline() -> list[str]:
    missing = []
    if not (ROOT / "harness" / "node_modules").is_dir():
        missing.append("npm ci in harness/")
    if not (ROOT / "templates" / "frontend" / "node_modules").is_dir():
        missing.append("npm ci in templates/frontend/")
    for tool in ("initdb", "pg_ctl", "psql") if not os.environ.get("AUDIT_PG_BIN") else ():
        if shutil.which(tool) is None:
            missing.append(f"{tool} on PATH")
    for tool in ("node", "npm", "uv"):
        if shutil.which(tool) is None:
            missing.append(f"{tool} on PATH")
    return missing


def _modal_ready() -> tuple[bool, str]:
    if importlib.util.find_spec("modal") is None:
        return False, "the modal package is not installed (uv sync installs the dev group)"
    if os.environ.get("MODAL_TOKEN_ID") or (Path.home() / ".modal.toml").exists():
        return True, "uses your Modal account and the slm-vol volume"
    return False, "no Modal token: run `uv run modal token new`"


def engines() -> list[EngineInfo]:
    missing = _missing_offline()
    modal_ok, modal_why = _modal_ready()
    stage_usd = {**MODAL_STAGE_USD, **{f"architect:{k}": v for k, v in MODAL_ARCHITECT_USD.items()}}
    return [
        EngineInfo(
            name="offline", label="Offline fixtures (no models)",
            data_goes_to="nowhere: gold fixtures and an audit on this machine; the brief only picks a template",
            leaves_machine=False, costs_money=False, available=not missing,
            why="needs " + ", ".join(missing) if missing else "free; tests the plumbing, not the models"),
        EngineInfo(
            name="modal", label="Real models on Modal",
            data_goes_to="your Modal account: open-weight models on rented GPUs; no third-party model API",
            leaves_machine=True, costs_money=True, available=modal_ok, why=modal_why, stage_usd=stage_usd),
    ]


def as_json(max_repairs: int = 1, architect: str = "thinking") -> list[dict]:
    """Each engine, its estimate for these options, and `estimates[architect][max_repairs]` for every option, so a UI
    can show the cost of any choice without its own copy of the formula."""
    return [{**asdict(e), "estimate_total_usd": e.estimate_total(max_repairs, architect),
             "estimates": {a: [e.estimate_total(r, a) for r in range(4)] for a in MODAL_ARCHITECT_USD}}
            for e in engines()]
