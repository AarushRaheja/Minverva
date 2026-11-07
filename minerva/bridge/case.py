"""Turn the contract into the case dict FrontEndSLM's Architect, repair loop and Critic read."""

from __future__ import annotations

from minerva.bridge.contract import AppContract, render_api_client
from minerva.bridge.tests import CompiledTests


def test_id_summary(contract: AppContract) -> list[str]:
    out = ["sign-out: control that calls signOut(); always visible"]
    for e in contract.entities:
        out += [
            f"nav-{e.tid}: always-visible control that shows {e.label}; no hamburger menu",
            f"{e.tid}-list: wrapper around the {e.label} rows; visible while {e.label} is showing",
            f"{e.tid}-row: on each {e.label} row, repeated once per row, and only while {e.label} is showing",
            f"{e.tid}-title-input: labelled text input for a new row's title",
            f"{e.tid}-submit: button that creates the row and shows it in the list without a page reload",
            f"{e.tid}-form-error: message shown when the title is empty; absent otherwise",
        ]
    return out


def build_case(contract: AppContract, tests: CompiledTests, run_id: str, design_intent: dict | None = None) -> dict:
    """`tests` are the VISIBLE tests. The bound ones never go in the prompt."""
    labels = [e.label for e in contract.entities]
    case = {
        "id": "frontend",
        "contract_profile": "fullstack",
        "api_contract": render_api_client(contract),
        "spec": {
            "project_id": run_id,
            "application_type": contract.name,
            "user_goal": contract.brief,
            "audience": ["signed-in users of this application"],
            "style": {"requested_look": contract.look} if contract.look else {},
            "sections": labels,
            "interactions": [{"id": f"create-{e.tid}", "action": f"Create a row in {e.label} from its title",
                              "expected": "The row is saved by the server and appears in the list"}
                             for e in contract.entities],
            "acceptance_criteria": [
                "Every required data-testid exists and every interaction test passes on desktop and mobile.",
                "Rows come from the server through ./api, including after a reload.",
                "Loading, empty and error states are all handled.",
            ],
            "constraints": {"framework": "react", "language": "typescript", "styling": "tailwind",
                            "responsive": True, "accessibility_target": "WCAG 2.2 AA",
                            "data": "real server data through ./api only"},
            "unspecified_requirements": ["editing rows", "deleting rows", "fields other than title",
                                         "payments", "real-time data", "file uploads"],
            "required_test_ids": test_id_summary(contract),
            "entity_slugs": [contract.primary.slug, *(e.slug for e in contract.entities if e != contract.primary)],
        },
        "tests": tests.visible,
    }
    if design_intent:
        case["design_intent"] = design_intent
    return case
