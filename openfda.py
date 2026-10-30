"""openFDA drug label connector.

Only safety and pharmacology sections are indexed. Dosage sections are deliberately never
indexed, so a US dose can never be retrieved and presented as UK guidance.
"""

from __future__ import annotations

from collections.abc import Iterator

from fovea.domain import Document, EvidenceGrade, Licence, SourceType
from ingestion.processing.cleaner import clean
from ingestion.sources.base import PoliteClient

LABELS = "https://api.fda.gov/drug/label.json"
SECTIONS = {
    "boxed_warning": "Boxed warning",
    "contraindications": "Contraindications",
    "warnings_and_cautions": "Warnings and precautions",
    "warnings": "Warnings",
    "drug_interactions": "Drug interactions",
    "use_in_specific_populations": "Use in specific populations",
    "pregnancy": "Pregnancy",
    "adverse_reactions": "Adverse reactions",
}
NEVER_INDEXED = {"dosage_and_administration", "dosage_forms_and_strengths", "how_supplied"}


def parse_label(generic: str, result: dict) -> Document | None:
    sections = []
    for key, heading in SECTIONS.items():
        values = result.get(key) or []
        text = clean(" ".join(values))
        if text:
            sections.append((heading, text[:6000]))
    if not sections:
        return None
    version = result.get("effective_time", "")
    return Document(
        id=f"openfda-{generic.replace(' ', '-')}-{result.get('set_id', '')[:8]}",
        source=SourceType.DRUG_LABEL,
        title=f"{generic.capitalize()}: US structured product label (safety sections)",
        url=f"{LABELS}?search=openfda.generic_name:{generic.replace(' ', '+')}",
        text=" ".join(body for _, body in sections),
        year=int(version[:4]) if version[:4].isdigit() else None,
        jurisdiction="US",
        licence=Licence.PUBLIC_DOMAIN,
        grade=EvidenceGrade.OBSERVATIONAL_OR_REGULATORY,
        sections=sections,
        drugs=[generic],
        identifiers={"set_id": result.get("set_id", "")},
        verification="Harvested from openFDA; dosage sections excluded.",
    )


class OpenFDAConnector:
    name = "openfda"

    def __init__(self, drugs: list[str], client: PoliteClient) -> None:
        self.drugs = drugs
        self.client = client

    def harvest(self, limit: int | None = None) -> Iterator[Document]:
        produced = 0
        for generic in self.drugs:
            response = self.client.get(
                LABELS, params={"search": f'openfda.generic_name:"{generic}"', "limit": 1}
            )
            for result in response.json().get("results", []):
                doc = parse_label(generic, result)
                if doc:
                    yield doc
                    produced += 1
                    if limit and produced >= limit:
                        return
