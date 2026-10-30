"""NICE aligned treatment option matcher.

Reads ``therapy_matrix.yaml`` and, for one eye's condition and findings, returns each option
NICE has issued guidance on, with its guidance number, status, whether the eye meets the
attached criteria (yes, no or unknown), the criteria that were not met and the information
that is missing. Options are ordered so the clinician sees eligible first line options first.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from fovea import knowledge
from fovea.clinical import ToolCard
from fovea.clinical.acuity import parse as parse_acuity
from fovea.domain import EyeContext

Eligibility = Literal["meets_criteria", "does_not_meet", "unknown", "not_applicable"]
_STATUS_LABEL = {
    "recommended": "Recommended",
    "recommended_with_criteria": "Recommended with criteria",
    "research_only": "Only in research",
    "not_recommended": "Not recommended",
    "terminated": "Terminated appraisal",
    "check_appraisal": "Check the appraisal",
}
_STATUS_ORDER = [
    "recommended_with_criteria",
    "recommended",
    "check_appraisal",
    "research_only",
    "not_recommended",
    "terminated",
]


@dataclass
class OptionResult:
    id: str
    agent: str
    guidance: str
    title: str
    status: str
    status_label: str
    line: str
    eligibility: Eligibility
    unmet: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    note: str = ""
    pivotal: list[str] = field(default_factory=list)
    published: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TherapyQuery:
    condition: str
    eye: EyeContext | None = None
    subtype: str | None = None
    prior_failure: str | None = None
    pigment_dispersion: bool = False
    line: str | None = None


def _check(option: dict[str, Any], q: TherapyQuery) -> tuple[Eligibility, list[str], list[str]]:
    criteria = option.get("criteria") or {}
    eye = q.eye or EyeContext()
    unmet: list[str] = []
    missing: list[str] = []
    if not criteria:
        return "unknown" if option["status"] == "check_appraisal" else "not_applicable", unmet, missing

    if "bcva_best" in criteria or criteria.get("outside_window"):
        best = parse_acuity(criteria.get("bcva_best", "6/12")).logmar or 0.30103
        worst = parse_acuity(criteria.get("bcva_worst", "6/96")).logmar or 1.20412
        if not eye.bcva:
            missing.append("best corrected visual acuity")
        else:
            acuity = parse_acuity(eye.bcva)
            if acuity.logmar is None:
                unmet.append(f"acuity recorded as {eye.bcva} has no numeric value")
            else:
                inside = best - 1e-6 <= acuity.logmar <= worst + 1e-6
                if criteria.get("outside_window"):
                    if inside:
                        return (
                            "not_applicable",
                            ["acuity is within 6/12 to 6/96, so the appraisal criteria apply instead"],
                            missing,
                        )
                    if acuity.logmar > worst:
                        unmet.append(
                            "acuity 6/96 or worse: consider only if an overall benefit to visual function is expected"
                        )
                elif not inside:
                    unmet.append(
                        f"acuity {eye.bcva} is outside {criteria.get('bcva_best')} to {criteria.get('bcva_worst')}"
                    )
    if criteria.get("no_permanent_foveal_damage"):
        if eye.permanent_foveal_damage is None:
            missing.append("whether there is permanent structural damage to the central fovea")
        elif eye.permanent_foveal_damage:
            unmet.append("permanent structural damage to the central fovea")
    if "max_lesion_disc_areas" in criteria:
        if eye.lesion_disc_areas is None:
            missing.append("lesion size in disc areas")
        elif eye.lesion_disc_areas > float(criteria["max_lesion_disc_areas"]):
            unmet.append(f"lesion larger than {criteria['max_lesion_disc_areas']} disc areas")
    if criteria.get("recent_progression"):
        if eye.recent_progression is None:
            missing.append("evidence of recent presumed disease progression")
        elif not eye.recent_progression:
            unmet.append("no evidence of recent disease progression")
    if "min_cst_um" in criteria:
        if eye.central_subfield_thickness_um is None:
            missing.append("central retinal thickness at the start of treatment")
        elif eye.central_subfield_thickness_um < float(criteria["min_cst_um"]):
            unmet.append(f"central retinal thickness below {criteria['min_cst_um']} micrometres")
    if "lens_status" in criteria and eye.lens_status not in criteria["lens_status"]:
        if eye.lens_status == "unknown":
            missing.append("lens status")
        else:
            unmet.append(f"lens status {eye.lens_status} is not covered")
    if "requires_prior_failure" in criteria:
        if q.prior_failure is None:
            missing.append(f"response to {criteria['requires_prior_failure'].replace('_', ' ')}")
        elif q.prior_failure not in {criteria["requires_prior_failure"], "any"}:
            unmet.append(
                f"requires insufficient response to {criteria['requires_prior_failure'].replace('_', ' ')}"
            )
    if "subtype" in criteria:
        if q.subtype is None:
            missing.append("occlusion type (central or branch)")
        elif q.subtype != criteria["subtype"]:
            return "not_applicable", [f"applies to {criteria['subtype'].upper()} only"], missing
    if "min_iop_mmhg" in criteria:
        if eye.iop_mmhg is None:
            missing.append("intraocular pressure")
        elif eye.iop_mmhg < float(criteria["min_iop_mmhg"]):
            unmet.append(f"IOP below {criteria['min_iop_mmhg']} mmHg")
    if criteria.get("not_pigment_dispersion") and q.pigment_dispersion:
        unmet.append("associated with pigment dispersion syndrome, where drops are more suitable")
    if criteria.get("stage") and eye.glaucoma_stage != criteria["stage"]:
        if eye.glaucoma_stage == "unknown":
            missing.append("glaucoma stage")
        else:
            unmet.append(f"applies to {criteria['stage']} disease")

    if unmet:
        return "does_not_meet", unmet, missing
    if missing:
        return "unknown", unmet, missing
    return "meets_criteria", unmet, missing


def match(q: TherapyQuery, eye_label: str | None = None) -> ToolCard:
    rules = knowledge.load("therapy_matrix")
    results: list[OptionResult] = []
    for option in rules.data["options"]:
        if option["condition"] != q.condition:
            continue
        if q.line and option.get("line") != q.line:
            continue
        eligibility, unmet, missing = _check(option, q)
        results.append(
            OptionResult(
                id=option["id"],
                agent=option["agent"],
                guidance=option["guidance"],
                title=option["title"],
                status=option["status"],
                status_label=_STATUS_LABEL[option["status"]],
                line=option.get("line", ""),
                eligibility=eligibility,
                unmet=unmet,
                missing=missing,
                note=" ".join(str(option.get("note", "")).split()),
                pivotal=list(option.get("pivotal", [])),
                published=str(option.get("published", "")),
            )
        )
    order = {"meets_criteria": 0, "unknown": 1, "not_applicable": 2, "does_not_meet": 3}
    results.sort(
        key=lambda r: (r.line != "first", order[r.eligibility], _STATUS_ORDER.index(r.status), r.guidance)
    )

    card = ToolCard(
        tool="therapy_options",
        title="NICE aligned treatment options",
        summary="",
        eye=eye_label,
        provenance=rules.provenance,
        details={"condition": q.condition, "options": [r.to_dict() for r in results]},
        references=sorted({f"NICE {r.guidance}" for r in results}),
    )
    if not results:
        card.summary = f"No NICE guidance options are configured for {q.condition.replace('_', ' ')}."
        return card
    eligible = [r for r in results if r.eligibility == "meets_criteria"]
    if eligible:
        names = ", ".join(f"{r.agent} ({r.guidance})" for r in eligible[:4])
        card.summary = f"{len(eligible)} option(s) meet the recorded criteria: {names}. Where several are suitable, NICE advises the least expensive."
    else:
        card.summary = (
            f"{len(results)} NICE option(s) found; none can be confirmed against the recorded findings yet."
        )
    missing = sorted({m for r in results for m in r.missing})
    card.missing = missing
    if any(r.status == "check_appraisal" for r in results):
        card.warn(
            "caution",
            "Some statuses could not be confirmed from the guidance text and are shown as check the appraisal.",
        )
    card.warn(
        "info",
        "Treatment decisions remain with the clinician and the patient; criteria are summarised from NICE guidance.",
    )
    return card
