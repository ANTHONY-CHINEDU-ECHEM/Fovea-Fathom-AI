"""Clinical tagging of documents: conditions, medicines and interventions.

Tags drive the condition and medicine priors at retrieval time, so tagging is negation
aware: "no diabetic macular oedema" or "excluding people with uveitis" does not tag the
document with that condition. Title mentions always count.
"""

from __future__ import annotations

import re

from fovea.clinical.understanding import _term_index, normalise
from fovea.domain import Document

_NEGATORS = re.compile(
    r"\b(no|not|without|excluding|excluded|exclusion of|absence of|other than|rather than|never)\b[^.;:]{0,30}$"
)
MAX_TAGS = 6


def _tag(text: str, kind: str, title: str) -> list[str]:
    counts: dict[str, int] = {}
    title_norm = normalise(title)
    body = normalise(text)
    for term, canonical in _term_index()[kind]:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])")
        if pattern.search(title_norm):
            counts[canonical] = counts.get(canonical, 0) + 5
        for m in pattern.finditer(body):
            if _NEGATORS.search(body[max(0, m.start() - 40) : m.start()]):
                continue
            counts[canonical] = counts.get(canonical, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, count in ranked if count >= 1][:MAX_TAGS]


def tag_document(doc: Document) -> Document:
    text = doc.text + " " + " ".join(body for _, body in doc.sections)
    if not doc.conditions:
        doc.conditions = _tag(text, "condition", doc.title)
    if not doc.drugs:
        doc.drugs = _tag(text, "drug", doc.title)
    if not doc.interventions:
        doc.interventions = _tag(text, "intervention", doc.title)
    return doc


def tag_text(text: str, kind: str) -> list[str]:
    return _tag(text, kind, "")
