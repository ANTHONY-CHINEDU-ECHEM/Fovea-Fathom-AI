"""Core domain model shared by ingestion, retrieval, generation and the API.

The model deliberately separates three things that general purpose assistants blur:

* **Provenance**: every document carries its source, licence, jurisdiction, evidence grade,
  publication year, a link to the authoritative text and how the record was verified.
* **Clinical scope**: every chunk carries the eye conditions, medicines and interventions it
  concerns, so evidence for one condition is never presented as evidence for another.
* **Laterality**: patient context is held per eye, because almost every ophthalmic decision
  is made for one eye at a time.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SourceType(str, Enum):
    NICE_GUIDELINE = "nice_guideline"
    NICE_TA = "nice_technology_appraisal"
    UK_SCREENING = "uk_screening_programme"
    COLLEGE_GUIDANCE = "college_guidance"
    PUBMED = "pubmed"
    EUROPE_PMC = "europe_pmc"
    CLINICAL_TRIAL = "clinicaltrials_gov"
    DRUG_LABEL = "openfda_label"
    PATIENT_INFO = "patient_information"
    NEI = "national_eye_institute"

    @property
    def label(self) -> str:
        return _SOURCE_LABELS[self]


_SOURCE_LABELS = {
    SourceType.NICE_GUIDELINE: "NICE guideline",
    SourceType.NICE_TA: "NICE technology appraisal",
    SourceType.UK_SCREENING: "NHS screening programme guidance",
    SourceType.COLLEGE_GUIDANCE: "Royal College of Ophthalmologists guidance",
    SourceType.PUBMED: "PubMed abstract",
    SourceType.EUROPE_PMC: "Europe PMC open access article",
    SourceType.CLINICAL_TRIAL: "ClinicalTrials.gov registry record",
    SourceType.DRUG_LABEL: "US structured product label",
    SourceType.PATIENT_INFO: "MedlinePlus patient information",
    SourceType.NEI: "National Eye Institute information",
}


class Licence(str, Enum):
    NICE_SYNDICATION = "nice_syndication"
    NICE_SUMMARY = "summary_in_own_words_with_link"
    OPEN_GOVERNMENT = "ogl_v3"
    PUBLIC_DOMAIN = "us_public_domain"
    CC_BY = "cc_by"
    CC0 = "cc0"
    ABSTRACT_FAIR_DEALING = "abstract_fair_dealing"
    LINK_ONLY = "link_only"


class EvidenceGrade(IntEnum):
    """Seven step ladder used for ranking and display. Higher is stronger."""

    EXPERT_OPINION = 1
    CASE_SERIES = 2
    OBSERVATIONAL_OR_REGULATORY = 3
    RANDOMISED_TRIAL = 4
    SYSTEMATIC_REVIEW = 5
    INTERNATIONAL_GUIDANCE = 6
    UK_NATIONAL_GUIDANCE = 7

    @property
    def label(self) -> str:
        return {
            1: "Expert opinion, narrative review or registry entry",
            2: "Case report or series",
            3: "Observational, early phase or regulatory",
            4: "Randomised controlled trial",
            5: "Systematic review or meta analysis",
            6: "International or professional body guidance",
            7: "UK national guidance",
        }[int(self)]


@dataclass
class Document:
    """A whole source record before chunking."""

    id: str
    source: SourceType
    title: str
    url: str
    text: str
    year: int | None = None
    published: str | None = None
    jurisdiction: str = "INT"
    licence: Licence = Licence.LINK_ONLY
    grade: EvidenceGrade = EvidenceGrade.EXPERT_OPINION
    sections: list[tuple[str, str]] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)
    interventions: list[str] = field(default_factory=list)
    identifiers: dict[str, str] = field(default_factory=dict)
    superseded_by: str | None = None
    verification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint_text(self) -> str:
        return f"{self.title}\n{self.text}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.value
        data["licence"] = self.licence.value
        data["grade"] = int(self.grade)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        payload = dict(data)
        payload["source"] = SourceType(payload["source"])
        payload["licence"] = Licence(payload.get("licence", Licence.LINK_ONLY.value))
        payload["grade"] = EvidenceGrade(int(payload.get("grade", 1)))
        payload["sections"] = [tuple(s) for s in payload.get("sections", [])]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class Chunk:
    """A retrievable passage with the provenance and clinical scope of its parent document."""

    id: str
    doc_id: str
    text: str
    title: str
    url: str
    source: SourceType
    section: str = ""
    year: int | None = None
    jurisdiction: str = "INT"
    licence: Licence = Licence.LINK_ONLY
    grade: EvidenceGrade = EvidenceGrade.EXPERT_OPINION
    conditions: list[str] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)
    interventions: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    position: int = 0

    @property
    def superseded(self) -> bool:
        return bool(self.superseded_by)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.value
        data["licence"] = self.licence.value
        data["grade"] = int(self.grade)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        payload = dict(data)
        payload["source"] = SourceType(payload["source"])
        payload["licence"] = Licence(payload.get("licence", Licence.LINK_ONLY.value))
        payload["grade"] = EvidenceGrade(int(payload.get("grade", 1)))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


def stable_id(*parts: str, length: int = 16) -> str:
    digest = hashlib.sha256("␟".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    rerank_score: float = 0.0
    prior: float = 1.0
    reasons: list[str] = field(default_factory=list)


# Patient context ---------------------------------------------------------------------------

Laterality = Literal["right", "left"]
LensStatus = Literal["phakic", "pseudophakic", "aphakic", "unknown"]


class VisualFieldPoint(BaseModel):
    years_from_baseline: float = Field(ge=0, le=60)
    mean_deviation_db: float = Field(ge=-35, le=5)


class EyeContext(BaseModel):
    """De identified findings for one eye."""

    diagnosis: str | None = None
    bcva: str | None = Field(
        default=None, description="Snellen 6/x or 20/x, logMAR, ETDRS letters, CF, HM, PL or NPL"
    )
    lens_status: LensStatus = "unknown"
    iop_mmhg: float | None = Field(default=None, ge=0, le=80)
    baseline_iop_mmhg: float | None = Field(default=None, ge=0, le=80)
    cct_um: float | None = Field(default=None, ge=300, le=800)
    central_subfield_thickness_um: float | None = Field(default=None, ge=100, le=1500)
    intraretinal_fluid: bool | None = None
    subretinal_fluid: bool | None = None
    new_haemorrhage: bool | None = None
    lesion_disc_areas: float | None = Field(default=None, ge=0, le=50)
    permanent_foveal_damage: bool | None = None
    recent_progression: bool | None = None
    glaucoma_stage: Literal["early", "moderate", "advanced", "unknown"] = "unknown"
    current_agent: str | None = None
    current_interval_weeks: float | None = Field(default=None, ge=0, le=52)
    injections_given: int | None = Field(default=None, ge=0, le=500)
    visual_fields: list[VisualFieldPoint] = Field(default_factory=list)


class PatientContext(BaseModel):
    """De identified clinical context. Free text fields are redacted before use."""

    age: int | None = Field(default=None, ge=0, le=120)
    sex: Literal["female", "male", "other", "unknown"] = "unknown"
    weight_kg: float | None = Field(default=None, ge=20, le=350)
    egfr: float | None = Field(default=None, ge=0, le=200)
    diabetes: Literal["type1", "type2", "none", "unknown"] = "unknown"
    pregnant: bool | None = None
    conditions: list[str] = Field(default_factory=list)
    medicines: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    right: EyeContext | None = None
    left: EyeContext | None = None

    @field_validator("conditions", "medicines", "allergies")
    @classmethod
    def _strip(cls, value: list[str]) -> list[str]:
        return [v.strip() for v in value if v and v.strip()]

    def eye(self, side: Laterality) -> EyeContext | None:
        return self.right if side == "right" else self.left

    def eyes(self) -> list[tuple[Laterality, EyeContext]]:
        out: list[tuple[Laterality, EyeContext]] = []
        if self.right is not None:
            out.append(("right", self.right))
        if self.left is not None:
            out.append(("left", self.left))
        return out

    def is_empty(self) -> bool:
        return self == PatientContext()
