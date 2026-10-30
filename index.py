"""The knowledge index: chunks, BM25, dense vectors, reranker and build manifest."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from fovea.clinical.trials import TrialRecord
from fovea.config import Settings
from fovea.domain import Chunk, Document, SourceType
from fovea.retrieval.bm25 import BM25Index
from fovea.retrieval.embedders import Embedder, build_embedder
from fovea.retrieval.reranker import Reranker, build_reranker
from fovea.retrieval.vector_store import MemoryVectorStore, QdrantVectorStore, VectorStore


def _payload(chunk: Chunk) -> dict[str, Any]:
    return {
        "doc_id": chunk.doc_id,
        "source": chunk.source.value,
        "jurisdiction": chunk.jurisdiction,
        "grade": int(chunk.grade),
        "year": chunk.year,
        "conditions": chunk.conditions,
        "drugs": chunk.drugs,
        "superseded": chunk.superseded,
    }


class KnowledgeIndex:
    def __init__(self, settings: Settings, embedder: Embedder | None = None) -> None:
        self.settings = settings
        self.embedder = embedder or build_embedder(
            settings.embedding_backend, settings.embedding_model, settings.embedding_dim
        )
        self.chunks: dict[str, Chunk] = {}
        self.bm25 = BM25Index()
        self.store: VectorStore = self._new_store()
        self.reranker: Reranker = build_reranker(
            settings.reranker_backend, settings.reranker_model, self.bm25
        )
        self.trials: list[TrialRecord] = []
        self.manifest: dict[str, Any] = {}

    def _new_store(self) -> VectorStore:
        if self.settings.vector_backend == "qdrant":
            return QdrantVectorStore(
                self.settings.qdrant_url, self.settings.qdrant_collection, self.embedder.dim
            )
        return MemoryVectorStore(self.embedder.dim)

    def __len__(self) -> int:
        return len(self.chunks)

    # Building --------------------------------------------------------------------------
    def build(
        self, chunks: list[Chunk], documents: list[Document] | None = None, batch_size: int = 256
    ) -> dict[str, Any]:
        started = time.time()
        for chunk in chunks:
            self.chunks[chunk.id] = chunk
        self.bm25.add([(c.id, f"{c.title}. {c.section}. {c.text}") for c in chunks])
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self.embedder.embed_documents([f"{c.title}. {c.section}. {c.text}" for c in batch])
            self.store.upsert([c.id for c in batch], vectors, [_payload(c) for c in batch])
        if documents:
            self.trials = [
                TrialRecord.from_metadata(
                    d.id,
                    d.title,
                    d.url,
                    d.conditions,
                    d.drugs,
                    {**d.metadata, "nct": d.identifiers.get("nct", d.id)},
                )
                for d in documents
                if d.source == SourceType.CLINICAL_TRIAL
            ]
        self.manifest = self._manifest(chunks, documents or [], time.time() - started)
        return self.manifest

    def _manifest(self, chunks: list[Chunk], documents: list[Document], seconds: float) -> dict[str, Any]:
        return {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "chunks": len(self.chunks),
            "documents": len({c.doc_id for c in self.chunks.values()}),
            "by_source": dict(Counter(c.source.value for c in self.chunks.values())),
            "by_licence": dict(Counter(c.licence.value for c in self.chunks.values())),
            "by_grade": {
                str(k): v for k, v in sorted(Counter(int(c.grade) for c in self.chunks.values()).items())
            },
            "superseded_chunks": sum(1 for c in self.chunks.values() if c.superseded),
            "trials": len(self.trials),
            "embedder": self.embedder.name,
            "reranker": self.reranker.name,
            "vector_backend": self.settings.vector_backend,
            "build_seconds": round(seconds, 2),
        }

    # Searching -------------------------------------------------------------------------
    def dense_search(
        self, query: str, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[str, float]]:
        vector = self.embedder.embed_query(query)
        return [
            (cid, s) for cid, s in self.store.search(np.asarray(vector), top_k, filters) if cid in self.chunks
        ]

    def sparse_search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        return self.bm25.search(query, top_k)

    def matches(self, chunk_id: str, filters: dict[str, Any]) -> bool:
        from fovea.retrieval.vector_store import _passes

        chunk = self.chunks.get(chunk_id)
        return chunk is not None and _passes(_payload(chunk), filters)

    def ids_mentioning(self, identifier: str) -> list[str]:
        needle = identifier.lower()
        return [
            cid
            for cid, c in self.chunks.items()
            if needle in c.doc_id.lower() or needle in c.title.lower() or needle in c.text.lower()
        ][:6]

    # Persistence -----------------------------------------------------------------------
    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "chunks.jsonl").open("w", encoding="utf-8") as handle:
            for chunk in self.chunks.values():
                handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
        self.bm25.save(directory / "bm25.json")
        if isinstance(self.store, MemoryVectorStore):
            self.store.save(directory)
        (directory / "trials.json").write_text(
            json.dumps([t.__dict__ for t in self.trials], indent=1), encoding="utf-8"
        )
        (directory / "manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path, settings: Settings) -> KnowledgeIndex:
        index = cls(settings)
        with (directory / "chunks.jsonl").open("r", encoding="utf-8") as handle:
            for line in handle:
                chunk = Chunk.from_dict(json.loads(line))
                index.chunks[chunk.id] = chunk
        index.bm25 = BM25Index.load(directory / "bm25.json")
        index.reranker = build_reranker(settings.reranker_backend, settings.reranker_model, index.bm25)
        if settings.vector_backend == "memory":
            index.store = MemoryVectorStore.load(
                directory, {cid: _payload(c) for cid, c in index.chunks.items()}
            )
        trials_path = directory / "trials.json"
        if trials_path.exists():
            index.trials = [TrialRecord(**t) for t in json.loads(trials_path.read_text(encoding="utf-8"))]
        manifest_path = directory / "manifest.json"
        index.manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        )
        return index

    @staticmethod
    def exists(directory: Path) -> bool:
        return (directory / "chunks.jsonl").exists() and (directory / "bm25.json").exists()
