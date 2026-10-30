"""Glaucoma and ocular hypertension tools.

* :func:`oht_assessment` applies the NICE NG81 treatment threshold of 24 mmHg.
* :func:`target_pressure` proposes a target from the baseline pressure and disease stage
  using local protocol percentages and ceilings (NICE sets no numeric target).
* :func:`field_progression` fits ordinary least squares to visual field mean deviation over
  time, reports the rate in dB per year with a 95 percent confidence interval and a two
  sided p value, and projects when the configured severe loss threshold would be reached.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fovea import knowledge
from fovea.clinical import ToolCard, ToolInputError


def oht_assessment(
    iop_mmhg: float, cct_um: float | None = None, eye: str | None = None, pigment_dispersion: bool = False
) -> ToolCard:
    rules = knowledge.load("screening_and_targets")
    threshold = float(rules.data["glaucoma"]["oht_treatment_iop_mmhg"])
    if not 0 < iop_mmhg <= 80:
        raise ToolInputError("Intraocular pressure must be between 0 and 80 mmHg")
    card = ToolCard(
        tool="oht_assessment",
        title="Ocular hypertension treatment threshold",
        summary="",
        eye=eye,
        provenance=rules.provenance,
        references=["NICE NG81 Glaucoma: diagnosis and management (2017, updated 2022)"],
    )
    meets = iop_mmhg >= threshold
    card.working.append(f"IOP {iop_mmhg:g} mmHg compared with the NG81 threshold of {threshold:g} mmHg.")
    if meets:
        option = (
            "generic prostaglandin analogue drops (SLT is less suitable in pigment dispersion)"
            if pigment_dispersion
            else "360 degree selective laser trabeculoplasty, or generic prostaglandin analogue drops if SLT is unsuitable or declined"
        )
        card.summary = f"IOP {iop_mmhg:g} mmHg meets the NG81 threshold when the person is at risk of visual impairment in their lifetime; first treatment is {option}."
    else:
        card.summary = f"IOP {iop_mmhg:g} mmHg is below the NG81 treatment threshold of {threshold:g} mmHg for ocular hypertension; follow the NG81 monitoring recommendations."
    if cct_um is not None:
        card.working.append(f"Central corneal thickness {cct_um:g} micrometres recorded.")
        if cct_um < 555:
            card.warn(
                "caution",
                "Thinner central corneas are associated with a higher risk of conversion to glaucoma; consider this in the risk discussion. Do not apply a numeric pressure correction.",
                "OHTS",
            )
    else:
        card.missing.append("central corneal thickness")
    card.details = {
        "iop_mmhg": iop_mmhg,
        "threshold_mmhg": threshold,
        "meets_threshold": meets,
        "cct_um": cct_um,
    }
    card.warn("info", rules.data["glaucoma"]["referral_note"])
    return card


def target_pressure(baseline_iop_mmhg: float, stage: str = "unknown", eye: str | None = None) -> ToolCard:
    rules = knowledge.load("screening_and_targets")
    cfg = rules.data["glaucoma"]
    stage = stage if stage in cfg["target_reduction_percent"] else "unknown"
    if not 5 <= baseline_iop_mmhg <= 80:
        raise ToolInputError("Baseline IOP must be between 5 and 80 mmHg")
    reduction = float(cfg["target_reduction_percent"][stage])
    ceiling = float(cfg["target_ceiling_mmhg"][stage])
    by_percent = baseline_iop_mmhg * (1 - reduction / 100)
    target = min(by_percent, ceiling)
    card = ToolCard(
        tool="target_iop",
        title="Target intraocular pressure",
        summary=f"Proposed target for {stage} disease: {math.floor(target):d} mmHg or lower (local protocol default).",
        eye=eye,
        provenance=rules.provenance,
        details={
            "baseline_mmhg": baseline_iop_mmhg,
            "stage": stage,
            "reduction_percent": reduction,
            "ceiling_mmhg": ceiling,
            "target_mmhg": math.floor(target),
        },
        working=[
            f"{reduction:g} percent below baseline {baseline_iop_mmhg:g} mmHg = {by_percent:.1f} mmHg",
            f"Stage ceiling = {ceiling:g} mmHg",
            f"Target = lower of the two, rounded down = {math.floor(target):d} mmHg",
        ],
        references=["Local glaucoma service protocol", "NICE NG81 (no numeric target is set by NICE)"],
    )
    card.warn(
        "caution",
        "Target pressures are local protocol defaults, not NICE values; agree and review the target with the glaucoma service.",
    )
    if stage == "unknown":
        card.missing.append("glaucoma stage (early, moderate or advanced)")
    return card


@dataclass
class Regression:
    slope: float
    intercept: float
    standard_error: float
    p_value: float
    ci_low: float
    ci_high: float
    n: int


def _betacf(a: float, b: float, x: float) -> float:
    max_iterations, eps, fpmin = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > fpmin else fpmin)
    h = d
    for m in range(1, max_iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > fpmin else fpmin
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > fpmin else fpmin
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_bt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    bt = math.exp(log_bt)
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t: float, df: int) -> float:
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    return regularized_incomplete_beta(df / 2, 0.5, x)


def t_critical_95(df: int) -> float:
    """Two sided 95 percent critical value of Student's t by bisection."""
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_two_sided_p(mid, df) > 0.05:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def linear_regression(xs: list[float], ys: list[float]) -> Regression:
    n = len(xs)
    if n < 3:
        raise ToolInputError("At least three visual fields are needed for a rate of progression")
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        raise ToolInputError("Visual fields must be at different times")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    df = n - 2
    sse = sum(r * r for r in residuals)
    se = math.sqrt(sse / df / sxx) if df > 0 else float("inf")
    if se == 0:
        p = 0.0
    else:
        p = t_two_sided_p(slope / se, df)
    tc = t_critical_95(df)
    return Regression(slope, intercept, se, p, slope - tc * se, slope + tc * se, n)


