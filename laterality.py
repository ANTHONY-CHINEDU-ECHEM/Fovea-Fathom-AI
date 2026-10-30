"""Laterality guard.

Wrong eye errors are a recognised never event in ophthalmology. The guard compares the eyes
named in the question and patient context with the eyes named in the answer. When the
question concerns one eye only and the answer attributes findings or treatment to the other,
the answer is flagged and the clinician is warned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_RIGHT_PHRASE = re.compile(r"\b(?:right eye|r eye|oculus dexter)\b", re.I)
_LEFT_PHRASE = re.compile(r"\b(?:left eye|l eye|oculus sinister)\b", re.I)
_RIGHT_ABBR = re.compile(r"\b(?:RE|OD)\b")
_LEFT_ABBR = re.compile(r"\b(?:LE|OS)\b")
_BOTH = re.compile(r"\b(?:both eyes|bilateral(?:ly)?|OU|each eye|either eye|fellow eye|second eye)\b", re.I)


def eyes_named(text: str) -> set[str]:
    """Eyes named in ``text``; abbreviations are matched case sensitively to avoid false hits."""
    found: set[str] = set()
    if _RIGHT_PHRASE.search(text) or _RIGHT_ABBR.search(text):
        found.add("right")
    if _LEFT_PHRASE.search(text) or _LEFT_ABBR.search(text):
        found.add("left")
    if _BOTH.search(text):
        found.add("both")
    return found


@dataclass
class LateralityReport:
    requested: list[str]
    mentioned: list[str]
    consistent: bool
    issues: list[str] = field(default_factory=list)


def check(question: str, context_eyes: list[str], answer: str) -> LateralityReport:
    requested = eyes_named(question)
    if not requested - {"both"} and context_eyes:
        requested |= set(context_eyes)
    mentioned = eyes_named(answer)
    issues: list[str] = []
    single = requested - {"both"}
    if len(single) == 1 and "both" not in requested:
        target = next(iter(single))
        other = "left" if target == "right" else "right"
        if other in mentioned:
            issues.append(
                f"The question concerns the {target} eye but the answer refers to the {other} eye; confirm laterality."
            )
    return LateralityReport(sorted(requested), sorted(mentioned), not issues, issues)
