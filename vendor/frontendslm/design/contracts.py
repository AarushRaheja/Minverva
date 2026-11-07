"""Traceable design intent and explicitly model-estimated visual quality."""
import re
from typing import Literal

from pydantic import Field, model_validator

from frontendslm.schemas import EvidenceReference, StrictModel


class DesignDecision(StrictModel):
    dimension: Literal['layout', 'typography', 'color', 'density', 'spacing', 'shape', 'motion', 'content', 'controls']
    choice: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class DescriptorInterpretation(StrictModel):
    term: str = Field(min_length=1)
    polarity: Literal['prefer', 'avoid']
    origin: Literal['explicit', 'inferred', 'default']
    source_quote: str
    meaning_in_context: str
    decisions: list[DesignDecision] = Field(min_length=1, max_length=4)


class DesignIntent(StrictModel):
    schema_version: Literal['1.0']
    primary_user_goal: str
    audience: list[str]
    interpretations: list[DescriptorInterpretation] = Field(min_length=1, max_length=4)
    layout: Literal['workspace', 'focus', 'editorial', 'storefront']
    density: Literal['compact', 'comfortable', 'spacious']
    typography: Literal['modern', 'humanist', 'editorial', 'technical']
    palette: Literal['neutral', 'warm', 'cool']
    accent: Literal['indigo', 'blue', 'teal', 'amber', 'rose']
    theme: Literal['light', 'dark']
    primary_action: str
    information_hierarchy: list[str] = Field(min_length=2, max_length=6)
    ux_priorities: list[str] = Field(min_length=2, max_length=5)
    avoid: list[str]
    assumptions: list[str]
    unresolved_descriptors: list[str]
    clarifying_questions: list[str] = Field(max_length=1)


def validate_intent_provenance(intent: DesignIntent, source_text: str) -> list[str]:
    errors = []
    for interpretation in intent.interpretations:
        if interpretation.origin == 'explicit' and (not interpretation.source_quote or interpretation.source_quote.casefold() not in source_text.casefold()):
            errors.append(f'Explicit descriptor lacks a real source quote: {interpretation.term}')
    if intent.unresolved_descriptors and not intent.clarifying_questions:
        errors.append('Unresolved descriptors require a concise clarification question')
    if explicitly_undefined(source_text) and not intent.unresolved_descriptors:
        errors.append('The user explicitly declared an undefined descriptor; clarification is required')
    return errors


def explicitly_undefined(text: str) -> bool:
    """Recognize a declared lack of definition, not a universal novelty detector."""
    return bool(re.search(r'\bno definition (?:is )?(?:provided|given)|\bundefined (?:private |team |design )?(?:term|descriptor)', text, re.IGNORECASE))


class VisualScore(StrictModel):
    score: int = Field(ge=0, le=5)
    reason: str = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=2)

    @model_validator(mode='after')
    def screenshots_only(self):
        if any(ref.type != 'screenshot' for ref in self.evidence):
            raise ValueError('Visual scores must cite visible screenshot regions')
        return self


class VisualScores(StrictModel):
    hierarchy: VisualScore
    typography: VisualScore
    spacing_alignment: VisualScore
    color_restraint: VisualScore
    composition_coherence: VisualScore
    responsive_composition: VisualScore
    intent_alignment: VisualScore


class VisualImprovement(StrictModel):
    priority: Literal['major', 'minor']
    observation: str
    recommendation: str
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=2)


class VisualAssessment(StrictModel):
    schema_version: Literal['1.0']
    assessment_kind: Literal['model_estimate_not_human_preference']
    scores: VisualScores
    perceived_descriptors: list[str] = Field(min_length=3, max_length=5)
    primary_action_visible: bool
    primary_action_description: str
    improvements: list[VisualImprovement] = Field(max_length=4)
    uncertainties: list[str]
    summary: str


def visual_result(assessment: VisualAssessment, supplied_images: set[str]) -> dict:
    weights = {'hierarchy': .20, 'typography': .15, 'spacing_alignment': .15, 'color_restraint': .10,
               'composition_coherence': .20, 'responsive_composition': .10, 'intent_alignment': .10}
    scores = assessment.scores.model_dump()
    refs = [ref for score in scores.values() for ref in score['evidence']]
    refs += [ref.model_dump() for issue in assessment.improvements for ref in issue.evidence]
    errors = [f'Unknown screenshot {ref["ref"]}' for ref in refs if ref['type'] != 'screenshot' or ref['ref'] not in supplied_images]
    total = round(sum(weights[key] * score['score'] * 20 for key, score in scores.items()), 1)
    return {'visual_quality_proxy': total, 'minimum_dimension': min(s['score'] for s in scores.values()),
            'reference_valid': not errors, 'errors': errors, 'human_preference': None,
            'primary_action_visible': assessment.primary_action_visible,
            'major_visual_issues': sum(i.priority == 'major' for i in assessment.improvements),
            'interpretation': 'Model-estimated visual rubric, not measured human beauty or task usability.'}
