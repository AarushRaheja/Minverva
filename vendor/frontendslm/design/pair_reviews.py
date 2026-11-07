"""Human preference records bound to two frozen model-output screenshot sets."""
import json
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from design.reviews import packet_path
from frontendslm.io import sha256
from frontendslm.schemas import StrictModel


class CandidateImpression(StrictModel):
    label: Literal['A', 'B']
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    perceived_descriptors: list[str] = Field(min_length=1, max_length=12)
    visual_quality: int | None = Field(default=None, strict=True, ge=1, le=5)

    @field_validator('perceived_descriptors')
    @classmethod
    def nonblank(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError('Descriptors must contain text')
        return values


class PairVisualReview(StrictModel):
    schema_version: Literal['pair-1.0']
    pair_id: str
    reviewer_declared_by_user: str = Field(min_length=1)
    submitted_at: AwareDatetime
    preferred: Literal['A', 'B', 'no_preference']
    reason: str = Field(min_length=1)
    impressions: list[CandidateImpression] = Field(min_length=2, max_length=2)
    manual_functionality: Literal['not_tested']
    training_eligible: Literal[False]


def validate_pair_submission(raw: bytes, packet: Path) -> dict:
    review = PairVisualReview.model_validate_json(raw)
    pair = json.loads((packet / 'pair.json').read_text())
    if review.pair_id != pair['pair_id'] or {i.label for i in review.impressions} != {'A', 'B'}:
        raise ValueError('Unknown pair or duplicate/missing candidate label')
    manifest = json.loads((packet / 'artifact-manifest.json').read_text())
    required = {'pair.json', 'review.html'} | {f'{label}/{name}' for label in ('A', 'B')
        for name in ('source.json', 'desktop.png', 'mobile.png', 'evidence.json')}
    if not required <= manifest['files'].keys():
        raise ValueError('Packet manifest omits required review evidence')
    for name, entry in manifest['files'].items():
        if sha256(packet_path(packet, name).read_bytes()) != entry['sha256']:
            raise ValueError(f'Review packet artifact changed: {name}')
    for impression in review.impressions:
        source = json.loads((packet / impression.label / 'source.json').read_text())['files']['src/App.tsx']
        expected = pair['candidates'][impression.label]['source_sha256']
        if sha256(source.encode()) != impression.source_sha256 or impression.source_sha256 != expected:
            raise ValueError('Review source checksum does not match the candidate')
    return {'review_id': sha256(raw)[:16], 'submission_sha256': sha256(raw),
        'status': 'validated_pair_visual_submission', 'review': review.model_dump(mode='json'),
        'packet_manifest_sha256': sha256((packet / 'artifact-manifest.json').read_bytes()),
        'validation_scope': 'Submission and artifact integrity; reviewer identity and observations are user-declared.',
        'manual_functionality': 'not_tested', 'human_grounding_verified': None, 'training_eligible': False,
        'limitations': ['One same-brief pair cannot establish general aesthetic superiority.',
                       'Initial screenshots support visual impressions, not manual task completion.',
                       'These evaluation-derived candidates remain excluded from training.']}
