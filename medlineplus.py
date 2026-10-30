"""MedlinePlus health topics connector (NLM web service), used for patient conversations."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator

from fovea.domain import Document, EvidenceGrade, Licence, SourceType
from ingestion.processing.cleaner import clean
from ingestion.sources.base import PoliteClient

SERVICE = "https://wsearch.nlm.nih.gov/ws/query"


def parse_topics(xml_text: str) -> list[Document]:
    docs: list[Document] = []
    root = ET.fromstring(xml_text)
    for document in root.iter("document"):
        url = document.get("url", "")
        fields = {c.get("name"): clean("".join(c.itertext())) for c in document.findall("content")}
        title = fields.get("title", "")
        summary = fields.get("FullSummary") or fields.get("snippet", "")
        if not title or not summary:
            continue
        docs.append(
            Document(
                id=f"medlineplus-{url.rstrip('/').split('/')[-1].replace('.html', '')}",
                source=SourceType.PATIENT_INFO,
                title=f"{title} (MedlinePlus)",
                url=url,
                text=summary,
                jurisdiction="US",
                licence=Licence.PUBLIC_DOMAIN,
                grade=EvidenceGrade.EXPERT_OPINION,
                sections=[("Patient information", summary)],
                identifiers={"url": url},
                verification="Harvested from the MedlinePlus web service.",
            )
        )
    return docs


class MedlinePlusConnector:
    name = "medlineplus"

    def __init__(self, topics: list[str], client: PoliteClient) -> None:
        self.topics = topics
        self.client = client

    def harvest(self, limit: int | None = None) -> Iterator[Document]:
        produced = 0
        for topic in self.topics:
            response = self.client.get(SERVICE, params={"db": "healthTopics", "term": topic, "retmax": 5})
            for doc in parse_topics(response.text):
                yield doc
                produced += 1
                if limit and produced >= limit:
                    return
