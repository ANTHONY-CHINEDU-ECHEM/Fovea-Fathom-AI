"""Near duplicate removal with 64 bit SimHash over word shingles.

PubMed and Europe PMC return the same paper; registry records repeat across query families.
Documents whose fingerprints differ by three bits or fewer are collapsed, keeping the record
with the highest evidence grade and then the longest text.
"""

from __future__ import annotations

import hashlib
import re

from fovea.domain import Document, SourceType

_WORD = re.compile(r"[a-z0-9]+")


def simhash(text: str, shingle: int = 3) -> int:
    words = _WORD.findall(text.lower())
    if not words:
        return 0
    vector = [0] * 64
    grams = [" ".join(words[i : i + shingle]) for i in range(max(1, len(words) - shingle + 1))]
    for gram in grams:
        value = int.from_bytes(hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if (value >> bit) & 1 else -1
    return sum(1 << bit for bit in range(64) if vector[bit] > 0)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def deduplicate(documents: list[Document], threshold: int = 3) -> tuple[list[Document], int]:
    ordered = sorted(documents, key=lambda d: (int(d.grade), len(d.text)), reverse=True)
    kept: list[Document] = []
    prints: list[int] = []
    seen_ids: set[str] = set()
    removed = 0
    for doc in ordered:
        # Identifiers are namespaced; a registry id shared by a trial publication and its registry
        # record does not make them duplicates, but the same PMID from PubMed and Europe PMC does.
        key_ids = {
            f"{name}:{value}"
            for name, value in doc.identifiers.items()
            if value and (name != "nct" or doc.source == SourceType.CLINICAL_TRIAL)
        }
        if key_ids & seen_ids:
            removed += 1
            continue
        fp = simhash(doc.fingerprint_text())
        if any(hamming(fp, other) <= threshold for other in prints):
            removed += 1
            continue
        kept.append(doc)
        prints.append(fp)
        seen_ids |= key_ids
    return kept, removed
