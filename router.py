"""Tool router: decides which deterministic tools a question calls for and runs them.

The router combines intents from query understanding with the structured patient context.
Tools run per eye whenever the context is given per eye, and each card is labelled with the
eye it describes so a right eye result can never be read as a left eye result.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from fovea.clinical import ToolCard, ToolInputError, glaucoma, injections, safety_screen, therapy, toxicity
from fovea.clinical import acuity as acuity_tool
from fovea.clinical.trials import TrialRecord, prefilter
from fovea.clinical.understanding import Understanding, find_conditions
from fovea.domain import EyeContext, PatientContext

log = logging.getLogger(__name__)

THERAPY_CONDITIONS = {
    "wet_amd",
    "dmo",
    "rvo",
    "myopic_cnv",
    "coag",
    "oht",
    "uveitis",
    "dry_eye",
    "limbal_stem_cell",
    "uveal_melanoma",
}
TE_CONDITIONS = {"wet_amd", "dmo", "rvo", "myopic_cnv"}


def _safe(name: str, fn: Callable[..., ToolCard], *args: Any, **kwargs: Any) -> ToolCard | None:
    try:
        return fn(*args, **kwargs)
    except ToolInputError as exc:
        log.info("tool %s skipped: %s", name, exc)
        return None


def _eyes_for(u: Understanding, ctx: PatientContext) -> list[tuple[str | None, EyeContext]]:
    eyes: list[tuple[str | None, EyeContext]] = [(side, eye) for side, eye in ctx.eyes()]
    if u.laterality and len(eyes) > 1:
        requested = {s for s in u.laterality if s in {"right", "left"}}
        if requested and "both" not in u.laterality:
            eyes = [(s, e) for s, e in eyes if s in requested]
    if eyes:
        # Findings typed in the question complete, but never overwrite, the structured context of
        # the eye the question is about (or of the only eye supplied).
        targets = [(s, e) for s, e in eyes if s in u.laterality] or (eyes if len(eyes) == 1 else [])
        merged = []
        for side, eye in eyes:
            merged.append((side, _complete(eye, u) if (side, eye) in targets else eye))
        return merged
    side = next((s for s in u.laterality if s in {"right", "left"}), None)
    return [(side, _complete(EyeContext(), u))]


_NEGATED = re.compile(r"\b(?:no|without|resolved|dry,? no)\s+(?:\w+\s+){0,2}$")


def _mentioned(text: str, phrase: str) -> bool:
    for m in re.finditer(re.escape(phrase), text):
        if not _NEGATED.search(text[max(0, m.start() - 30) : m.start()]):
            return True
    return False


def _complete(eye: EyeContext, u: Understanding) -> EyeContext:
    updates: dict[str, Any] = {}
    if eye.bcva is None and u.acuities:
        updates["bcva"] = u.acuities[0]
    if eye.central_subfield_thickness_um is None and u.cst_values:
        updates["central_subfield_thickness_um"] = u.cst_values[0]
    if eye.iop_mmhg is None and u.iop_values:
        updates["iop_mmhg"] = u.iop_values[0]
    if eye.current_interval_weeks is None and u.interval_weeks is not None:
        updates["current_interval_weeks"] = u.interval_weeks
    if eye.injections_given is None and u.injection_count is not None:
        updates["injections_given"] = u.injection_count
    if eye.subretinal_fluid is None and _mentioned(u.normalised, "subretinal fluid"):
        updates["subretinal_fluid"] = True
    if eye.intraretinal_fluid is None and _mentioned(u.normalised, "intraretinal fluid"):
        updates["intraretinal_fluid"] = True
    if eye.new_haemorrhage is None and _mentioned(u.normalised, "new haemorrhage"):
        updates["new_haemorrhage"] = True
    return eye.model_copy(update=updates) if updates else eye


def _condition_for_eye(u: Understanding, eye: EyeContext) -> str | None:
    if eye.diagnosis:
        found = find_conditions(eye.diagnosis)
        if found:
            return found[0]
    return u.conditions[0] if u.conditions else None


def run_tools(
    u: Understanding, ctx: PatientContext, trial_records: list[TrialRecord] | None = None
) -> list[ToolCard]:
    cards: list[ToolCard] = []
    intents = set(u.intents)
    eyes = _eyes_for(u, ctx)

    for side, eye in eyes:
        condition = _condition_for_eye(u, eye)
        if eye.bcva and ("acuity_conversion" in intents or condition in {"wet_amd"}):
            card = _safe("acuity", acuity_tool.convert, eye.bcva or "", eye=side)
            if card:
                cards.append(card)
        if condition in THERAPY_CONDITIONS and ("therapy_options" in intents or not ctx.is_empty()):
            subtype = "crvo" if "crvo" in u.normalised else "brvo" if "brvo" in u.normalised else None
            prior = (
                "non_corticosteroid"
                if any(
                    w in u.normalised
                    for w in (
                        "not responded",
                        "insufficient response",
                        "inadequate response",
                        "refractory",
                        "persistent despite",
                    )
                )
                else None
            )
            q = therapy.TherapyQuery(
                condition,
                eye,
                subtype=subtype,
                prior_failure=prior,
                pigment_dispersion="pigment dispersion" in u.normalised,
            )
            cards.append(therapy.match(q, eye_label=side))
        agent = next((d for d in u.drugs if d in injections.AGENT_ALIASES), None) or (
            eye.current_agent or None
        )
        if (
            condition in TE_CONDITIONS
            and agent
            and ("treat_and_extend" in intents or eye.current_interval_weeks is not None)
        ):
            activity = injections.VisitActivity(
                intraretinal_fluid=bool(eye.intraretinal_fluid),
                subretinal_fluid=bool(eye.subretinal_fluid),
                new_haemorrhage=bool(eye.new_haemorrhage),
                letters_lost=0,
                intraocular_inflammation=any(
                    w in u.normalised for w in ("intraocular inflammation", "vitritis")
                ),
            )
            given = eye.injections_given if eye.injections_given is not None else u.injection_count
            card = _safe(
                "treat_and_extend",
                injections.plan,
                agent,
                condition,
                given or 0,
                eye.current_interval_weeks,
                activity,
                eye=side,
            )
            if card:
                if given is None:
                    card.missing.append("number of injections given")
                cards.append(card)
        if eye.iop_mmhg is not None and (condition in {"oht", "coag"} or "oht_threshold" in intents):
            card = _safe(
                "oht",
                glaucoma.oht_assessment,
                eye.iop_mmhg,
                eye.cct_um,
                eye=side,
                pigment_dispersion="pigment dispersion" in u.normalised,
            )
            if card:
                cards.append(card)
        baseline = eye.baseline_iop_mmhg or (eye.iop_mmhg if "glaucoma_target" in intents else None)
        if baseline and ("glaucoma_target" in intents or condition == "coag"):
            card = _safe("target_iop", glaucoma.target_pressure, baseline, eye.glaucoma_stage, eye=side)
            if card:
                cards.append(card)
        if len(eye.visual_fields) >= 3:
            points = [(p.years_from_baseline, p.mean_deviation_db) for p in eye.visual_fields]
            card = _safe("field_progression", glaucoma.field_progression, points, ctx.age, eye=side)
            if card:
                cards.append(card)

    weight = ctx.weight_kg or _weight_from_text(u.normalised)
    if "hcq_monitoring" in intents and weight:
        dose = _dose_from_text(u.normalised)
        years = _years_from_text(u.normalised)
        if dose and years is not None:
            card = _safe(
                "hcq",
                toxicity.monitoring_plan,
                weight,
                dose,
                years,
                drug="chloroquine"
                if "chloroquine" in u.normalised and "hydroxychloroquine" not in u.normalised
                else "hydroxychloroquine",
                tamoxifen="tamoxifen" in u.normalised or any("tamoxifen" in m.lower() for m in ctx.medicines),
                egfr=ctx.egfr,
            )
            if card:
                cards.append(card)

    planned = list(
        dict.fromkeys(
            u.drugs
            + [
                i.replace("_", " ")
                for i in u.interventions
                if i in {"cataract_surgery", "intravitreal_injection", "trabeculectomy", "vitrectomy"}
            ]
        )
    )
    if planned and ("safety_screen" in intents or ctx.medicines or ctx.conditions or ctx.allergies):
        extra = [c.replace("_", " ") for c in u.conditions] + [u.normalised]
        cards.append(
            safety_screen.screen(
                safety_screen.ScreenInput(planned=planned, patient=ctx, extra_conditions=extra)
            )
        )

    if "trials" in intents and trial_records is not None:
        cards.append(
            prefilter(
                trial_records,
                u.conditions[0] if u.conditions else None,
                age=ctx.age or u.age,
                sex=None if ctx.sex == "unknown" else ctx.sex,
            )
        )
    return cards


def _weight_from_text(text: str) -> float | None:
    m = re.search(r"(\d{2,3}(?:\.\d)?)\s?kg\b", text)
    return float(m.group(1)) if m else None


def _dose_from_text(text: str) -> float | None:
    m = re.search(r"(\d{2,4})\s?mg\s?(?:a day|daily|per day|od|once daily)?", text)
    if not m:
        return None
    dose = float(m.group(1))
    if re.search(r"(\d{2,4})\s?mg\s?(?:twice daily|bd|two times)", text):
        dose *= 2
    if "weekly" in text or "per week" in text or "a week" in text:
        dose = dose / 7
    return dose


def _years_from_text(text: str) -> float | None:
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s?(?:years?|yrs?)\b(?! old)", text)
    return float(m.group(1)) if m else None
