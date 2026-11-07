"""The pipeline with no models: gold backend artifacts, the reference UI, and the audit on this machine.

It proves the plumbing and costs nothing. It says nothing about what the models can do, and it ignores the brief's
content beyond picking a template.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from minerva.bridge.contract import contract_from_plan
from minerva.bridge.reference_ui import render_reference_ui
from minerva.integrator.assemble import HOST_KINDS
from minerva.verify.audit import LocalAuditor
from slm.bench.catalog import TRAIN_TEMPLATES, build_plan, gold_artifacts
from slm.manager.spec import gold_spec, to_plan, without_oauth_plan, ProjectSpec


class OfflineEngine:
    name = "offline"

    def __init__(self, ui: Callable[[str, dict], str] | None = None):
        self.ui = ui  # (source, job) -> source; lets tests inject a broken UI into the loop
        self.audit_runner = LocalAuditor(trusted=True)

    def cost_estimate(self, stage: str) -> float:
        return 0.0

    def plan(self, brief: str) -> dict:
        index = int(hashlib.sha256(brief.encode()).hexdigest(), 16) % len(TRAIN_TEMPLATES)
        plan = without_oauth_plan(build_plan(TRAIN_TEMPLATES[index]))
        return {"spec": gold_spec(plan).model_dump_json(), "seconds": 0.0, "usd": 0.0}

    def backend(self, spec_json: str, brief: str) -> dict:
        plan = to_plan(ProjectSpec.model_validate_json(spec_json))
        artifacts = {k: v.model_dump_json() for k, v in gold_artifacts(plan).items()
                     if plan.task(k).kind not in HOST_KINDS}
        return {"artifacts": artifacts, "failing": [], "seconds": 0.0, "usd": 0.0}

    def intent(self, brief: str, look: str) -> dict:
        return {"intent": None, "questions": [], "error": "offline: no model", "seconds": 0.0, "usd": 0.0}

    def _contract(self, job: dict):
        from minerva.bridge.contract import AppContract, Entity  # noqa: F401

        spec = job["spec"]
        entities = tuple(Entity(s) for s in spec["entity_slugs"])
        return AppContract(name=spec["application_type"], brief=spec["user_goal"], entities=entities, primary=entities[0],
                           look=spec["style"].get("requested_look", ""))

    def architect(self, job: dict, run_key: str) -> dict:
        from frontendslm.generation import component_manifest

        source = render_reference_ui(self._contract(job))
        if self.ui is not None:
            source = self.ui(source, job)
        return {"manifest": component_manifest(source).model_dump(), "error": None, "seconds": 0.0, "usd": 0.0,
                "output_tokens": 0}

    def critic(self, case: dict, evidence_dir: Path, run_key: str) -> dict | None:
        # No Critic model here, so nothing is accepted on its authority.
        return {"effective_verdict": "uncertain", "schema_valid": False, "error": "offline: no model", "usd": 0.0}

    def audit(self, files: dict[str, str], task: dict, out_dir: Path) -> dict:
        return self.audit_runner(files, task, out_dir)
