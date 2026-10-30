"""Medication and procedure safety screen.

Checks planned eye treatment against current medicines, conditions, allergies, age, renal
function, pregnancy and lens status using ``safety_rules.yaml``. Matching works on generic
names, drug classes and procedure identifiers, so ``Timoptol`` planned for someone with asthma
fires the same rule as ``timolol``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from fovea import knowledge
from fovea.clinical import ToolCard
from fovea.clinical.understanding import classes_for, find_drugs, normalise
from fovea.domain import PatientContext

_SEVERITY_ORDER = {"contraindication": 0, "major": 1, "caution": 2, "monitor": 3, "info": 4}
_PROCEDURES = {
    "cataract surgery": "cataract_surgery",
    "phacoemulsification": "cataract_surgery",
    "phaco": "cataract_surgery",
    "intravitreal injection": "intravitreal_injection",
    "intravitreal": "intravitreal_injection",
    "trabeculectomy": "trabeculectomy",
    "vitrectomy": "vitrectomy",
}


@dataclass
class ScreenInput:
    planned: list[str]
    patient: PatientContext = field(default_factory=PatientContext)
    extra_conditions: list[str] = field(default_factory=list)
    lens_status: str | None = None


def _identifiers(names: list[str]) -> set[str]:
    out: set[str] = set()
    for name in names:
        text = normalise(name)
        generics = find_drugs(text)
        out.update(generics)
        out.update(classes_for(generics))
        for phrase, pid in _PROCEDURES.items():
            if phrase in text:
                out.add(pid)
        out.add(text)
    return out


def _contains_any(haystack: list[str], needles: list[str]) -> bool:
    text = " | ".join(normalise(h) for h in haystack)
    return any(re.search(rf"(?<![a-z]){re.escape(normalise(n))}(?![a-z])", text) for n in needles)


def screen(inp: ScreenInput) -> ToolCard:
    rules = knowledge.load("safety_rules")
    patient = inp.patient
    planned = _identifiers(inp.planned)
    current = _identifiers(patient.medicines)
    conditions = [*patient.conditions, *inp.extra_conditions]
    lens = inp.lens_status
    if lens is None:
        lens_values = {eye.lens_status for _, eye in patient.eyes()}
        lens = next(iter(lens_values)) if len(lens_values) == 1 else None

    card = ToolCard(
        tool="safety_screen",
        title="Medication and procedure safety screen",
        summary="",
        provenance=rules.provenance,
        details={"planned": sorted(planned), "checked_rules": len(rules.data["rules"])},
    )
    hits = []
    for rule in rules.data["rules"]:
        when = rule.get("when", {})
        if "planned_any" in when and when["planned_any"] and not planned & set(when["planned_any"]):
            continue
        if "current_any" in when and when["current_any"] and not current & set(when["current_any"]):
            continue
        if "also_current_any" in when and not current & set(when["also_current_any"]):
            continue
        if when.get("conditions_any") and not _contains_any(conditions, when["conditions_any"]):
            continue
        if when.get("allergies_any") and not _contains_any(patient.allergies, when["allergies_any"]):
            continue
        if "age_below" in when and (patient.age is None or patient.age >= when["age_below"]):
            continue
        if "egfr_below" in when and (patient.egfr is None or patient.egfr >= when["egfr_below"]):
            continue
        if when.get("pregnant") and not patient.pregnant:
            continue
        if when.get("lens_status_any") and (lens is None or lens not in when["lens_status_any"]):
            continue
        hits.append(rule)

    hits.sort(key=lambda r: _SEVERITY_ORDER.get(r["severity"], 9))
    for rule in hits:
        card.warn(
            rule["severity"],
            f"{rule['title']}: {' '.join(rule['message'].split())}",
            rule.get("reference", ""),
        )
    if hits:
        worst = hits[0]["severity"]
        card.summary = f"{len(hits)} finding(s); the most serious is a {worst}: {hits[0]['title']}."
    else:
        card.summary = "No configured safety rule fired for the planned treatment and recorded context."
    if not patient.medicines:
        card.missing.append("current medicines")
    if not patient.conditions and not inp.extra_conditions:
        card.missing.append("relevant conditions")
    card.references = ["Summary of Product Characteristics for each medicine", "BNF interactions appendix"]
    card.warn(
        "info",
        "The screen covers a curated subset of eye treatment risks and does not replace the SmPC, the BNF or a pharmacist.",
    )
    return card
