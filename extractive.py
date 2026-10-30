"""Extractive generator: the final fallback, which copies cited sentences from the sources.

Sentences are scored by weighted overlap with the question, sentences from passages whose
conditions conflict with the question are skipped, and each chosen sentence carries the
number of its source. Because sentences are copied verbatim, every figure is supported by
construction; the generator is therefore safe to use when no model is reachable.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from fovea.clinical.understanding import Understanding
from fovea.domain import ScoredChunk
from fovea.generation.citations import split_sentences
from fovea.retrieval.bm25 import BM25Index
from fovea.retrieval.tokenizer import STOPWORDS, tokenize

MAX_SENTENCES = 5
RELATIVE_FLOOR = 0.45
ANCHOR_MIN_IDF = 2.0
ANCHOR_WEIGHT = 0.8
CLOSING = "Clinical judgement: confirm against the full guidance, the SmPC, the local protocol and the patient's own findings before acting."


def _anchors(precise: set[str], bm25: BM25Index) -> dict[str, float]:
    """The rarest specific terms of the question (trial acronyms, guidance numbers, rare drugs)."""
    ranked = sorted(((bm25.idf(t), t) for t in precise if not t.startswith("concept_")), reverse=True)
    if not ranked:
        return {}
    ceiling = ranked[0][0]
    return {t: idf for idf, t in ranked[:3] if idf >= max(ANCHOR_MIN_IDF, 0.75 * ceiling)}


def compose(u: Understanding, passages: list[ScoredChunk], bm25: BM25Index) -> str:
    precise = {t for t in tokenize(u.precision_query) if t not in STOPWORDS}
    query = [t for t in dict.fromkeys(tokenize(u.recall_query)) if t not in STOPWORDS]
    weights = {t: bm25.idf(t) * (1.0 if t in precise else 0.4) for t in query}
    anchors = _anchors(precise, bm25)
    best = passages[0].score if passages else 0.0
    candidates: list[tuple[float, int, int, str]] = []
    for rank, item in enumerate(passages, start=1):
        c = item.chunk
        if u.conditions and c.conditions and not set(u.conditions) & set(c.conditions):
            continue
        passage_tokens = set(tokenize(f"{c.title} {c.section} {c.text}"))
        anchor_credit = sum(idf for t, idf in anchors.items() if t in passage_tokens)
        if anchors and not anchor_credit and item.score < RELATIVE_FLOOR * best:
            continue
        if not anchors and item.score < RELATIVE_FLOOR * best:
            continue
        for position, sentence in enumerate(split_sentences(c.text)):
            if len(sentence.split()) < 6:
                continue
            tokens = set(tokenize(sentence))
            if not tokens & precise and not anchor_credit:
                continue
            overlap = sum(w for t, w in weights.items() if t in tokens) + ANCHOR_WEIGHT * anchor_credit
            if overlap <= 0:
                continue
            score = overlap**1.5 * item.score**0.5 / (1 + 0.05 * position) / (1 + 0.05 * (rank - 1))
            candidates.append((score, rank, position, sentence))
    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for _, rank, position, sentence in candidates:
        key = re.sub(r"\W+", " ", sentence.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        chosen.append((rank, position, sentence))
        if len(chosen) >= MAX_SENTENCES:
            break
    if not chosen:
        return "The sources retrieved do not answer this question directly.\n\n" + CLOSING
    chosen.sort(key=lambda x: (x[0], x[1]))
    lines = []
    for rank, _, sentence in chosen:
        sentence = sentence.rstrip()
        if not sentence.endswith((".", "!", "?")):
            sentence += "."
        label = ""
        if passages[rank - 1].chunk.superseded:
            label = f" (superseded by {passages[rank - 1].chunk.superseded_by})"
        lines.append(f"{sentence[:-1]}{label} [{rank}]{sentence[-1]}")
    return " ".join(lines) + "\n\n" + CLOSING


def stream(text: str) -> Iterator[str]:
    yield from re.findall(r"\S+\s*", text)
