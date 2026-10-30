"""Section aware chunking.

Chunks never cross a section boundary, so a recommendation is never glued to the heading of
the next one. Long sections are split on sentence boundaries into windows of roughly
``target_chars`` with a one sentence overlap. Every chunk inherits the provenance and clinical
tags of its document, and its own condition and medicine tags are recomputed from its text so
that a long review discussing several conditions yields correctly scoped passages.
"""

from __future__ import annotations

import re

from fovea.domain import Chunk, Document, stable_id
from ingestion.processing.tagger import tag_text

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


def _windows(text: str, target_chars: int, overlap: int) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE.split(text) if s.strip()]
    if not sentences:
        return []
    windows: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        if current and sum(len(s) + 1 for s in current) + len(sentence) > target_chars:
            windows.append(" ".join(current))
            current = current[-overlap:] if overlap else []
        current.append(sentence)
    if current:
        windows.append(" ".join(current))
    return windows


def chunk_document(doc: Document, target_chars: int = 900, overlap: int = 1) -> list[Chunk]:
    sections = doc.sections or [("", doc.text)]
    acronym = str(doc.metadata.get("acronym", "")).strip()
    if acronym:
        sections = [(f"{acronym}: {heading}" if heading else acronym, body) for heading, body in sections]
    chunks: list[Chunk] = []
    position = 0
    for heading, body in sections:
        for window in _windows(body, target_chars, overlap):
            own_conditions = tag_text(window, "condition")
            own_drugs = tag_text(window, "drug")
            chunks.append(
                Chunk(
                    id=stable_id(doc.id, heading, str(position), window[:80]),
                    doc_id=doc.id,
                    text=window,
                    title=doc.title,
                    url=doc.url,
                    source=doc.source,
                    section=heading,
                    year=doc.year,
                    jurisdiction=doc.jurisdiction,
                    licence=doc.licence,
                    grade=doc.grade,
                    conditions=own_conditions or list(doc.conditions),
                    drugs=own_drugs or list(doc.drugs),
                    interventions=list(doc.interventions),
                    superseded_by=doc.superseded_by,
                    position=position,
                )
            )
            position += 1
    return chunks
