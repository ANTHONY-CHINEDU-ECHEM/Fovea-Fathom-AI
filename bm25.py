"""Okapi BM25 over the clinical tokenizer, with persistence to JSON."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from fovea.retrieval.tokenizer import tokenize


class BM25Index:
    def __init__(self, k1: float = 1.4, b: float = 0.72) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self.doc_len: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.avg_len = 0.0

    def __len__(self) -> int:
        return len(self.doc_ids)

    def add(self, items: list[tuple[str, str]]) -> None:
        for chunk_id, text in items:
            tokens = tokenize(text)
            position = len(self.doc_ids)
            self.doc_ids.append(chunk_id)
            self.doc_len.append(len(tokens))
            for term, freq in Counter(tokens).items():
                self.postings[term].append((position, freq))
        self.avg_len = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0

    def idf(self, term: str) -> float:
        n = len(self.doc_ids)
        df = len(self.postings.get(term, ()))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 40) -> list[tuple[str, float]]:
        if not self.doc_ids:
            return []
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self.idf(term)
            for position, freq in postings:
                norm = self.k1 * (1 - self.b + self.b * self.doc_len[position] / (self.avg_len or 1))
                scores[position] += idf * freq * (self.k1 + 1) / (freq + norm)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [(self.doc_ids[p], s) for p, s in ranked]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "k1": self.k1,
            "b": self.b,
            "doc_ids": self.doc_ids,
            "doc_len": self.doc_len,
            "postings": {t: p for t, p in self.postings.items()},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        data = json.loads(path.read_text(encoding="utf-8"))
        index = cls(data["k1"], data["b"])
        index.doc_ids = data["doc_ids"]
        index.doc_len = data["doc_len"]
        index.postings = defaultdict(list, {t: [tuple(x) for x in p] for t, p in data["postings"].items()})
        index.avg_len = sum(index.doc_len) / len(index.doc_len) if index.doc_len else 0.0
        return index
