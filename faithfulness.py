"""Claim support: does each cited sentence say what its sources say?

Each cited sentence is compared with the union of its cited passages. Content tokens are
weighted, with medicines, conditions, guidance numbers and numbers counted three times, and the
sentence is supported when the weighted share of its tokens found in the passages reaches the
threshold. The answer level score is the share of supported claims.
"""

from __future__ import annotations

from dataclasses import dataclass

from fovea.domain import ScoredChunk
from fovea.generation.citations import CitationReport
from fovea.retrieval.tokenizer import tokenize

HEAVY_PREFIXES = ("concept_",)
SUPPORT_THRESHOLD = 0.6


def _weight(token: str, heavy: set[str]) -> float:
    if token in heavy or any(ch.isdigit() for ch in token) or token.startswith(("ta", "ng", "nct")):
        return 3.0
    return 1.0


@dataclass
class FaithfulnessReport:
    claims: int
    supported: int
    score: float
    unsupported_sentences: list[str]


def assess(report: CitationReport, passages: list[ScoredChunk]) -> FaithfulnessReport:
    heavy: set[str] = set()
    for p in passages:
        heavy.update(p.chunk.drugs)
        heavy.update(p.chunk.conditions)
    claims = 0
    supported = 0
    unsupported: list[str] = []
    for sentence in report.sentences:
        if not sentence.factual or not sentence.citations:
            continue
        claims += 1
        tokens = [t for t in tokenize(sentence.text, concepts=False) if not t.isdigit() or len(t) > 0]
        tokens = [t for t in tokens if t not in {str(c) for c in sentence.citations}]
        if not tokens:
            supported += 1
            continue
        evidence: set[str] = set()
        for c in sentence.citations:
            if 1 <= c <= len(passages):
                chunk = passages[c - 1].chunk
                evidence.update(tokenize(f"{chunk.title} {chunk.text}", concepts=False))
        total = sum(_weight(t, heavy) for t in tokens)
        found = sum(_weight(t, heavy) for t in tokens if t in evidence)
        if total and found / total >= SUPPORT_THRESHOLD:
            supported += 1
        else:
            unsupported.append(sentence.text)
    score = supported / claims if claims else 1.0
    return FaithfulnessReport(claims, supported, round(score, 4), unsupported)
