"""HTTP routes for answers, deterministic tools, governance and operations."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from prometheus_client import generate_latest

from fovea import __version__, knowledge
from fovea.api.schemas import (
    AcuityRequest,
    AskRequest,
    AskResponse,
    BiometryRequest,
    FeedbackRequest,
    GlaucomaRequest,
    GradingRequest,
    HCQRequest,
    ScreenRequest,
    SearchRequest,
    TherapyRequest,
    TreatExtendRequest,
    TrialsRequest,
)
from fovea.api.security import require_admin, require_api_key
from fovea.cache import cache_key
from fovea.clinical import (
    ToolCard,
    ToolInputError,
    acuity,
    biometry,
    glaucoma,
    injections,
    safety_screen,
    screening,
    therapy,
    toxicity,
)
from fovea.clinical.trials import prefilter
from fovea.clinical.understanding import find_conditions, understand
from fovea.container import Container, get_container
from fovea.generation.pipeline import AskInput
from fovea.guardrails import emergency, pii
from fovea.observability import metrics
from fovea.retrieval.hybrid import HybridRetriever

router = APIRouter()


def container() -> Container:
    return get_container()


def _tool(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        card: ToolCard = fn(*args, **kwargs)
    except ToolInputError as exc:
        raise HTTPException(422, str(exc)) from exc
    metrics.TOOL_USE.labels(card.tool).inc()
    return card.to_dict()


def _input(body: AskRequest) -> AskInput:
    return AskInput(body.question, body.context, body.provider, body.in_scope_conversation, body.filters())


@router.post("/v1/ask", response_model=AskResponse, tags=["answers"])
def ask(
    body: AskRequest, c: Container = Depends(container), _: str = Depends(require_api_key)
) -> dict[str, Any]:
    metrics.REQUESTS.labels("ask").inc()
    redacted = pii.redact(body.question).text
    key = cache_key(redacted, body.context.model_dump(), body.provider, c.index_version)
    if not emergency.triage(redacted):
        cached = c.cache.get(key)
        if cached:
            metrics.CACHE_HITS.inc()
            return {**cached, "cached": True}
    result = c.pipeline.ask(_input(body))
    final = result["final"]
    c.audit.record_answer(final)
    metrics.observe_final(final)
    if not final["emergencies"] and final["status"] == "answered":
        c.cache.set(key, result, c.settings.cache_ttl_seconds)
    return {**result, "cached": False}


@router.post("/v1/ask/stream", tags=["answers"])
def ask_stream(
    body: AskRequest, c: Container = Depends(container), _: str = Depends(require_api_key)
) -> StreamingResponse:
    metrics.REQUESTS.labels("ask_stream").inc()

    def generate() -> Iterator[str]:
        for event in c.pipeline.events(_input(body)):
            if event.type == "final":
                c.audit.record_answer(event.data)
                metrics.observe_final(event.data)
            yield f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/v1/understand", tags=["answers"])
def understand_question(body: AskRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    from fovea.clinical.router import run_tools

    redacted = pii.redact(body.question)
    u = understand(redacted.text)
    return {
        "redacted_question": redacted.text,
        "redactions": redacted.counts,
        "understanding": u.to_dict(),
        "emergencies": [a.to_dict() for a in emergency.triage(redacted.text)],
        "tools": [card.to_dict() for card in run_tools(u, body.context, get_container().index.trials)],
    }


@router.post("/v1/search", tags=["evidence"])
def search(
    body: SearchRequest, c: Container = Depends(container), _: str = Depends(require_api_key)
) -> dict[str, Any]:
    metrics.REQUESTS.labels("search").inc()
    u = understand(pii.redact(body.query).text)
    filters: dict[str, Any] = {}
    if body.source_types:
        filters["source"] = body.source_types
    if body.min_grade:
        filters["min_grade"] = body.min_grade
    if body.jurisdiction:
        filters["jurisdiction"] = body.jurisdiction
    result = HybridRetriever(c.index, c.settings).retrieve(u, top_k=body.top_k, filters=filters or None)
    return {
        "query": u.precision_query,
        "candidates": result.candidates,
        "results": [
            {
                "chunk_id": p.chunk.id,
                "title": p.chunk.title,
                "section": p.chunk.section,
                "url": p.chunk.url,
                "source": p.chunk.source.value,
                "grade": int(p.chunk.grade),
                "year": p.chunk.year,
                "superseded_by": p.chunk.superseded_by,
                "score": round(p.score, 4),
                "reasons": p.reasons,
                "text": p.chunk.text,
            }
            for p in result.passages
        ],
    }


@router.post("/v1/tools/acuity", tags=["tools"])
def tool_acuity(body: AcuityRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    return _tool(acuity.convert, body.value, eye=body.eye)


@router.post("/v1/tools/biometry", tags=["tools"])
def tool_biometry(body: BiometryRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    data = body.model_dump(exclude={"eye"})
    return _tool(biometry.calculate, biometry.BiometryInput(**data), eye=body.eye)


@router.post("/v1/tools/grading", tags=["tools"])
def tool_grade(body: GradingRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    return _tool(screening.grade, screening.ScreeningFeatures.from_dict(body.features), eye=body.eye)


@router.post("/v1/tools/intervals", tags=["tools"])
def tool_treat_extend(body: TreatExtendRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    activity = injections.VisitActivity(
        body.intraretinal_fluid,
        body.subretinal_fluid,
        body.new_haemorrhage,
        body.letters_lost,
        body.intraocular_inflammation,
    )
    return _tool(
        injections.plan,
        body.agent,
        body.condition,
        body.injections_given,
        body.current_interval_weeks,
        activity,
        eye=body.eye,
        consecutive_dry_at_max=body.consecutive_dry_at_max,
    )


@router.post("/v1/tools/glaucoma", tags=["tools"])
def tool_glaucoma(body: GlaucomaRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    if body.iop_mmhg is not None:
        cards.append(
            _tool(
                glaucoma.oht_assessment,
                body.iop_mmhg,
                body.cct_um,
                eye=body.eye,
                pigment_dispersion=body.pigment_dispersion,
            )
        )
    if body.baseline_iop_mmhg is not None:
        cards.append(_tool(glaucoma.target_pressure, body.baseline_iop_mmhg, body.stage, eye=body.eye))
    if body.visual_fields:
        points = [(p.years_from_baseline, p.mean_deviation_db) for p in body.visual_fields]
        cards.append(_tool(glaucoma.field_progression, points, body.age, eye=body.eye))
    if not cards:
        raise HTTPException(422, "Provide an IOP, a baseline IOP or at least three visual fields")
    return {"cards": cards}


@router.post("/v1/tools/hydroxychloroquine", tags=["tools"])
def tool_hcq(body: HCQRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    return _tool(
        toxicity.monitoring_plan,
        body.weight_kg,
        body.daily_dose_mg,
        body.years_on_treatment,
        body.drug,
        body.tamoxifen,
        body.egfr,
    )


@router.post("/v1/tools/therapy", tags=["tools"])
def tool_therapy(body: TherapyRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    condition = (
        body.condition
        if "_" in body.condition or body.condition in {"dmo", "rvo", "coag", "oht"}
        else (find_conditions(body.condition) or [body.condition])[0]
    )
    q = therapy.TherapyQuery(
        condition, body.context.eye(body.eye), body.subtype, body.prior_failure, body.pigment_dispersion
    )
    return _tool(therapy.match, q, eye_label=body.eye)


@router.post("/v1/tools/screen", tags=["tools"])
def tool_screen(body: ScreenRequest, _: str = Depends(require_api_key)) -> dict[str, Any]:
    return _tool(
        safety_screen.screen, safety_screen.ScreenInput(body.planned, body.context, body.extra_conditions)
    )


@router.post("/v1/tools/trials", tags=["tools"])
def tool_trials(
    body: TrialsRequest, c: Container = Depends(container), _: str = Depends(require_api_key)
) -> dict[str, Any]:
    return _tool(
        prefilter, c.index.trials, body.condition, body.age, body.sex, body.drug, body.open_only, body.uk_only
    )


@router.post("/v1/feedback", tags=["governance"])
def feedback(
    body: FeedbackRequest, c: Container = Depends(container), _: str = Depends(require_api_key)
) -> dict[str, Any]:
    metrics.FEEDBACK.labels("positive" if body.rating > 0 else "negative").inc()
    return c.audit.record_feedback(body.request_id, body.rating, body.reasons, body.comment)


@router.get("/v1/knowledge", tags=["governance"])
def knowledge_manifest(
    c: Container = Depends(container), _: str = Depends(require_api_key)
) -> dict[str, Any]:
    manifest = {k: v for k, v in c.index.manifest.items() if k != "verification"}
    return {"index": manifest, "rule_files": knowledge.manifest(), "version": __version__}


@router.get("/v1/audit/summary", tags=["governance"])
def audit_summary(c: Container = Depends(container), _: str = Depends(require_admin)) -> dict[str, Any]:
    return c.audit.summary()


@router.get("/health", tags=["operations"])
def health(c: Container = Depends(container)) -> dict[str, Any]:
    for status in c.router.status():
        metrics.CIRCUIT_OPEN.labels(str(status["provider"])).set(1 if status["circuit"] == "open" else 0)
    return {
        "status": "ok",
        "version": __version__,
        "index_chunks": len(c.index),
        "index_built_at": c.index_version,
        "providers": c.router.status(),
        "cache": type(c.cache).__name__,
    }


@router.get("/ready", tags=["operations"])
def ready(c: Container = Depends(container)) -> dict[str, Any]:
    if len(c.index) == 0:
        raise HTTPException(503, "Index is empty")
    return {"ready": True}


@router.get("/metrics", tags=["operations"], response_class=PlainTextResponse)
def prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(
        generate_latest(metrics.REGISTRY).decode("utf-8"), media_type="text/plain; version=0.0.4"
    )
