"""Intraocular lens power calculation for cataract surgery planning.

Implements the SRK/T theoretical formula (Retzlaff, Sanders and Kraff, J Cataract Refract
Surg 1990, with the published erratum) and the SRK II regression formula as a cross check.
These calculations are decision support for checking a biometer printout: the biometer's
own optimised constants and the local biometry protocol always take precedence, and the
choice of formula for very short or very long eyes is a matter for the local protocol.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fovea.clinical import ToolCard, ToolInputError

N_AQUEOUS = 1.336
N_CORNEA_CALC = 1.333
VERTEX_MM = 12.0
KERATOMETRIC_INDEX = 337.5

# Biometry recheck triggers widely used in UK practice (Royal College of Ophthalmologists
# cataract surgery guidelines). Local protocols may differ and take precedence.
RECHECK_AXIAL_LENGTH_SHORT = 21.20
RECHECK_AXIAL_LENGTH_LONG = 26.60
RECHECK_K_LOW = 41.0
RECHECK_K_HIGH = 47.0
RECHECK_FELLOW_AXIAL_DIFF = 0.7
RECHECK_FELLOW_K_DIFF = 0.9


@dataclass
class BiometryInput:
    axial_length_mm: float
    k1_d: float
    k2_d: float
    a_constant: float = 118.4
    target_refraction_d: float = 0.0
    fellow_axial_length_mm: float | None = None
    fellow_mean_k_d: float | None = None

    @property
    def mean_k(self) -> float:
        return (self.k1_d + self.k2_d) / 2

    def validate(self) -> None:
        if not 18.0 <= self.axial_length_mm <= 35.0:
            raise ToolInputError("Axial length must be between 18 and 35 mm")
        for k in (self.k1_d, self.k2_d):
            if not 35.0 <= k <= 55.0:
                raise ToolInputError("Keratometry must be between 35 and 55 dioptres")
        if not 110.0 <= self.a_constant <= 122.0:
            raise ToolInputError("A constant must be between 110 and 122")
        if not -10.0 <= self.target_refraction_d <= 4.0:
            raise ToolInputError("Target refraction must be between minus 10 and plus 4 dioptres")


def _srkt_geometry(axial_length: float, mean_k: float, a_constant: float) -> tuple[float, float, float]:
    radius = KERATOMETRIC_INDEX / mean_k
    if axial_length <= 24.2:
        corrected_length = axial_length
    else:
        corrected_length = -3.446 + 1.716 * axial_length - 0.0237 * axial_length**2
    corneal_width = -5.41 + 0.58412 * corrected_length + 0.098 * mean_k
    x = radius**2 - (corneal_width**2) / 4
    corneal_height = radius - math.sqrt(max(x, 0.0))
    acd_constant = 0.62467 * a_constant - 68.747
    offset = acd_constant - 3.336
    estimated_elp = corneal_height + offset
    retinal_thickness = 0.65696 - 0.02029 * axial_length
    optical_length = axial_length + retinal_thickness
    return radius, estimated_elp, optical_length


def srkt_power(
    axial_length: float, mean_k: float, a_constant: float, target_refraction: float = 0.0
) -> float:
    """SRK/T lens power (dioptres) for the given target spectacle refraction."""
    r, c1, lopt = _srkt_geometry(axial_length, mean_k, a_constant)
    na, ncm1, v = N_AQUEOUS, N_CORNEA_CALC - 1.0, VERTEX_MM
    ref = target_refraction
    numerator = 1000 * na * (na * r - ncm1 * lopt - 0.001 * ref * (v * (na * r - ncm1 * lopt) + lopt * r))
    denominator = (lopt - c1) * (na * r - ncm1 * c1 - 0.001 * ref * (v * (na * r - ncm1 * c1) + c1 * r))
    return numerator / denominator


def srkt_predicted_refraction(
    axial_length: float, mean_k: float, a_constant: float, iol_power: float
) -> float:
    """Predicted spectacle refraction (dioptres) for an implanted lens of ``iol_power``."""
    r, c1, lopt = _srkt_geometry(axial_length, mean_k, a_constant)
    na, ncm1, v = N_AQUEOUS, N_CORNEA_CALC - 1.0, VERTEX_MM
    numerator = 1000 * na * (na * r - ncm1 * lopt) - iol_power * (lopt - c1) * (na * r - ncm1 * c1)
    denominator = na * (v * (na * r - ncm1 * lopt) + lopt * r) - 0.001 * iol_power * (lopt - c1) * (
        v * (na * r - ncm1 * c1) + c1 * r
    )
    return numerator / denominator


def srk2_power(
    axial_length: float, mean_k: float, a_constant: float, target_refraction: float = 0.0
) -> float:
    """SRK II regression formula, used only as a plausibility cross check."""
    if axial_length < 20.0:
        a1 = a_constant + 3.0
    elif axial_length < 21.0:
        a1 = a_constant + 2.0
    elif axial_length < 22.0:
        a1 = a_constant + 1.0
    elif axial_length < 24.5:
        a1 = a_constant
    else:
        a1 = a_constant - 0.5
    emmetropic = a1 - 2.5 * axial_length - 0.9 * mean_k
    ratio = 1.25 if emmetropic > 14 else 1.0
    return emmetropic - ratio * target_refraction


def calculate(inp: BiometryInput, eye: str | None = None) -> ToolCard:
    inp.validate()
    mean_k = inp.mean_k
    exact = srkt_power(inp.axial_length_mm, mean_k, inp.a_constant, inp.target_refraction_d)
    check = srk2_power(inp.axial_length_mm, mean_k, inp.a_constant, inp.target_refraction_d)
    centre = round(exact * 2) / 2
    table = []
    for step in (-1.0, -0.5, 0.0, 0.5, 1.0):
        power = centre + step
        refraction = srkt_predicted_refraction(inp.axial_length_mm, mean_k, inp.a_constant, power)
        table.append({"iol_power_d": power, "predicted_refraction_d": round(refraction, 2)})
    closest = min(table, key=lambda row: abs(row["predicted_refraction_d"] - inp.target_refraction_d))

    card = ToolCard(
        tool="biometry",
        title="Intraocular lens power (SRK/T)",
        eye=eye,
        summary=(
            f"SRK/T gives {exact:.2f} D for a target of {inp.target_refraction_d:+.2f} D; "
            f"the nearest half dioptre lens is {closest['iol_power_d']:.1f} D with a predicted refraction of "
            f"{closest['predicted_refraction_d']:+.2f} D."
        ),
        details={
            "srkt_exact_d": round(exact, 2),
            "srk2_cross_check_d": round(check, 2),
            "mean_k_d": round(mean_k, 2),
            "corneal_cylinder_d": round(abs(inp.k2_d - inp.k1_d), 2),
            "table": table,
            "suggested_iol_d": closest["iol_power_d"],
        },
        working=[
            f"Mean K = ({inp.k1_d} + {inp.k2_d}) / 2 = {mean_k:.2f} D; corneal radius = 337.5 / K = {KERATOMETRIC_INDEX / mean_k:.3f} mm",
            f"ACD constant = 0.62467 x {inp.a_constant} minus 68.747 = {0.62467 * inp.a_constant - 68.747:.3f} mm",
            f"SRK/T exact power for target {inp.target_refraction_d:+.2f} D = {exact:.2f} D",
            f"SRK II cross check = {check:.2f} D",
        ],
        provenance="SRK/T (Retzlaff 1990, with erratum); SRK II regression cross check",
        references=[
            "Retzlaff JA, Sanders DR, Kraff MC. Development of the SRK/T intraocular lens implant power calculation formula. J Cataract Refract Surg 1990",
            "NICE NG77 Cataracts in adults: management",
        ],
    )

    al = inp.axial_length_mm
    if al < RECHECK_AXIAL_LENGTH_SHORT or al > RECHECK_AXIAL_LENGTH_LONG:
        card.warn(
            "major",
            f"Axial length {al} mm is outside 21.20 to 26.60 mm; repeat biometry and follow the local formula choice for short or long eyes.",
        )
    if mean_k < RECHECK_K_LOW or mean_k > RECHECK_K_HIGH:
        card.warn(
            "major",
            f"Mean keratometry {mean_k:.2f} D is outside 41 to 47 D; repeat keratometry and consider previous refractive surgery or keratoconus.",
        )
    if abs(exact - check) > 1.0:
        card.warn(
            "caution",
            "SRK/T and SRK II differ by more than 1 D; check the measurements and the biometer printout.",
        )
    if abs(inp.k2_d - inp.k1_d) >= 1.0:
        card.warn(
            "info",
            f"Corneal cylinder of {abs(inp.k2_d - inp.k1_d):.2f} D; consider whether a toric lens is appropriate.",
        )
    if (
        inp.fellow_axial_length_mm is not None
        and abs(inp.fellow_axial_length_mm - al) > RECHECK_FELLOW_AXIAL_DIFF
    ):
        card.warn(
            "major",
            "Axial length differs from the fellow eye by more than 0.7 mm; repeat biometry on both eyes.",
        )
    if inp.fellow_mean_k_d is not None and abs(inp.fellow_mean_k_d - mean_k) > RECHECK_FELLOW_K_DIFF:
        card.warn(
            "major",
            "Mean keratometry differs from the fellow eye by more than 0.9 D; repeat keratometry on both eyes.",
        )
    card.warn(
        "info", "Confirm against the biometer printout with optimised constants before ordering a lens."
    )
    return card
