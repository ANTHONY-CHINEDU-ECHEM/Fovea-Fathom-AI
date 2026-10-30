"""PubMed connector using NCBI Entrez with history server batching.

Query families from ``corpus.yaml`` are searched with ``esearch`` (usehistory), and records
are fetched in batches with ``efetch`` as XML. Systematic reviews, meta analyses and randomised
trials are harvested in a priority pass so a capped run still indexes the strongest evidence.
Without an API key NCBI allows three requests per second; with one, ten.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator

from fovea.domain import Document, Licence, SourceType
from ingestion.processing.cleaner import clean
from ingestion.processing.grader import grade
from ingestion.sources.base import PoliteClient

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PRIORITY_FILTER = (
    '(systematic[sb] OR "meta-analysis"[pt] OR "randomized controlled trial"[pt] OR "practice guideline"[pt])'
)


def parse_efetch(xml_text: str) -> list[Document]:
    docs: list[Document] = []
    root = ET.fromstring(xml_text)
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        title_node = article.find(".//ArticleTitle")
        title = clean("".join(title_node.itertext())) if title_node is not None else ""
        sections: list[tuple[str, str]] = []
        for part in article.findall(".//Abstract/AbstractText"):
            label = part.get("Label") or ""
            text = clean("".join(part.itertext()))
            if text:
                sections.append((label.title(), text))
        if not sections:
            continue
        year_text = (
            article.findtext(".//JournalIssue/PubDate/Year") or article.findtext(".//ArticleDate/Year") or ""
        )
        year = int(year_text) if year_text.isdigit() else None
        types = [t.text or "" for t in article.findall(".//PublicationType")]
        journal = article.findtext(".//Journal/ISOAbbreviation") or article.findtext(".//Journal/Title") or ""
        docs.append(
            Document(
                id=f"pubmed-{pmid}",
                source=SourceType.PUBMED,
                title=title,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                text=" ".join(body for _, body in sections),
                year=year,
                jurisdiction="INT",
                licence=Licence.ABSTRACT_FAIR_DEALING,
                grade=grade(SourceType.PUBMED, types, title),
                sections=sections,
                identifiers={"pmid": pmid},
                metadata={"publication_types": types, "journal": journal},
                verification="Harvested from PubMed efetch.",
            )
        )
    return docs


class PubMedConnector:
    name = "pubmed"

    def __init__(
        self,
        families: dict[str, str],
        client: PoliteClient,
        api_key: str = "",
        email: str = "",
        batch: int = 200,
        per_family: int = 2000,
    ) -> None:
        self.families = families
        self.client = client
        self.api_key = api_key
        self.email = email
        self.batch = batch
        self.per_family = per_family

    def _params(self, **extra: object) -> dict[str, object]:
        params: dict[str, object] = {"db": "pubmed", "tool": "fovea_fathom_ai", **extra}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params

    def _search(self, term: str, limit: int) -> Iterator[Document]:
        response = self.client.get(
            f"{EUTILS}/esearch.fcgi", params=self._params(term=term, usehistory="y", retmode="json", retmax=0)
        )
        result = response.json()["esearchresult"]
        count = min(int(result["count"]), limit)
        webenv, key = result["webenv"], result["querykey"]
        for start in range(0, count, self.batch):
            fetch = self.client.get(
                f"{EUTILS}/efetch.fcgi",
                params=self._params(
                    WebEnv=webenv,
                    query_key=key,
                    retstart=start,
                    retmax=min(self.batch, count - start),
                    retmode="xml",
                ),
            )
            yield from parse_efetch(fetch.text)

    def harvest(self, limit: int | None = None) -> Iterator[Document]:
        budget = limit or self.per_family
        seen: set[str] = set()
        for family, query in self.families.items():
            for term in (f"({query}) AND {PRIORITY_FILTER}", query):
                for doc in self._search(term, budget):
                    if doc.id in seen:
                        continue
                    seen.add(doc.id)
                    doc.metadata["family"] = family
                    yield doc
