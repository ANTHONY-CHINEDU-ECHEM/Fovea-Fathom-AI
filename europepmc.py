"""Europe PMC connector: open access full text, restricted to CC BY and CC0 licences."""

from __future__ import annotations

from collections.abc import Iterator

from fovea.domain import Document, Licence, SourceType
from ingestion.processing.cleaner import clean
from ingestion.processing.grader import grade
from ingestion.sources.base import PoliteClient

SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ALLOWED = {"cc by": Licence.CC_BY, "cc0": Licence.CC0}


def parse_result(item: dict) -> Document | None:
    licence = (item.get("license") or "").lower().replace("-", " ")
    if licence not in ALLOWED:
        return None
    abstract = clean(item.get("abstractText", ""))
    if not abstract:
        return None
    pmcid = item.get("pmcid") or item.get("id")
    title = clean(item.get("title", ""))
    year = int(item["pubYear"]) if str(item.get("pubYear", "")).isdigit() else None
    types = item.get("pubTypeList", {}).get("pubType", [])
    return Document(
        id=f"epmc-{pmcid}",
        source=SourceType.EUROPE_PMC,
        title=title,
        url=f"https://europepmc.org/article/PMC/{pmcid}"
        if str(pmcid).startswith("PMC")
        else f"https://europepmc.org/abstract/MED/{item.get('pmid', '')}",
        text=abstract,
        year=year,
        jurisdiction="INT",
        licence=ALLOWED[licence],
        grade=grade(SourceType.EUROPE_PMC, types, title),
        sections=[("Abstract", abstract)],
        identifiers={"pmcid": str(pmcid), "pmid": str(item.get("pmid", ""))},
        metadata={"publication_types": types, "journal": item.get("journalTitle", "")},
        verification="Harvested from Europe PMC REST API; licence checked.",
    )


class EuropePMCConnector:
    name = "europe_pmc"

    def __init__(self, queries: list[str], client: PoliteClient, page_size: int = 200) -> None:
        self.queries = queries
        self.client = client
        self.page_size = page_size

    def harvest(self, limit: int | None = None) -> Iterator[Document]:
        produced = 0
        for query in self.queries:
            cursor = "*"
            while True:
                response = self.client.get(
                    SEARCH,
                    params={
                        "query": f"({query}) AND OPEN_ACCESS:y",
                        "format": "json",
                        "resultType": "core",
                        "pageSize": self.page_size,
                        "cursorMark": cursor,
                    },
                )
                data = response.json()
                for item in data.get("resultList", {}).get("result", []):
                    doc = parse_result(item)
                    if doc:
                        produced += 1
                        yield doc
                        if limit and produced >= limit:
                            return
                next_cursor = data.get("nextCursorMark")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
