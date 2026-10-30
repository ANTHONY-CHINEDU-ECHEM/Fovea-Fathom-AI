"""Registry prefilter for ClinicalTrials.gov records.

Filters indexed registry records by condition, intervention, recruitment status, age, sex and
UK sites. The prefilter narrows the list for a conversation with the trial team; eligibility
is always decided by the trial protocol and the investigators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fovea.clinical import ToolCard

OPEN_STATUSES = {"RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}


@dataclass
class TrialRecord:
    nct: str
    title: str
    url: str
    conditions: list[str] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)
    status: str = "UNKNOWN"
    status_verified: bool = False
    phase: str = ""
    min_age: int | None = None
    max_age: int | None = None
    sex: str = "ALL"
    uk_sites: bool | None = None

    @classmethod
    def from_metadata(
        cls, doc_id: str, title: str, url: str, conditions: list[str], drugs: list[str], meta: dict[str, Any]
    ) -> TrialRecord:
        return cls(
            nct=meta.get("nct", doc_id),
            title=title,
            url=url,
            conditions=conditions,
            drugs=drugs,
            status=str(meta.get("status", "UNKNOWN")).upper(),
            status_verified=bool(meta.get("status_verified", False)),
            phase=str(meta.get("phase", "")),
            min_age=meta.get("min_age"),
            max_age=meta.get("max_age"),
            sex=str(meta.get("sex", "ALL")).upper(),
            uk_sites=meta.get("uk_sites"),
        )


def prefilter(
    records: list[TrialRecord],
    condition: str | None,
    age: int | None = None,
    sex: str | None = None,
    drug: str | None = None,
    open_only: bool = True,
    uk_only: bool = False,
) -> ToolCard:
    card = ToolCard(
        tool="trials",
        title="Clinical trial registry prefilter",
        summary="",
        provenance="ClinicalTrials.gov API version 2 records in the index",
        references=["ClinicalTrials.gov"],
    )
    kept: list[dict[str, Any]] = []
    for rec in records:
        reasons: list[str] = []
        if condition and condition not in rec.conditions:
            continue
        if drug and rec.drugs and drug not in rec.drugs:
            continue
        if open_only and rec.status_verified and rec.status not in OPEN_STATUSES:
            continue
        if age is not None:
            if rec.min_age is not None and age < rec.min_age:
                continue
            if rec.max_age is not None and age > rec.max_age:
                continue
        if sex and rec.sex not in {"ALL", sex.upper()}:
            continue
        if uk_only and rec.uk_sites is False:
            continue
        if not rec.status_verified:
            reasons.append("recruitment status not verified in this snapshot; refresh the registry records")
        if rec.uk_sites is None:
            reasons.append("UK sites not confirmed")
        kept.append(
            {
                "nct": rec.nct,
                "title": rec.title,
                "url": rec.url,
                "status": rec.status,
                "phase": rec.phase,
                "cautions": reasons,
            }
        )
    card.details = {
        "trials": kept,
        "filters": {"condition": condition, "age": age, "sex": sex, "drug": drug, "open_only": open_only},
    }
    if kept:
        card.summary = f"{len(kept)} registry record(s) pass the prefilter for {condition.replace('_', ' ') if condition else 'the question'}."
    else:
        card.summary = "No indexed registry record passes the prefilter."
    card.warn(
        "info",
        "This is a registry prefilter. Eligibility is decided by the trial team against the full protocol.",
    )
    if any(t["cautions"] for t in kept):
        card.warn(
            "caution",
            "Some records carry no verified recruitment status; check the registry before referral.",
        )
    return card
