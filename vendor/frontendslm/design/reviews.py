"""Bind submitted human observations to their exact artifact; keep training eligibility separate."""
import json
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from frontendslm.io import sha256
from frontendslm.schemas import StrictModel


class HumanVisualReview(StrictModel):
    schema_version: Literal['1.0']
    candidate_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewer_declared_by_user: str = Field(min_length=1)
    submitted_at: AwareDatetime
    perceived_descriptors: list[str] = Field(min_length=1, max_length=12)
    visual_quality: int = Field(strict=True, ge=1, le=5)
    primary_action_clarity: Literal['clear', 'partly', 'unclear']
    first_action: str = Field(min_length=1)
    manual_functionality: Literal['not_tested', 'passed', 'needs_correction']
    notes: str
    status: Literal['submitted_for_validation']
    training_eligible: Literal[False]

    @field_validator('perceived_descriptors')
    @classmethod
    def nonblank_descriptors(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError('Descriptors must contain text')
        return values


def packet_path(packet: Path, name: str) -> Path:
    path = (packet / name).resolve()
    if Path(name).is_absolute() or '..' in Path(name).parts or not path.is_relative_to(packet.resolve()):
        raise ValueError('Artifact path escapes the review packet')
    return path


def validate_submission(raw: bytes, packet: Path) -> dict:
    review = HumanVisualReview.model_validate_json(raw)
    case = json.loads((packet / 'case.json').read_text())
    family, separator, variant = review.candidate_id.partition('/')
    variants = {row['variant'] for row in json.loads((packet / 'summary.json').read_text())['candidates']}
    if not separator or family != case['id'] or variant not in variants:
        raise ValueError('Review names an unknown candidate')
    manifest = json.loads((packet / 'artifact-manifest.json').read_text())
    required = {'case.json', 'summary.json', 'review.html', f'{variant}/source.json',
                f'{variant}/render/desktop.png', f'{variant}/render/mobile.png',
                f'{variant}/render/evidence.json'}
    if not required <= manifest['files'].keys():
        raise ValueError('Review packet manifest omits required provenance artifacts')
    for name, entry in manifest['files'].items():
        if sha256(packet_path(packet, name).read_bytes()) != entry['sha256']:
            raise ValueError(f'Review packet artifact changed: {name}')
    source_path = packet_path(packet, f'{variant}/source.json')
    source = json.loads(source_path.read_text())['files']['src/App.tsx']
    if sha256(source.encode()) != review.source_sha256:
        raise ValueError('Review source checksum does not match the candidate')
    return {'schema_version': '1.0', 'review_id': sha256(raw)[:16],
            'submission_sha256': sha256(raw), 'status': 'validated_visual_submission',
            'validation_scope': 'Submission schema and saved artifact integrity; not verification of reviewer identity or unobserved behavior.',
            'review': review.model_dump(mode='json'),
            'packet_manifest_sha256': sha256((packet / 'artifact-manifest.json').read_bytes()),
            'human_visual_observation_recorded': True,
            'manual_functionality': review.manual_functionality,
            'source_implementation_human_verified': False,
            'training_eligible': False,
            'limitations': ['One reviewer assessing one original assistant-authored candidate.',
                            'Exact screenshots inspected and source-code review were not recorded.',
                            'Perceived descriptors are not functionality measurements or universal style instructions.',
                            'No ratings of the controlled defects or 4B model outputs were submitted.']}


def visual_preferences(preferences: dict) -> dict:
    """Never disclose human ratings or candidate-specific feedback to a blinded scoring call."""
    keys = ('schema_version', 'user_statement', 'reference_urls', 'default_direction',
            'default_direction_origin', 'specific_brief_overrides_default', 'functionality_required')
    return {key: preferences[key] for key in keys if key in preferences}
