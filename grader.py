"""Evidence grading on the seven step ladder."""

from __future__ import annotations

from fovea.domain import EvidenceGrade, SourceType

_PUBLICATION_TYPES = [
    ({"systematic review", "meta-analysis", "meta analysis"}, EvidenceGrade.SYSTEMATIC_REVIEW),
    (
        {"practice guideline", "guideline", "consensus development conference"},
        EvidenceGrade.INTERNATIONAL_GUIDANCE,
    ),
    (
        {
            "randomized controlled trial",
            "clinical trial, phase iii",
            "clinical trial, phase iv",
            "pragmatic clinical trial",
        },
        EvidenceGrade.RANDOMISED_TRIAL,
    ),
    (
        {
            "clinical trial, phase ii",
            "clinical trial, phase i",
            "observational study",
            "comparative study",
            "multicenter study",
            "cohort",
        },
        EvidenceGrade.OBSERVATIONAL_OR_REGULATORY,
    ),
    ({"case reports", "case series"}, EvidenceGrade.CASE_SERIES),
    ({"review", "editorial", "comment", "letter"}, EvidenceGrade.EXPERT_OPINION),
]


def grade(source: SourceType, publication_types: list[str] | None = None, title: str = "") -> EvidenceGrade:
    if source in {SourceType.NICE_GUIDELINE, SourceType.NICE_TA, SourceType.UK_SCREENING}:
        return EvidenceGrade.UK_NATIONAL_GUIDANCE
    if source == SourceType.COLLEGE_GUIDANCE:
        return EvidenceGrade.INTERNATIONAL_GUIDANCE
    if source == SourceType.DRUG_LABEL:
        return EvidenceGrade.OBSERVATIONAL_OR_REGULATORY
    if source in {SourceType.CLINICAL_TRIAL, SourceType.PATIENT_INFO, SourceType.NEI}:
        return EvidenceGrade.EXPERT_OPINION
    types = {t.lower() for t in (publication_types or [])}
    lowered = title.lower()
    for keys, value in _PUBLICATION_TYPES:
        if types & keys:
            return value
    if "systematic review" in lowered or "meta-analysis" in lowered or "meta analysis" in lowered:
        return EvidenceGrade.SYSTEMATIC_REVIEW
    if "randomized" in lowered or "randomised" in lowered:
        return EvidenceGrade.RANDOMISED_TRIAL
    return EvidenceGrade.OBSERVATIONAL_OR_REGULATORY
