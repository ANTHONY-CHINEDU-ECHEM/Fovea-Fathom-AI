"""Diabetic retinopathy grading on the NHS Diabetic Eye Screening Programme scale.

Retinopathy grades:
* R0  no retinopathy
* R1  background: microaneurysms, retinal haemorrhages, any exudate
* R2  pre proliferative: venous beading, venous loop or reduplication, intraretinal
      microvascular abnormality (IRMA), multiple deep, round or blot haemorrhages
* R3A active proliferative: new vessels on the disc or elsewhere, preretinal or vitreous
      haemorrhage, preretinal fibrosis with or without tractional detachment, reactivation
      of a treated eye
* R3S stable treated proliferative retinopathy
Maculopathy grades:
* M1  exudate within one disc diameter of the centre of the fovea; a group of exudates within
      the macula; retinal thickening within one disc diameter of the fovea where stereo is
      available; or any microaneurysm or haemorrhage within one disc diameter of the fovea
      only when best visual acuity is 6/12 or worse
* M0  none of the above
The pathway and urgency order are read from ``screening_and_targets.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass

from fovea import knowledge
from fovea.clinical import ToolCard
from fovea.clinical.acuity import parse as parse_acuity

R3A_FEATURES = {
    "new_vessels_disc": "new vessels on the disc",
    "new_vessels_elsewhere": "new vessels elsewhere",
    "preretinal_haemorrhage": "preretinal haemorrhage",
    "vitreous_haemorrhage": "vitreous haemorrhage",
    "preretinal_fibrosis": "preretinal fibrosis",
    "tractional_detachment": "tractional retinal detachment",
    "reactivation_in_treated_eye": "reactivation in a treated eye",
}
R2_FEATURES = {
    "venous_beading": "venous beading",
    "venous_loop": "venous loop or reduplication",
    "irma": "intraretinal microvascular abnormality",
    "multiple_blot_haemorrhages": "multiple deep, round or blot haemorrhages",
}
R1_FEATURES = {
    "microaneurysms": "microaneurysms",
    "retinal_haemorrhages": "retinal haemorrhages",
    "exudates": "exudates",
    "venous_loop_isolated": "isolated venous loop",
}
M1_FEATURES = {
    "exudate_within_1dd": "exudate within one disc diameter of the fovea",
    "exudate_group_in_macula": "group of exudates within the macula",
    "thickening_within_1dd": "retinal thickening within one disc diameter of the fovea",
}


@dataclass
class ScreeningFeatures:
    ungradable: bool = False
    laser_scars_stable: bool = False
    microaneurysms_or_haemorrhage_within_1dd: bool = False
    best_va: str | None = None
    features: frozenset[str] = frozenset()

    @classmethod
    def from_dict(cls, data: dict) -> ScreeningFeatures:
        flags = {k for k, v in data.items() if v is True}
        return cls(
            ungradable=bool(data.get("ungradable")),
            laser_scars_stable=bool(data.get("laser_scars_stable")),
            microaneurysms_or_haemorrhage_within_1dd=bool(
                data.get("microaneurysms_or_haemorrhage_within_1dd")
            ),
            best_va=data.get("best_va"),
            features=frozenset(flags),
        )


def grade(features: ScreeningFeatures, eye: str | None = None) -> ToolCard:
    rules = knowledge.load("screening_and_targets")
    programme = rules.data["diabetic_eye_screening"]
    card = ToolCard(
        tool="dr_grading",
        title="Diabetic eye screening grade",
        summary="",
        eye=eye,
        provenance=rules.provenance,
        references=[programme["source"]],
    )

    if features.ungradable:
        outcome = "U"
        card.working.append("Images recorded as ungradable.")
        r_grade, m_grade = "U", ""
    else:
        found_r3a = sorted(name for key, name in R3A_FEATURES.items() if key in features.features)
        found_r2 = sorted(name for key, name in R2_FEATURES.items() if key in features.features)
        found_r1 = sorted(name for key, name in R1_FEATURES.items() if key in features.features)
        if found_r3a:
            r_grade = "R3A"
            card.working.append("R3A features: " + ", ".join(found_r3a))
        elif features.laser_scars_stable:
            r_grade = "R3S"
            card.working.append("Stable treated proliferative retinopathy with no active features.")
        elif found_r2:
            r_grade = "R2"
            card.working.append("R2 features: " + ", ".join(found_r2))
        elif found_r1:
            r_grade = "R1"
            card.working.append("R1 features: " + ", ".join(found_r1))
        else:
            r_grade = "R0"
            card.working.append("No retinopathy features recorded.")

        found_m1 = sorted(name for key, name in M1_FEATURES.items() if key in features.features)
        va_rule = False
        if features.microaneurysms_or_haemorrhage_within_1dd:
            if features.best_va:
                acuity = parse_acuity(features.best_va)
                if acuity.logmar is not None and acuity.logmar >= 0.30103 - 1e-6:
                    va_rule = True
                    found_m1.append(
                        "microaneurysm or haemorrhage within one disc diameter with best acuity 6/12 or worse"
                    )
                else:
                    card.working.append(
                        "Microaneurysm or haemorrhage within one disc diameter, but best acuity is better than 6/12, so not M1 on that feature alone."
                    )
            else:
                card.missing.append(
                    "best corrected acuity (needed to decide M1 for macular microaneurysms or haemorrhages)"
                )
        m_grade = "M1" if found_m1 else "M0"
        if found_m1:
            card.working.append("M1 features: " + ", ".join(found_m1))
        if va_rule:
            card.working.append(
                "The acuity criterion for macular microaneurysms or haemorrhages was applied."
            )
        outcome = f"{r_grade}{m_grade}"

    outcomes = programme["outcomes"]
    pathway = outcomes.get(outcome, {"pathway": "Follow the local programme pathway.", "referable": False})
    order = programme["urgency_order"]
    rank = order.index(outcome) + 1 if outcome in order else None
    card.summary = f"Grade {outcome}. {pathway['pathway']}"
    card.details = {
        "retinopathy": r_grade,
        "maculopathy": m_grade or None,
        "outcome": outcome,
        "referable": bool(pathway.get("referable")),
        "urgent": bool(pathway.get("urgent")),
        "urgency_rank": rank,
        "urgency_order": order,
    }
    if pathway.get("urgent"):
        card.warn("major", "Active proliferative retinopathy: urgent referral to the hospital eye service.")
    elif pathway.get("referable"):
        card.warn("caution", "Referable result: follow the programme referral pathway.")
    card.warn(
        "info",
        "Grading is decision support for trained graders and does not replace programme quality assurance.",
    )
    return card


def worst_eye(outcomes: list[str]) -> str | None:
    """Return the outcome that needs the most urgent action, using the programme order."""
    order = knowledge.load("screening_and_targets").data["diabetic_eye_screening"]["urgency_order"]
    ranked = [o for o in outcomes if o in order]
    return min(ranked, key=order.index) if ranked else None
