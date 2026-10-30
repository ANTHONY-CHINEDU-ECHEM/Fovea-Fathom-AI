"""Dense embedders.

* :class:`HashingEmbedder` runs offline with no model download: signed feature hashing of
  clinical tokens and character trigrams, L2 normalised. It is deterministic, which makes the
  continuous integration evaluation reproducible.
* :class:`SentenceTransformerEmbedder` wraps BGE base (or any sentence transformer) for
  production, using the instruction prefix recommended for BGE queries.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from fovea.retrieval.tokenizer import tokenize


class Embedder(Protocol):
    dim: int
    name: str

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _bucket(feature: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return value % dim, 1.0 if (value >> 63) & 1 else -1.0


class HashingEmbedder:
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = tokenize(text)
        for token in tokens:
            index, sign = _bucket("t:" + token, self.dim)
            vec[index] += sign * 1.0
            if len(token) > 5 and not token.startswith("concept_"):
                for i in range(len(token) - 2):
                    index, sign = _bucket("c:" + token[i : i + 3], self.dim)
                    vec[index] += sign * 0.25
        for left, right in zip(tokens, tokens[1:], strict=False):
            index, sign = _bucket(f"b:{left}_{right}", self.dim)
            vec[index] += sign * 0.5
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm else vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._vector(t) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


class SentenceTransformerEmbedder:
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # optional dependency

        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.name = model_name

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self.model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32,
        )

    def embed_query(self, text: str) -> np.ndarray:
        return np.asarray(
            self.model.encode(self.QUERY_PREFIX + text, normalize_embeddings=True), dtype=np.float32
        )


def build_embedder(backend: str, model_name: str, dim: int) -> Embedder:
    if backend == "sentence_transformers":
        return SentenceTransformerEmbedder(model_name)
    return HashingEmbedder(dim)
