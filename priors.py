"""Clinical priors that scale relevance by provenance and clinical scope.

Priors multiply the reranker score rather than add to it, so provenance alone never lifts an
irrelevant passage. The boost combines:

* evidence grade on the seven step ladder
* recency, for research evidence only, with a configurable half life
* a UK jurisdiction bonus
* condition match or conflict: DMO evidence is promoted for a DMO question and demoted for a
  wet AMD question
* medicine match or conflict for named agents
* a penalty for superseded guidance
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fovea.config import Settings
from fovea.domain import Chunk, SourceType

RESEARCH = {SourceType.PUBMED, SourceType.EUROPE_PMC, SourceType.CLINICAL_TRIAL}
CURRENT_YEAR = 2026


@dataclass
class PriorResult:
    factor: float
    reasons: list[str] = field(default_factory=list)


def compute(chunk: Chunk, conditions: list[str], drugs: list[str], settings: Settings) -> PriorResult:
    reasons: list[str] = []
    factor = 1.0 + settings.evidence_weight * (int(chunk.grade) - 1) / 6
    reasons.append(f"grade {int(chunk.grade)}")

    if chunk.source in RESEARCH and chunk.year:
        age = max(0, CURRENT_YEAR - chunk.year)
        recency = 0.6 + 0.4 * 0.5 ** (age / settings.recency_half_life_years)
        factor *= recency
        reasons.append(f"recency {recency:.2f}")
    if chunk.jurisdiction == "UK":
        factor *= 1 + settings.uk_bonus
        reasons.append("UK")

    if conditions and chunk.conditions:
        if set(conditions) & set(chunk.conditions):
            factor *= 1 + settings.condition_bonus
            reasons.append("condition match")
        else:
            factor /= 1 + settings.condition_bonus
            reasons.append("condition conflict")
    if drugs and chunk.drugs:
        if set(drugs) & set(chunk.drugs):
            factor *= 1 + settings.drug_bonus
            reasons.append("medicine match")
        elif not set(drugs) <= {"aspirin", "warfarin", "apixaban", "tamsulosin"}:
            factor /= 1 + settings.drug_bonus / 2
            reasons.append("different medicine")
    if chunk.superseded:
        factor *= settings.superseded_factor
        reasons.append(f"superseded by {chunk.superseded_by}")
    return PriorResult(factor, reasons)
