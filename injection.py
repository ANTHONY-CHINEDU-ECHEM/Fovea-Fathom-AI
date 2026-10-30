"""Prompt injection filter for harvested passages.

Harvested documents are data, not instructions. Passages that address the model or try to
change its behaviour are dropped before generation, and every remaining source is wrapped in
an element that the system prompt marks as untrusted.
"""

from __future__ import annotations

import re

from fovea.domain import ScoredChunk

_PATTERNS = [
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts)",
    r"disregard (?:the|your) (?:system|previous) (?:prompt|instructions)",
    r"you are (?:now )?(?:an?|the) (?:ai|assistant|language model)\b",
    r"\bsystem prompt\b",
    r"\bas an ai (?:language )?model\b",
    r"reveal (?:your|the) (?:instructions|prompt)",
    r"</?(?:source|system|instructions)>",
    r"\bdo not cite\b",
    r"respond (?:only )?with",
]
_INJECTION = re.compile("|".join(_PATTERNS), re.I)


def is_suspicious(text: str) -> bool:
    return bool(_INJECTION.search(text))


def filter_passages(passages: list[ScoredChunk]) -> tuple[list[ScoredChunk], int]:
    kept = [p for p in passages if not is_suspicious(p.chunk.text)]
    return kept, len(passages) - len(kept)
