"""Prometheus metrics, including safety signals the alert rules watch."""

from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

REQUESTS = Counter("fovea_requests_total", "Questions received", ["endpoint"], registry=REGISTRY)
ANSWERS = Counter("fovea_answers_total", "Answers by status", ["status"], registry=REGISTRY)
LATENCY = Histogram(
    "fovea_answer_latency_seconds",
    "End to end answer latency",
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32),
    registry=REGISTRY,
)
PROVIDER = Counter("fovea_provider_total", "Answers by provider", ["provider"], registry=REGISTRY)
FALLBACKS = Counter("fovea_provider_fallbacks_total", "Provider fallbacks", ["provider"], registry=REGISTRY)
EMERGENCIES = Counter("fovea_emergencies_total", "Emergency banners raised", ["emergency"], registry=REGISTRY)
UNSUPPORTED_FIGURES = Counter(
    "fovea_unsupported_figures_total", "Figures not found in cited sources", registry=REGISTRY
)
UNGROUNDED = Counter("fovea_ungrounded_answers_total", "Answers that failed grounding", registry=REGISTRY)
LATERALITY_FLAGS = Counter(
    "fovea_laterality_flags_total", "Answers flagged for an eye mismatch", registry=REGISTRY
)
SUPERSEDED_CITED = Counter(
    "fovea_superseded_cited_total", "Answers citing superseded guidance", registry=REGISTRY
)
CITATION_COVERAGE = Histogram(
    "fovea_citation_coverage",
    "Citation coverage per answer",
    buckets=(0.5, 0.7, 0.8, 0.9, 0.95, 1.0),
    registry=REGISTRY,
)
CLAIM_SUPPORT = Histogram(
    "fovea_claim_support",
    "Claim support per answer",
    buckets=(0.5, 0.7, 0.8, 0.9, 0.95, 1.0),
    registry=REGISTRY,
)
TOOL_USE = Counter("fovea_tool_cards_total", "Deterministic tool cards produced", ["tool"], registry=REGISTRY)
CACHE_HITS = Counter("fovea_cache_hits_total", "Answer cache hits", registry=REGISTRY)
FEEDBACK = Counter("fovea_feedback_total", "Clinician feedback", ["polarity"], registry=REGISTRY)
INDEX_CHUNKS = Gauge("fovea_index_chunks", "Chunks in the knowledge index", registry=REGISTRY)
CIRCUIT_OPEN = Gauge(
    "fovea_circuit_open", "Circuit breaker open for provider", ["provider"], registry=REGISTRY
)


def observe_final(final: dict[str, Any]) -> None:
    ANSWERS.labels(final["status"]).inc()
    LATENCY.observe((final.get("latency_ms") or 0) / 1000)
    if final.get("provider"):
        PROVIDER.labels(final["provider"]).inc()
    for name in final.get("fallbacks", []):
        FALLBACKS.labels(name).inc()
    for emergency in final.get("emergencies", []):
        EMERGENCIES.labels(emergency).inc()
    for tool in final.get("tools", []):
        TOOL_USE.labels(tool).inc()
    grounding = final.get("grounding")
    if grounding:
        CITATION_COVERAGE.observe(grounding["citation_coverage"])
        CLAIM_SUPPORT.observe(grounding["claim_support"])
        if grounding["unsupported_figures"]:
            UNSUPPORTED_FIGURES.inc(len(grounding["unsupported_figures"]))
        if not grounding["grounded"]:
            UNGROUNDED.inc()
    laterality = final.get("laterality")
    if laterality and not laterality.get("consistent", True):
        LATERALITY_FLAGS.inc()
    if final.get("superseded_cited"):
        SUPERSEDED_CITED.inc()
