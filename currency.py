"""Guidance currency: mark documents replaced by newer guidance using the supersession graph."""

from __future__ import annotations

import re

from fovea import knowledge
from fovea.domain import Document


def apply(documents: list[Document]) -> int:
    graph = knowledge.load("supersession").data["superseded"]
    marked = 0
    for doc in documents:
        if doc.superseded_by:
            marked += 1
            continue
        guidance_id = doc.identifiers.get("guidance", "")
        for edge in graph:
            old = edge["old"]
            if not re.fullmatch(r"[A-Z]{2,3}\d{2,4}", old):
                continue
            if guidance_id.upper() == old or re.search(rf"\(\s*{old}\s*\)", doc.title, re.I):
                doc.superseded_by = edge["new"]
                marked += 1
                break
    return marked
