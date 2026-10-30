"""The answer pipeline, expressed as a stream of events.

``AnswerPipeline.events`` yields, in order:

* ``meta``        request id, redaction summary, scope decision, provider chain
* ``emergency``   eye emergency banner, before any retrieval (only when triggered)
* ``tools``       deterministic tool cards
* ``sources``     the numbered sources passed to the model
* ``token``       answer text as it is generated
* ``final``       the validated answer with its grounding, laterality and audit summary

``/v1/ask`` collects the same events into one response, so streaming and non streaming
answers are produced by identical code.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from fovea import knowledge
from fovea.clinical.router import run_tools
from fovea.clinical.understanding import understand
from fovea.config import Settings
from fovea.domain import PatientContext, ScoredChunk
from fovea.generation import answerability, citations, extractive, faithfulness, laterality
from fovea.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from fovea.guardrails import emergency, injection, pii, scope
from fovea.llm.base import GenerationRequest
from fovea.llm.router import LLMRouter
from fovea.retrieval.hybrid import HybridRetriever
from fovea.retrieval.index import KnowledgeIndex

ABSTAIN_TEXT = (
    "I cannot answer this reliably from the indexed evidence. {reason} "
    "Please consult the full NICE guidance, the SmPC and the local protocol, or refine the question."
)
OUT_OF_SCOPE_TEXT = (
    "This question does not appear to concern eye care, which is the only scope of Fovea Fathom AI."
)


@dataclass
class AskInput:
    question: str
    context: PatientContext = field(default_factory=PatientContext)
    provider: str | None = None
    in_scope_conversation: bool = False
    filters: dict[str, Any] | None = None


@dataclass
class Event:
    type: str
    data: dict[str, Any]


def _redact_context(ctx: PatientContext) -> tuple[PatientContext, int]:
    count = 0
    updates: dict[str, Any] = {}
    for name in ("conditions", "medicines", "allergies"):
        values = getattr(ctx, name)
        redacted = [pii.redact(v) for v in values]
        count += sum(sum(r.counts.values()) for r in redacted)
        updates[name] = [r.text for r in redacted]
    eyes: dict[str, Any] = {}
    for side, eye in ctx.eyes():
        if eye.diagnosis:
            r = pii.redact(eye.diagnosis)
            count += sum(r.counts.values())
            eyes[side] = eye.model_copy(update={"diagnosis": r.text})
    return ctx.model_copy(update={**updates, **eyes}), count


def _source_view(number: int, item: ScoredChunk) -> dict[str, Any]:
    c = item.chunk
    return {
        "number": number,
        "chunk_id": c.id,
        "doc_id": c.doc_id,
        "title": c.title,
        "section": c.section,
        "url": c.url,
        "source": c.source.value,
        "source_label": c.source.label,
        "grade": int(c.grade),
        "grade_label": c.grade.label,
        "year": c.year,
        "jurisdiction": c.jurisdiction,
        "licence": c.licence.value,
        "superseded_by": c.superseded_by,
        "score": round(item.score, 4),
        "relevance": round(item.rerank_score, 4),
        "prior": round(item.prior, 3),
        "reasons": item.reasons,
        "excerpt": c.text[:600],
    }


class AnswerPipeline:
    def __init__(self, index: KnowledgeIndex, router: LLMRouter, settings: Settings) -> None:
        self.index = index
        self.router = router
        self.settings = settings
        self.retriever = HybridRetriever(index, settings)

    def currency_notes(self, passages: list[ScoredChunk]) -> list[str]:
        notes = []
        graph = knowledge.load("supersession").data["superseded"]
        for item in passages:
            if item.chunk.superseded:
                note = next((g["note"] for g in graph if g["new"] == item.chunk.superseded_by), None)
                notes.append(
                    f"'{item.chunk.title}' is superseded by {item.chunk.superseded_by}. {note or ''}".strip()
                )
        return list(dict.fromkeys(notes))

    def events(self, inp: AskInput) -> Iterator[Event]:
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        red = pii.redact(inp.question)
        ctx, ctx_redactions = _redact_context(inp.context)
        question = red.text
        context_text = " ".join(
            [*ctx.conditions, *ctx.medicines, *(e.diagnosis or "" for _, e in ctx.eyes())]
        )
        u = understand(re.sub(r"\[[A-Z_]+\]", " ", question), context_text)
        known_ids = {g for g in u.guidance_ids if self.index.ids_mentioning(g)}
        decision = scope.check(
            u,
            has_context=not ctx.is_empty(),
            in_scope_conversation=inp.in_scope_conversation,
            known_ids=known_ids,
        )
        alerts = emergency.triage(f"{question} {context_text}")

        yield Event(
            "meta",
            {
                "request_id": request_id,
                "redacted_question": question,
                "redactions": {**red.counts, **({"CONTEXT": ctx_redactions} if ctx_redactions else {})},
                "in_scope": decision.in_scope or bool(alerts),
                "scope_reason": decision.reason,
                "provider_chain": self.router.chain(inp.provider),
                "understanding": {
                    "conditions": u.conditions,
                    "drugs": u.drugs,
                    "interventions": u.interventions,
                    "laterality": u.laterality,
                    "intents": u.intents,
                },
            },
        )
        if alerts:
            yield Event("emergency", {"alerts": [a.to_dict() for a in alerts]})

        if not decision.in_scope and not alerts:
            yield Event("token", {"text": OUT_OF_SCOPE_TEXT})
            yield Event(
                "final",
                self._final(
                    request_id,
                    OUT_OF_SCOPE_TEXT,
                    "out_of_scope",
                    [],
                    u,
                    alerts,
                    None,
                    None,
                    None,
                    None,
                    None,
                    [],
                    started,
                    question,
                ),
            )
            return

        cards = run_tools(u, ctx, self.index.trials)
        if cards:
            yield Event("tools", {"cards": [c.to_dict() for c in cards]})

        if alerts:
            u.recall_query = f"{u.recall_query} {emergency.guidance_query(alerts)}"
        retrieval = self.retriever.retrieve(u, filters=inp.filters)
        passages, dropped = injection.filter_passages(retrieval.passages)
        gate = answerability.assess(u, passages, self.index.bm25, self.settings)
        yield Event(
            "sources",
            {
                "sources": [_source_view(i, p) for i, p in enumerate(passages, start=1)],
                "dropped_for_injection": dropped,
            },
        )

        if not gate.answerable:
            text = ABSTAIN_TEXT.format(reason=gate.reason)
            yield Event("token", {"text": text})
            yield Event(
                "final",
                self._final(
                    request_id,
                    text,
                    "abstained",
                    passages,
                    u,
                    alerts,
                    gate,
                    None,
                    None,
                    None,
                    None,
                    cards,
                    started,
                    question,
                ),
            )
            return

        prompt = build_user_prompt(question, passages, ctx, self.currency_notes(passages))
        request = GenerationRequest(
            SYSTEM_PROMPT, prompt, self.settings.llm_max_tokens, self.settings.llm_temperature
        )
        tokens, outcome = self.router.stream(
            request, inp.provider, lambda: extractive.stream(extractive.compose(u, passages, self.index.bm25))
        )
        pieces: list[str] = []
        for piece in tokens:
            pieces.append(piece)
            yield Event("token", {"text": piece})
        raw = "".join(pieces).strip()

        report = citations.validate(raw, passages)
        faith = faithfulness.assess(report, passages)
        context_eyes: list[str] = [side for side, _ in ctx.eyes()]
        lat = laterality.check(question, context_eyes if len(context_eyes) == 1 else [], report.answer)
        yield Event(
            "final",
            self._final(
                request_id,
                report.answer,
                "answered",
                passages,
                u,
                alerts,
                gate,
                report,
                faith,
                lat,
                outcome,
                cards,
                started,
                question,
            ),
        )

    def _final(
        self,
        request_id,
        answer,
        status,
        passages,
        u,
        alerts,
        gate,
        report,
        faith,
        lat,
        outcome,
        cards,
        started,
        question,
    ) -> dict[str, Any]:
        s = self.settings
        grounding = None
        if report is not None and faith is not None:
            grounded = (
                report.coverage >= s.min_citation_coverage
                and not report.unsupported_figures
                and faith.score >= s.min_faithfulness
                and (lat is None or lat.consistent)
            )
            grounding = {
                "citation_coverage": report.coverage,
                "invalid_citations": report.invalid_citations,
                "unsupported_figures": report.unsupported_figures,
                "claim_support": faith.score,
                "claims": faith.claims,
                "unsupported_claims": faith.unsupported_sentences,
                "cited_sources": report.cited_ids,
                "grounded": grounded,
            }
        return {
            "request_id": request_id,
            "status": status,
            "answer": answer,
            "question": question,
            "grounding": grounding,
            "laterality": None
            if lat is None
            else {
                "requested": lat.requested,
                "mentioned": lat.mentioned,
                "consistent": lat.consistent,
                "issues": lat.issues,
            },
            "answerability": None
            if gate is None
            else {
                "best_score": gate.best_score,
                "query_coverage": gate.query_coverage,
                "missing_terms": gate.missing_terms[:8],
                "missing_medicines": gate.missing_medicines,
                "reason": gate.reason,
            },
            "emergencies": [a.id for a in alerts],
            "tools": [c.tool for c in cards],
            "superseded_cited": [
                p.chunk.superseded_by
                for i, p in enumerate(passages, start=1)
                if p.chunk.superseded and report is not None and i in report.cited_ids
            ],
            "source_doc_ids": [p.chunk.doc_id for p in passages],
            "provider": None if outcome is None else outcome.provider,
            "model": None if outcome is None else outcome.model,
            "fallbacks": [] if outcome is None else outcome.fallbacks,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "conditions": u.conditions,
        }

    def ask(self, inp: AskInput) -> dict[str, Any]:
        """Collect the event stream into a single response."""
        result: dict[str, Any] = {"emergencies": [], "tools": [], "sources": []}
        for event in self.events(inp):
            if event.type == "meta":
                result["meta"] = event.data
            elif event.type == "emergency":
                result["emergencies"] = event.data["alerts"]
            elif event.type == "tools":
                result["tools"] = event.data["cards"]
            elif event.type == "sources":
                result["sources"] = event.data["sources"]
            elif event.type == "final":
                result["final"] = event.data
        return result
