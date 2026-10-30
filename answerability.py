"""Answerability gate: abstain when the evidence cannot support an answer.

The system abstains when:
* the best passage score is below the evidence threshold;
* the question's most specific terms, weighted by inverse document frequency with guideline
  synonyms credited, are poorly covered by the selected passages; or
* a medicine named in the question appears in none of the selected passages.
Emergencies keep their banner even when the answer abstains.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fovea.clinical.understanding import Understanding, find_conditions
from fovea.config import Settings
from fovea.domain import ScoredChunk
from fovea.retrieval.bm25 import BM25Index
from fovea.retrieval.tokenizer import STOPWORDS, tokenize

GENERIC = {
    "patient",
    "treatment",
    "treat",
    "eye",
    "eyes",
    "recommend",
    "recommended",
    "option",
    "nice",
    "should",
    "use",
    "used",
    "give",
    "start",
    "first",
    "line",
    "best",
    "management",
    "manage",
    "people",
    "adult",
    "adults",
    "clinical",
    "please",
    "tell",
    "explain",
    "current",
    "evidence",
    "guidance",
    "offer",
    "need",
    "know",
    "right",
    "left",
    "year",
    "old",
    "apply",
    "applie",
    "bcva",
    "acuity",
    "va",
    "cst",
    "crt",
    "subfield",
    "today",
    "phakic",
    "pseudophakic",
}


@dataclass
class AnswerabilityDecision:
    answerable: bool
    best_score: float
    query_coverage: float
    missing_terms: list[str] = field(default_factory=list)
    missing_medicines: list[str] = field(default_factory=list)
    reason: str = ""


def assess(
    u: Understanding, passages: list[ScoredChunk], bm25: BM25Index, settings: Settings
) -> AnswerabilityDecision:
    best = passages[0].score if passages else 0.0
    precise = [
        t
        for t in dict.fromkeys(tokenize(u.precision_query, concepts=False))
        if t not in STOPWORDS
        and t not in GENERIC
        and not any(ch.isdigit() for ch in t)
        and not t.startswith("[")
    ]
    recall_extra = set(tokenize(u.recall_query, concepts=True)) - set(precise)
    text_tokens: set[str] = set()
    tagged_conditions: set[str] = set()
    for p in passages:
        text_tokens.update(tokenize(f"{p.chunk.title} {p.chunk.section} {p.chunk.text}"))
        tagged_conditions.update(p.chunk.conditions)
    # An abbreviation such as "dmo" is covered when a passage is tagged with that condition.
    for token in precise:
        found = find_conditions(token)
        if found and set(found) & tagged_conditions:
            text_tokens.add(token)
    weights = {t: bm25.idf(t) for t in precise}
    total = sum(weights.values())
    covered = 0.0
    missing: list[str] = []
    for token, weight in weights.items():
        if token in text_tokens:
            covered += weight
        else:
            missing.append(token)
    credit = 0.5 * sum(bm25.idf(t) for t in recall_extra if t in text_tokens)
    coverage = min(1.0, (covered + credit) / total) if total else 1.0

    missing_meds = [
        d for d in u.drugs if not any(d in p.chunk.drugs or d in p.chunk.text.lower() for p in passages)
    ]
    decision = AnswerabilityDecision(True, round(best, 4), round(coverage, 4), missing, missing_meds)
    if not passages:
        decision.answerable, decision.reason = False, "No passage was retrieved."
    elif best < settings.min_evidence_score:
        decision.answerable, decision.reason = False, "The best evidence is too weak to answer reliably."
    elif coverage < settings.min_query_coverage:
        decision.answerable, decision.reason = (
            False,
            "The retrieved evidence does not cover the specific terms of the question.",
        )
    elif missing_meds:
        decision.answerable, decision.reason = (
            False,
            f"No retrieved source mentions {', '.join(missing_meds)}.",
        )
    return decision
