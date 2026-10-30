"""Hydroxychloroquine and chloroquine retinopathy monitoring.

Applies the Royal College of Ophthalmologists recommendations on monitoring (December 2020):
dose by actual body weight, risk factors (dose above 5 mg/kg/day of hydroxychloroquine or
2.3 mg/kg/day of chloroquine, concomitant tamoxifen, eGFR below 60), annual monitoring from
five years of hydroxychloroquine or from one year with risk factors or with chloroquine, and
no baseline examination for new starters.
"""

from __future__ import annotations

from fovea import knowledge
from fovea.clinical import ToolCard, ToolInputError


def monitoring_plan(
    weight_kg: float,
    daily_dose_mg: float,
    years_on_treatment: float,
    drug: str = "hydroxychloroquine",
    tamoxifen: bool = False,
    egfr: float | None = None,
) -> ToolCard:
    rules = knowledge.load("screening_and_targets")
    cfg = rules.data["hydroxychloroquine"]
    drug_key = drug.strip().lower()
    if drug_key not in {"hydroxychloroquine", "chloroquine"}:
        raise ToolInputError("Drug must be hydroxychloroquine or chloroquine")
    if not 20 <= weight_kg <= 350:
        raise ToolInputError("Weight must be between 20 and 350 kg")
    if not 0 < daily_dose_mg <= 1000:
        raise ToolInputError("Average daily dose must be between 0 and 1000 mg")
    if years_on_treatment < 0:
        raise ToolInputError("Years on treatment cannot be negative")

    per_kg = daily_dose_mg / weight_kg
    limit = float(
        cfg["hcq_max_mg_per_kg_day"] if drug_key == "hydroxychloroquine" else cfg["cq_max_mg_per_kg_day"]
    )
    risks: list[str] = []
    if per_kg > limit:
        risks.append(f"dose {per_kg:.2f} mg/kg/day above {limit:g} mg/kg/day")
    if tamoxifen:
        risks.append("concomitant tamoxifen")
    if egfr is not None and egfr < float(cfg["egfr_threshold"]):
        risks.append(f"eGFR {egfr:g} below {cfg['egfr_threshold']}")
    if drug_key == "chloroquine":
        start = float(cfg["start_years_chloroquine"])
    elif risks:
        start = float(cfg["start_years_with_risk"])
    else:
        start = float(cfg["start_years_standard"])

    due = years_on_treatment >= start
    card = ToolCard(
        tool="hcq_monitoring",
        title=f"{drug_key.capitalize()} retinopathy monitoring",
        summary=(
            f"{per_kg:.2f} mg/kg/day by actual body weight. "
            + (
                f"Annual monitoring is due now (it starts after {start:g} year{'s' if start != 1 else ''} of treatment)."
                if due
                else f"Annual monitoring should start after {start:g} year{'s' if start != 1 else ''} of treatment, "
                f"in about {start - years_on_treatment:.1f} years."
            )
        ),
        provenance=rules.provenance,
        references=[cfg["source"]],
        details={
            "mg_per_kg_day": round(per_kg, 2),
            "limit_mg_per_kg_day": limit,
            "risk_factors": risks,
            "monitoring_start_year": start,
            "monitoring_due": due,
            "tests": cfg["tests"],
        },
        working=[
            f"{daily_dose_mg:g} mg per day / {weight_kg:g} kg = {per_kg:.2f} mg/kg/day",
            "Risk factors: " + (", ".join(risks) if risks else "none recorded"),
            f"Monitoring starts after {start:g} year{'s' if start != 1 else ''} of treatment",
        ],
    )
    if per_kg > limit:
        card.warn(
            "major", f"Dose exceeds {limit:g} mg/kg/day; discuss dose with the prescriber.", cfg["source"]
        )
    card.warn("info", cfg["baseline"])
    card.warn("info", "Tests: " + "; ".join(cfg["tests"]) + ".")
    if egfr is None:
        card.missing.append("eGFR")
    return card
