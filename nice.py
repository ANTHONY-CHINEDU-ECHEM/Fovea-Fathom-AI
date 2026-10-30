"""NICE Syndication API connector.

NICE content may be stored and redistributed only under a NICE syndication licence. With a
key, guidance and appraisal content is harvested through the syndication API; without one the
index keeps only the verified seed summaries, written in our own words with links to NICE.
Parsing is isolated in :func:`parse_guidance` so a change to the API format affects one function.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fovea.domain import Document, EvidenceGrade, Licence, SourceType
from ingestion.processing.cleaner import clean
from ingestion.sources.base import PoliteClient

API = "https://api.nice.org.uk/services/content"


def parse_guidance(guidance_id: str, payload: dict[str, Any]) -> Document | None:
    chapters = payload.get("chapters") or payload.get("Chapters") or []
    sections: list[tuple[str, str]] = []
    for chapter in chapters:
        heading = clean(chapter.get("title") or chapter.get("Title") or "")
        body = clean(chapter.get("content") or chapter.get("Content") or "")
        if body:
            sections.append((heading, body))
    if not sections:
        return None
    title = clean(payload.get("title") or payload.get("Title") or guidance_id)
    published = str(payload.get("publishedDate") or payload.get("PublishedDate") or "")
    source = SourceType.NICE_TA if guidance_id.upper().startswith("TA") else SourceType.NICE_GUIDELINE
    return Document(
        id=f"nice-{guidance_id.lower()}",
        source=source,
        title=title,
        url=f"https://www.nice.org.uk/guidance/{guidance_id.lower()}",
        text=" ".join(body for _, body in sections),
        year=int(published[:4]) if published[:4].isdigit() else None,
        published=published or None,
        jurisdiction="UK",
        licence=Licence.NICE_SYNDICATION,
        grade=EvidenceGrade.UK_NATIONAL_GUIDANCE,
        sections=sections,
        identifiers={"guidance": guidance_id.upper()},
        verification="Harvested from the NICE Syndication API under licence.",
    )


class NICEConnector:
    name = "nice"

    def __init__(self, guidance_ids: list[str], client: PoliteClient, api_key: str) -> None:
        self.guidance_ids = guidance_ids
        self.client = client
        self.api_key = api_key

    def harvest(self, limit: int | None = None) -> Iterator[Document]:
        if not self.api_key:
            return
        headers = {
            "API-Key": self.api_key,
            "Accept": "application/vnd.nice.syndication.guidance+json;version=1.0",
        }
        for count, gid in enumerate(self.guidance_ids, start=1):
            response = self.client.get(f"{API}/{gid.lower()}", headers=headers)
            doc = parse_guidance(gid, response.json())
            if doc:
                yield doc
            if limit and count >= limit:
                return
