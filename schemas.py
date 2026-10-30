"""Request and response schemas for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from fovea.domain import PatientContext, VisualFieldPoint


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    context: PatientContext = Field(default_factory=PatientContext)
    provider: Literal["anthropic", "openai", "ollama", "extractive"] | None = None
    in_scope_conversation: bool = False
    source_types: list[str] | None = Field(
        default=None, description="Restrict retrieval to these source types"
    )
    min_grade: int | None = Field(default=None, ge=1, le=7)
    jurisdiction: Literal["UK", "US", "INT"] | None = None

    def filters(self) -> dict[str, Any] | None:
        filters: dict[str, Any] = {}
        if self.source_types:
            filters["source"] = self.source_types
        if self.min_grade:
            filters["min_grade"] = self.min_grade
        if self.jurisdiction:
            filters["jurisdiction"] = self.jurisdiction
        return filters or None


class AskResponse(BaseModel):
    meta: dict[str, Any]
    emergencies: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    final: dict[str, Any]
    cached: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    source_types: list[str] | None = None
    min_grade: int | None = Field(default=None, ge=1, le=7)
    jurisdiction: Literal["UK", "US", "INT"] | None = None


class AcuityRequest(BaseModel):
    value: str = Field(description="Snellen, logMAR, ETDRS letters, decimal, CF, HM, PL or NPL")
    eye: Literal["right", "left"] | None = None


class BiometryRequest(BaseModel):
    axial_length_mm: float = Field(ge=18, le=35)
    k1_d: float = Field(ge=35, le=55)
    k2_d: float = Field(ge=35, le=55)
    a_constant: float = Field(default=118.4, ge=110, le=122)
    target_refraction_d: float = Field(default=0.0, ge=-10, le=4)
    fellow_axial_length_mm: float | None = Field(default=None, ge=18, le=35)
    fellow_mean_k_d: float | None = Field(default=None, ge=35, le=55)
    eye: Literal["right", "left"] | None = None


class GradingRequest(BaseModel):
    features: dict[str, Any] = Field(
        description="Feature flags such as irma, new_vessels_disc, exudate_within_1dd, best_va"
    )
    eye: Literal["right", "left"] | None = None


class TreatExtendRequest(BaseModel):
    agent: str
    condition: Literal["wet_amd", "dmo", "rvo", "myopic_cnv"]
    injections_given: int = Field(ge=0, le=500)
    current_interval_weeks: float | None = Field(default=None, ge=0, le=52)
    intraretinal_fluid: bool = False
    subretinal_fluid: bool = False
    new_haemorrhage: bool = False
    letters_lost: int = Field(default=0, ge=0, le=100)
    intraocular_inflammation: bool = False
    consecutive_dry_at_max: int = Field(default=0, ge=0, le=50)
    eye: Literal["right", "left"] | None = None


class GlaucomaRequest(BaseModel):
    iop_mmhg: float | None = Field(default=None, gt=0, le=80)
    baseline_iop_mmhg: float | None = Field(default=None, ge=5, le=80)
    cct_um: float | None = Field(default=None, ge=300, le=800)
    stage: Literal["early", "moderate", "advanced", "unknown"] = "unknown"
    pigment_dispersion: bool = False
    visual_fields: list[VisualFieldPoint] = Field(default_factory=list)
    age: int | None = Field(default=None, ge=0, le=120)
    eye: Literal["right", "left"] | None = None


class HCQRequest(BaseModel):
    weight_kg: float = Field(ge=20, le=350)
    daily_dose_mg: float = Field(gt=0, le=1000)
    years_on_treatment: float = Field(ge=0, le=60)
    drug: Literal["hydroxychloroquine", "chloroquine"] = "hydroxychloroquine"
    tamoxifen: bool = False
    egfr: float | None = Field(default=None, ge=0, le=200)


class TherapyRequest(BaseModel):
    condition: str
    context: PatientContext = Field(default_factory=PatientContext)
    eye: Literal["right", "left"] = "right"
    subtype: Literal["crvo", "brvo"] | None = None
    prior_failure: str | None = None
    pigment_dispersion: bool = False


class ScreenRequest(BaseModel):
    planned: list[str] = Field(min_length=1)
    context: PatientContext = Field(default_factory=PatientContext)
    extra_conditions: list[str] = Field(default_factory=list)


class TrialsRequest(BaseModel):
    condition: str | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    sex: Literal["female", "male"] | None = None
    drug: str | None = None
    open_only: bool = True
    uk_only: bool = False


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
    rating: Literal[-1, 1]
    reasons: list[str] = Field(default_factory=list)
    comment: str | None = Field(default=None, max_length=2000)
