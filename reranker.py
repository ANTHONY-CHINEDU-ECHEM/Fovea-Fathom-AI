"""Rerankers.

* :class:`LexicalReranker` (offline): inverse document frequency weighted coverage of the
  precision query by the passage (80 percent of the score), coverage of the guideline synonyms
  added to the recall query (20 percent), and a bonus for adjacent query term pairs found in
  order. Scores fall in 0 to 1.
* :class:`CrossEncoderReranker` (production): BGE reranker base through sentence
  transformers, squashed with a logistic function so both rerankers share a scale.
"""

from __future__ import annotations

import math
from typing import Protocol

from fovea.retrieval.bm25 import BM25Index
from fovea.retrieval.tokenizer import tokenize

PRECISE_SHARE = 0.8
SYNONYM_SHARE = 0.2
BIGRAM_BONUS = 0.15


class Reranker(Protocol):
    name: str

    def score(self, precision_query: str, recall_query: str, passages: list[str]) -> list[float]: ...


class LexicalReranker:
    name = "lexical"

    def __init__(self, bm25: BM25Index) -> None:
        self.bm25 = bm25

    def score(self, precision_query: str, recall_query: str, passages: list[str]) -> list[float]:
        precise = list(dict.fromkeys(tokenize(precision_query)))
        extra = [t for t in dict.fromkeys(tokenize(recall_query)) if t not in precise]
        weights = {t: self.bm25.idf(t) for t in precise + extra}
        precise_total = sum(weights[t] for t in precise)
        extra_total = sum(weights[t] for t in extra)
        if precise_total <= 0:
            return [0.0 for _ in passages]
        pairs = list(zip(precise, precise[1:], strict=False))
        scores = []
        for passage in passages:
            tokens = tokenize(passage)
            present = set(tokens)
            value = PRECISE_SHARE * sum(weights[t] for t in precise if t in present) / precise_total
            if extra_total > 0:
                value += SYNONYM_SHARE * sum(weights[t] for t in extra if t in present) / extra_total
            if pairs:
                bigrams = set(zip(tokens, tokens[1:], strict=False))
                value += BIGRAM_BONUS * sum(1 for p in pairs if p in bigrams) / len(pairs)
            scores.append(min(1.0, value))
        return scores


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder  # optional dependency

        self.model = CrossEncoder(model_name)
        self.name = model_name

    def score(self, precision_query: str, recall_query: str, passages: list[str]) -> list[float]:
        raw = self.model.predict([(precision_query, p) for p in passages])
        return [1 / (1 + math.exp(-float(r))) for r in raw]


def build_reranker(backend: str, model_name: str, bm25: BM25Index) -> Reranker:
    if backend == "cross_encoder":
        return CrossEncoderReranker(model_name)
    return LexicalReranker(bm25)
