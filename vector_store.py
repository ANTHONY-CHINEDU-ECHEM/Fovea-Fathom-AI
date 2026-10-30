"""Vector stores: an in memory numpy store and a Qdrant adapter with payload indexes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import numpy as np


class VectorStore(Protocol):
    def upsert(self, ids: list[str], vectors: np.ndarray, payloads: list[dict[str, Any]]) -> None: ...

    def search(
        self, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[str, float]]: ...

    def count(self) -> int: ...


def _passes(payload: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for key, wanted in filters.items():
        value = payload.get(key)
        if isinstance(wanted, (list, tuple, set)):
            if isinstance(value, list):
                if not set(value) & set(wanted):
                    return False
            elif value not in wanted:
                return False
        elif key.startswith("min_"):
            field = key[4:]
            if payload.get(field) is None or payload[field] < wanted:
                return False
        elif value != wanted:
            return False
    return True


class MemoryVectorStore:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.ids: list[str] = []
        self.payloads: list[dict[str, Any]] = []
        self.matrix = np.zeros((0, dim), dtype=np.float32)

    def upsert(self, ids: list[str], vectors: np.ndarray, payloads: list[dict[str, Any]]) -> None:
        if len(ids) == 0:
            return
        existing = {cid: i for i, cid in enumerate(self.ids)}
        new_rows, new_ids, new_payloads = [], [], []
        for cid, vec, payload in zip(ids, vectors, payloads, strict=True):
            if cid in existing:
                self.matrix[existing[cid]] = vec
                self.payloads[existing[cid]] = payload
            else:
                new_rows.append(vec)
                new_ids.append(cid)
                new_payloads.append(payload)
        if new_rows:
            self.matrix = np.vstack([self.matrix, np.asarray(new_rows, dtype=np.float32)])
            self.ids.extend(new_ids)
            self.payloads.extend(new_payloads)

    def search(
        self, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        scores = self.matrix @ vector.astype(np.float32)
        order = np.argsort(-scores)
        out: list[tuple[str, float]] = []
        for i in order:
            if _passes(self.payloads[i], filters):
                out.append((self.ids[i], float(scores[i])))
                if len(out) >= top_k:
                    break
        return out

    def count(self) -> int:
        return len(self.ids)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.matrix)
        (directory / "vector_ids.json").write_text(json.dumps(self.ids), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path, payloads: dict[str, dict[str, Any]]) -> MemoryVectorStore:
        matrix = np.load(directory / "vectors.npy")
        store = cls(int(matrix.shape[1]))
        store.matrix = matrix.astype(np.float32)
        store.ids = json.loads((directory / "vector_ids.json").read_text(encoding="utf-8"))
        store.payloads = [payloads.get(i, {}) for i in store.ids]
        return store


class QdrantVectorStore:
    """Qdrant adapter. Payload indexes cover the fields used by filters and priors."""

    INDEXED = ("source", "jurisdiction", "grade", "year", "conditions", "drugs")

    def __init__(self, url: str, collection: str, dim: int) -> None:
        from qdrant_client import QdrantClient  # optional dependency
        from qdrant_client.http import models

        self.models = models
        self.client = QdrantClient(url=url)
        self.collection = collection
        self.dim = dim
        names = {c.name for c in self.client.get_collections().collections}
        if collection not in names:
            self.client.create_collection(
                collection, vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE)
            )
            for field in self.INDEXED:
                schema = (
                    models.PayloadSchemaType.INTEGER
                    if field in {"grade", "year"}
                    else models.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(collection, field_name=field, field_schema=schema)

    @staticmethod
    def _point_id(chunk_id: str) -> int:
        return int(chunk_id[:15], 16)

    def upsert(self, ids: list[str], vectors: np.ndarray, payloads: list[dict[str, Any]]) -> None:
        points = [
            self.models.PointStruct(
                id=self._point_id(cid), vector=vec.tolist(), payload={**payload, "chunk_id": cid}
            )
            for cid, vec, payload in zip(ids, vectors, payloads, strict=True)
        ]
        for start in range(0, len(points), 256):
            self.client.upsert(self.collection, points=points[start : start + 256])

    def search(
        self, vector: np.ndarray, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[tuple[str, float]]:
        must = []
        for key, wanted in (filters or {}).items():
            if key.startswith("min_"):
                must.append(self.models.FieldCondition(key=key[4:], range=self.models.Range(gte=wanted)))
            elif isinstance(wanted, (list, tuple, set)):
                must.append(self.models.FieldCondition(key=key, match=self.models.MatchAny(any=list(wanted))))
            else:
                must.append(self.models.FieldCondition(key=key, match=self.models.MatchValue(value=wanted)))
        query_filter = self.models.Filter(must=must) if must else None
        hits = self.client.search(
            self.collection, query_vector=vector.tolist(), limit=top_k, query_filter=query_filter
        )
        return [(h.payload["chunk_id"], float(h.score)) for h in hits]

    def count(self) -> int:
        return int(self.client.count(self.collection).count)
