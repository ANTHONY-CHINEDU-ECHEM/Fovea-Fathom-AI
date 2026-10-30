"""Citation and figure validation.

* Citations to ids that were never supplied are removed.
* Sentence coverage is the share of factual sentences that carry at least one valid citation.
* Every number carrying a clinical unit (percentages, weeks, months, mg, mmHg, micrometres,
  letters, dioptres, dB, logMAR, Snellen fractions, hazard ratios) must match a number in one of
  the sentence's cited sources, compared numerically so 0.5 matches 0.50 and 6/12 matches 6/12.
  Unmatched figures are flagged inside the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from fovea.domain import ScoredChunk

_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])|\n+")
_FIGURE = re.compile(
    r"(?<![\w/])(\d+(?:\.\d+)?)\s?(%|percent|per cent|weeks?|months?|mg/kg|mg|micrograms?|mmhg|mm hg|µm|um|micrometres?|microns?|"
    r"letters?|dioptres?|d\b|db|logmar|years?|disc areas?|injections?|doses?)"
    r"|(?<![\w.])((?:6|20)/\d+(?:\.\d+)?)"
    r"|\b(?:hazard ratio|hr|odds ratio|or|risk ratio|rr)\s*(?:of\s*)?(\d+\.\d+)",
    re.I,
)
UNVERIFIED_MARK = " [figure not found in the cited source]"


@dataclass
class SentenceCheck:
    text: str
    citations: list[int]
    figures: list[str] = field(default_factory=list)
    unmatched_figures: list[str] = field(default_factory=list)
    factual: bool = True


@dataclass
class CitationReport:
    answer: str
    sentences: list[SentenceCheck]
    invalid_citations: list[int]
    coverage: float
    unsupported_figures: list[str]
    cited_ids: list[int]


_LEADING_CITES = re.compile(r"^((?:\[\d+(?:\s*,\s*\d+)*\]\s*)+)(.*)$", re.S)


def split_sentences(text: str) -> list[str]:
    """Split into sentences, re attaching citations written after the full stop to their sentence."""
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]
    out: list[str] = []
    for part in parts:
        m = _LEADING_CITES.match(part)
        if m and out:
            out[-1] = f"{out[-1]} {m.group(1).strip()}"
            part = m.group(2).strip()
        if part:
            out.append(part)
    return out


def _is_factual(sentence: str) -> bool:
    lower = sentence.lower()
    if lower.startswith(
        ("clinical judgement", "the sources do not", "i cannot", "these sources do not", "no source")
    ):
        return False
    if sentence.endswith("?") or len(sentence.split()) < 4:
        return False
    return True


def _numbers(text: str) -> set[float | str]:
    values: set[float | str] = set()
    for m in re.finditer(r"(?:6|20)/\d+(?:\.\d+)?", text):
        values.add(m.group(0))
    for m in re.finditer(r"(?<![\d/])\d+(?:\.\d+)?", text):
        try:
            values.add(round(float(m.group(0)), 4))
        except ValueError:
            continue
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "twelve": 12,
        "sixteen": 16,
        "twenty": 20,
        "twenty four": 24,
    }
    lower = text.lower()
    for word, value in words.items():
        if re.search(rf"\b{word}\b", lower):
            values.add(float(value))
    return values


def figures_in(sentence: str) -> list[tuple[str, float | str]]:
    out: list[tuple[str, float | str]] = []
    for m in _FIGURE.finditer(sentence):
        if m.group(3):
            out.append((m.group(3), m.group(3)))
        elif m.group(4):
            out.append((m.group(0), round(float(m.group(4)), 4)))
        elif m.group(1):
            out.append((m.group(0), round(float(m.group(1)), 4)))
    return out


def validate(answer: str, passages: list[ScoredChunk], mark: bool = True) -> CitationReport:
    valid_ids = set(range(1, len(passages) + 1))
    invalid: list[int] = []

    def strip_invalid(m: re.Match[str]) -> str:
        ids = [int(x) for x in re.split(r"\s*,\s*", m.group(1))]
        kept = [i for i in ids if i in valid_ids]
        invalid.extend(i for i in ids if i not in valid_ids)
        return "".join(f"[{i}]" for i in kept)

    cleaned = _CITATION.sub(strip_invalid, answer)
    source_numbers = {
        i: _numbers(p.chunk.text + " " + p.chunk.title) for i, p in enumerate(passages, start=1)
    }

    checks: list[SentenceCheck] = []
    unsupported: list[str] = []
    marked = cleaned
    for sentence in split_sentences(cleaned):
        cites = sorted({int(x) for group in _CITATION.findall(sentence) for x in re.split(r"\s*,\s*", group)})
        check = SentenceCheck(text=sentence, citations=cites, factual=_is_factual(sentence))
        available: set[float | str] = set()
        for c in cites:
            available |= source_numbers.get(c, set())
        for label, value in figures_in(_CITATION.sub("", sentence)):
            check.figures.append(label)
            if value not in available:
                check.unmatched_figures.append(label)
        if check.unmatched_figures and check.factual:
            unsupported.extend(check.unmatched_figures)
            if mark and UNVERIFIED_MARK.strip() not in sentence:
                marked = marked.replace(sentence, sentence + UNVERIFIED_MARK, 1)
        checks.append(check)

    factual = [c for c in checks if c.factual]
    coverage = sum(1 for c in factual if c.citations) / len(factual) if factual else 1.0
    cited = sorted({i for c in checks for i in c.citations})
    return CitationReport(
        answer=marked,
        sentences=checks,
        invalid_citations=sorted(set(invalid)),
        coverage=round(coverage, 4),
        unsupported_figures=unsupported,
        cited_ids=cited,
    )
