"""Versioned contracts. Unknown requirements and unmeasured quality stay explicit."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Interaction(StrictModel):
    id: str
    action: str
    expected: str


class Step(StrictModel):
    action: Literal["click", "fill", "select", "press", "expect_visible", "expect_hidden", "expect_text", "expect_count"]
    test_id: str
    value: str = ""


class InteractionTest(StrictModel):
    id: str
    steps: list[Step] = Field(min_length=1)


class Specification(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    application_type: str
    user_goal: str
    audience: list[str]
    style: dict[str, str]
    sections: list[str]
    interactions: list[Interaction]
    acceptance_criteria: list[str]
    constraints: dict[str, str | bool] = Field(default_factory=lambda: {
        "framework": "react", "language": "typescript", "styling": "tailwind",
        "responsive": True, "accessibility_target": "WCAG 2.2 AA", "data": "local demonstration only",
    })
    unspecified_requirements: list[str] = Field(default_factory=lambda: [
        "authentication", "backend integrations", "payments", "real-time data",
    ])


class BenchmarkCase(StrictModel):
    id: str
    category: str
    design_family: str
    difficulty: Literal["simple", "intermediate", "advanced"]
    split: Literal["evaluation"] = "evaluation"
    provenance: str = "Original benchmark authored for FrontEndSLM; never promote to training."
    spec: Specification
    tests: list[InteractionTest] = Field(min_length=1)


class SourceManifest(StrictModel):
    design_tokens: dict
    component_tree: list[str]
    files: dict[str, str]

    @model_validator(mode="after")
    def validate_files(self):
        allowed = {"src/App.tsx", "src/index.css"}
        if set(self.files) != allowed:
            raise ValueError(f"Only and exactly {sorted(allowed)} may be generated")
        if any(not value.strip() for value in self.files.values()):
            raise ValueError("Empty source file")
        if sum(len(value.encode()) for value in self.files.values()) > 120_000:
            raise ValueError("Source manifest exceeds 120KB")
        return self


class EvidenceReference(StrictModel):
    type: Literal["screenshot", "test", "build", "runtime", "accessibility", "overflow"]
    ref: str
    region: list[float] | None = None

    @model_validator(mode="after")
    def validate_region(self):
        if self.type == "screenshot" and self.region is None:
            raise ValueError("Visual claims need normalized bounding boxes")
        if self.region is not None:
            if len(self.region) != 4 or not all(0 <= n <= 1 for n in self.region):
                raise ValueError("Expected normalized [x1,y1,x2,y2]")
            x1, y1, x2, y2 = self.region
            if x1 >= x2 or y1 >= y2:
                raise ValueError("Region must have positive area")
        return self


class Issue(StrictModel):
    id: str
    category: Literal["visual_hierarchy", "typography", "spacing", "color", "responsive", "interaction", "accessibility", "prompt_adherence", "content_consistency", "runtime"]
    severity: Literal["blocker", "major", "minor", "cosmetic"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference] = Field(min_length=1)
    observation: str
    recommendation: str
    acceptance_test: str


class ContentReview(StrictModel):
    test_ref: str
    screen_quote: str
    comparison: str
    status: Literal['consistent', 'contradicted', 'no_related_claim', 'unknown']


class Critique(StrictModel):
    schema_version: Literal["1.0"]
    content_reviews: list[ContentReview] = Field(default_factory=list)
    verdict: Literal["accept", "revise", "uncertain"]
    issues: list[Issue]
    uncertainties: list[str]
    summary: str


def validate_critique_references(critique: Critique, evidence: dict) -> list[dict]:
    """Check reference existence, NOT whether a visual claim is true."""
    known = {(r["type"], r["ref"]) for r in evidence.get("references", [])}
    results = []
    for issue in critique.issues:
        errors = [f"Unknown evidence: {ref.type}/{ref.ref}" for ref in issue.evidence if (ref.type, ref.ref) not in known]
        if issue.category == "interaction" and not any(r.type == "test" for r in issue.evidence):
            errors.append("Interaction claims require measured test evidence")
        results.append({"issue_id": issue.id, "reference_valid": not errors, "errors": errors,
                        "human_grounding_verified": None})
    return results