def field_progression(
    points: list[tuple[float, float]], age_years: float | None = None, eye: str | None = None
) -> ToolCard:
    rules = knowledge.load("screening_and_targets")
    cfg = rules.data["glaucoma"]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    reg = linear_regression(xs, ys)
    rates = cfg["progression_rate_db_per_year"]
    if reg.slope <= rates["fast"]:
        category = "fast"
    elif reg.slope <= rates["moderate"]:
        category = "moderate"
    elif reg.slope <= rates["slow"]:
        category = "slow"
    else:
        category = "no measurable progression"
    significant = reg.p_value < 0.05 and reg.slope < 0
    card = ToolCard(
        tool="field_progression",
        title="Visual field rate of progression",
        summary=(
            f"Mean deviation is changing by {reg.slope:+.2f} dB per year (95 percent CI {reg.ci_low:+.2f} to {reg.ci_high:+.2f}, "
            f"p = {reg.p_value:.3f}, {reg.n} fields): {category}{', statistically significant' if significant else ''}."
        ),
        eye=eye,
        provenance=rules.provenance,
        references=[
            "Ordinary least squares regression of mean deviation on time",
            "Local glaucoma service protocol",
        ],
    )
    threshold = float(cfg["blindness_md_threshold_db"])
    latest_x = max(xs)
    latest_fit = reg.intercept + reg.slope * latest_x
    years_to_threshold = None
    if reg.slope < 0 and latest_fit > threshold:
        years_to_threshold = (threshold - latest_fit) / reg.slope
        card.working.append(
            f"At the fitted rate, mean deviation would reach {threshold:g} dB in about {years_to_threshold:.1f} years."
        )
        if age_years is not None:
            reach_age = age_years + years_to_threshold
            card.working.append(f"That corresponds to age {reach_age:.0f}.")
            if reach_age < 90:
                card.warn(
                    "major",
                    "Projected severe field loss within a typical lifetime: review the target pressure and treatment escalation.",
                )
    if reg.n < 5:
        card.warn(
            "caution",
            "Fewer than five fields: rate estimates are imprecise. NG81 and the glaucoma service set the testing frequency.",
        )
    if age_years is None:
        card.missing.append("age (needed to judge risk of visual impairment in the person's lifetime)")
    card.details = {
        "slope_db_per_year": round(reg.slope, 3),
        "ci_95": [round(reg.ci_low, 3), round(reg.ci_high, 3)],
        "p_value": round(reg.p_value, 4),
        "n_fields": reg.n,
        "category": category,
        "significant": significant,
        "years_to_threshold": None if years_to_threshold is None else round(years_to_threshold, 1),
        "threshold_db": threshold,
    }
    card.working.insert(0, f"Fitted line: MD = {reg.intercept:.2f} + ({reg.slope:.3f} x years)")
    return card
