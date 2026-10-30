"""ClinicalTrials.gov API version 2 connector with page token paging."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from fovea.domain import Document, EvidenceGrade, Licence, SourceType
from ingestion.processing.cleaner import clean
from ingestion.processing.tagger import tag_text
from ingestion.sources.base import PoliteClient

STUDIES = "https://clinicaltrials.gov/api/v2/studies"


def _age(value: str | None) -> int | None:
    if not value:
        return None
    m = re.match(r"(\d+)\s*(Year|Month|Week|Day)", value, re.I)
    if not m:
        return None
    number, unit = int(m.group(1)), m.group(2).lower()
    return number if unit == "year" else 0


def parse_study(study: dict[str, Any]) -> Document:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    desc = proto.get("descriptionModule", {})
    elig = proto.get("eligibilityModule", {})
    design = proto.get("designModule", {})
    conds = proto.get("conditionsModule", {}).get("conditions", [])
    arms = proto.get("armsInterventionsModule", {}).get("interventions", [])
    locations = proto.get("contactsLocationsModule", {}).get("locations", [])
    nct = ident.get("nctId", "")
    summary = clean(desc.get("briefSummary", ""))
    eligibility = clean(elig.get("eligibilityCriteria", ""))
    interventions = ", ".join(i.get("name", "") for i in arms)
    sections = [("Summary", summary)]
    if interventions:
        sections.append(("Interventions", f"Interventions: {interventions}. Conditions: {', '.join(conds)}."))
    if eligibility:
        sections.append(("Eligibility", eligibility[:3000]))
    start = status.get("startDateStruct", {}).get("date", "")
    text = " ".join(body for _, body in sections)
    return Document(
        id=f"ctgov-{nct.lower()}",
        source=SourceType.CLINICAL_TRIAL,
        title=clean(ident.get("officialTitle") or ident.get("briefTitle", "")),
        url=f"https://clinicaltrials.gov/study/{nct}",
        text=text,
        year=int(start[:4]) if start[:4].isdigit() else None,
        jurisdiction="INT",
        licence=Licence.PUBLIC_DOMAIN,
        grade=EvidenceGrade.EXPERT_OPINION,
        sections=sections,
        conditions=tag_text(" ".join(conds) + " " + ident.get("briefTitle", ""), "condition"),
        drugs=tag_text(interventions, "drug"),
        identifiers={"nct": nct},
        metadata={
            "nct": nct,
            "status": status.get("overallStatus", "UNKNOWN"),
            "status_verified": True,
            "phase": ",".join(design.get("phases", [])),
            "min_age": _age(elig.get("minimumAge")),
            "max_age": _age(elig.get("maximumAge")),
            "sex": elig.get("sex", "ALL"),
            "uk_sites": any(loc.get("country") == "United Kingdom" for loc in locations)
            if locations
            else None,
        },
        verification="Harvested from ClinicalTrials.gov API version 2.",
    )


class ClinicalTrialsConnector:
    name = "clinicaltrials_gov"

    def __init__(self, conditions: list[str], client: PoliteClient, page_size: int = 100) -> None:
        self.conditions = conditions
        self.client = client
        self.page_size = page_size

    def harvest(self, limit: int | None = None) -> Iterator[Document]:
        produced = 0
        for condition in self.conditions:
            token: str | None = None
            while True:
                params: dict[str, Any] = {
                    "query.cond": condition,
                    "pageSize": self.page_size,
                    "format": "json",
                }
                if token:
                    params["pageToken"] = token
                data = self.client.get(STUDIES, params=params).json()
                for study in data.get("studies", []):
                    yield parse_study(study)
                    produced += 1
                    if limit and produced >= limit:
                        return
                token = data.get("nextPageToken")
                if not token:
                    break
