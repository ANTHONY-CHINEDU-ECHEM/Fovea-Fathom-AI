"""Evaluation metrics computed per question and aggregated across the golden set."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuestionResult:
    id: str
    status: str
    expected_status: str
    hit_at_5: bool | None
    reciprocal_rank: float | None
    fact_recall: float | None
    citation_coverage: float | None
    claim_support: float | None
    unsupported_figures: int
    emergency_ok: bool
    tools_ok: bool | None
    redaction_ok: bool | None
    scope_ok: bool
    laterality_ok: bool
    latency_ms: float
    notes: list[str] = field(default_factory=list)


def retrieval(expected: list[str], retrieved: list[str]) -> tuple[bool | None, float | None]:
    if not expected:
        return None, None
    hit = any(doc in expected for doc in retrieved[:5])
    for rank, doc in enumerate(retrieved, start=1):
        if doc in expected:
            return hit, 1.0 / rank
    return hit, 0.0


def fact_recall(expected: list[str], answer: str) -> float | None:
    if not expected:
        return None
    lowered = answer.lower()
    return sum(1 for fact in expected if fact.lower() in lowered) / len(expected)


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else None


def _rate(values: list[bool | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(1 for v in present if v) / len(present), 4) if present else None


def aggregate(results: list[QuestionResult]) -> dict[str, Any]:
    answered_expected = [r for r in results if r.expected_status == "answered"]
    abstain_expected = [r for r in results if r.expected_status == "abstained"]
    scope_expected = [r for r in results if r.expected_status == "out_of_scope"]
    answered = [r for r in results if r.status == "answered"]
    return {
        "questions": len(results),
        "retrieval_hit_at_5": _rate([r.hit_at_5 for r in results]),
        "retrieval_mrr": _mean([r.reciprocal_rank for r in results]),
        "expected_fact_recall": _mean([r.fact_recall for r in results if r.status == "answered"]),
        "citation_coverage": _mean([r.citation_coverage for r in answered]),
        "claim_support": _mean([r.claim_support for r in answered]),
        "answers_with_unsupported_figures": round(
            sum(1 for r in answered if r.unsupported_figures) / (len(answered) or 1), 4
        ),
        "answered_when_expected": _rate([r.status == "answered" for r in answered_expected]),
        "emergency_triage_accuracy": _rate([r.emergency_ok for r in results]),
        "abstention_accuracy": _rate([r.status == "abstained" for r in abstain_expected]),
        "scope_accuracy": _rate([r.scope_ok for r in results]),
        "tool_routing_accuracy": _rate([r.tools_ok for r in results]),
        "redaction_accuracy": _rate([r.redaction_ok for r in results]),
        "laterality_consistency": _rate([r.laterality_ok for r in answered]),
        "out_of_scope_detected": _rate([r.status == "out_of_scope" for r in scope_expected]),
        "median_latency_ms": sorted(r.latency_ms for r in results)[len(results) // 2] if results else None,
    }
