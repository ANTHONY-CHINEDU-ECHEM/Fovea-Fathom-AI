"""Ingestion pipeline: harvest, checkpoint, clean, tag, deduplicate, apply currency, chunk, index.

Raw harvested records are checkpointed to JSONL per source so an interrupted harvest resumes
where it stopped. The seed snapshot is always merged in, so curated UK guidance summaries
remain in the index alongside harvested content.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import yaml

from fovea.config import DATA_DIR, REPO_ROOT, SEED_DIR, Settings
from fovea.domain import Chunk, Document
from fovea.retrieval.index import KnowledgeIndex
from ingestion.processing import currency
from ingestion.processing.chunker import chunk_document
from ingestion.processing.dedup import deduplicate
from ingestion.processing.tagger import tag_document

log = logging.getLogger(__name__)
CORPUS = REPO_ROOT / "ingestion" / "config" / "corpus.yaml"
RAW_DIR = DATA_DIR / "raw"


def load_seed(directory: Path = SEED_DIR) -> list[Document]:
    docs: list[Document] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            docs.extend(Document.from_dict(json.loads(line)) for line in handle if line.strip())
    return docs


def load_corpus_config(path: Path = CORPUS) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def checkpoint(name: str, documents: Iterable[Document], directory: Path = RAW_DIR) -> Iterator[Document]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for doc in documents:
            handle.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")
            yield doc


def read_checkpoints(directory: Path = RAW_DIR) -> list[Document]:
    docs: list[Document] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    docs.append(Document.from_dict(json.loads(line)))
                except (ValueError, KeyError):
                    continue
    return docs


def process(documents: list[Document]) -> tuple[list[Document], list[Chunk], dict[str, Any]]:
    started = time.time()
    tagged = [tag_document(d) for d in documents]
    unique, removed = deduplicate(tagged)
    superseded = currency.apply(unique)
    chunks = [c for d in unique for c in chunk_document(d)]
    stats = {
        "documents_in": len(documents),
        "duplicates_removed": removed,
        "documents_kept": len(unique),
        "superseded_documents": superseded,
        "chunks": len(chunks),
        "seconds": round(time.time() - started, 2),
    }
    return unique, chunks, stats


def build_index(
    settings: Settings, documents: list[Document], out_dir: Path | None = None
) -> tuple[KnowledgeIndex, dict[str, Any]]:
    docs, chunks, stats = process(documents)
    index = KnowledgeIndex(settings)
    manifest = index.build(chunks, docs)
    manifest["processing"] = stats
    manifest["verification"] = {d.id: d.verification for d in docs if d.verification}
    index.manifest = manifest
    index.save(Path(out_dir or settings.index_dir))
    return index, manifest


def harvest_all(settings: Settings, quick: bool = False, only: list[str] | None = None) -> list[Document]:
    from ingestion.sources.base import Connector, PoliteClient
    from ingestion.sources.clinicaltrials import ClinicalTrialsConnector
    from ingestion.sources.europepmc import EuropePMCConnector
    from ingestion.sources.medlineplus import MedlinePlusConnector
    from ingestion.sources.nice import NICEConnector
    from ingestion.sources.openfda import OpenFDAConnector
    from ingestion.sources.pubmed import PubMedConnector

    cfg = load_corpus_config()
    ncbi_rate = 9.0 if settings.ncbi_api_key else 2.5
    connectors: dict[str, Connector] = {
        "nice": NICEConnector(cfg["nice_guidance"], PoliteClient(1.0), settings.nice_api_key),
        "pubmed": PubMedConnector(
            cfg["pubmed_query_families"],
            PoliteClient(ncbi_rate),
            settings.ncbi_api_key,
            settings.ncbi_email,
            per_family=200 if quick else 2000,
        ),
        "europe_pmc": EuropePMCConnector(cfg["europe_pmc_queries"], PoliteClient(5.0)),
        "clinicaltrials_gov": ClinicalTrialsConnector(cfg["clinicaltrials_conditions"], PoliteClient(3.0)),
        "openfda": OpenFDAConnector(cfg["openfda_drugs"], PoliteClient(3.0)),
        "medlineplus": MedlinePlusConnector(cfg["medlineplus_topics"], PoliteClient(1.0)),
    }
    limit = 100 if quick else None
    harvested: list[Document] = []
    for name, connector in connectors.items():
        if only and name not in only:
            continue
        log.info("harvesting %s", name)
        try:
            harvested.extend(checkpoint(name, connector.harvest(limit)))
        except Exception as exc:  # one failing source must not stop the others
            log.error("source %s failed: %s", name, exc)
    return harvested
