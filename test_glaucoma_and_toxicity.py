import pytest

from fovea.clinical import ToolInputError
from fovea.clinical.glaucoma import (
    field_progression,
    linear_regression,
    oht_assessment,
    t_critical_95,
    t_two_sided_p,
    target_pressure,
)
from fovea.clinical.toxicity import monitoring_plan


def test_student_t_against_tables() -> None:
    assert t_two_sided_p(2.228, 10) == pytest.approx(0.05, abs=5e-4)
    assert t_critical_95(10) == pytest.approx(2.228, abs=1e-3)
    assert t_critical_95(3) == pytest.approx(3.182, abs=1e-3)
    assert t_two_sided_p(0.0, 5) == pytest.approx(1.0)


def test_regression_recovers_known_slope() -> None:
    reg = linear_regression([0, 1, 2, 3, 4], [-1.0, -2.0, -3.0, -4.0, -5.0])
    assert reg.slope == pytest.approx(-1.0)
    assert reg.p_value == pytest.approx(0.0, abs=1e-9)


def test_field_progression_flags_fast_loss_within_lifetime() -> None:
    card = field_progression([(0, -3.0), (1, -5.1), (2, -7.0), (3, -9.2), (4, -11.0)], age_years=55)
    assert card.details["category"] == "fast"
    assert card.details["significant"]
    assert any(f.severity == "major" for f in card.findings)


def test_stable_fields_not_significant() -> None:
    card = field_progression([(0, -2.0), (1, -1.8), (2, -2.1), (3, -1.9)])
    assert card.details["category"] == "no measurable progression"
    assert not card.details["significant"]


def test_too_few_fields_rejected() -> None:
    with pytest.raises(ToolInputError):
        field_progression([(0, -1.0), (1, -2.0)])


def test_ng81_threshold() -> None:
    assert oht_assessment(24).details["meets_threshold"]
    assert not oht_assessment(23.9).details["meets_threshold"]
    card = oht_assessment(26, cct_um=520)
    assert any("Thinner central corneas" in f.message for f in card.findings)
    assert "prostaglandin" in oht_assessment(28, pigment_dispersion=True).summary


def test_target_pressure_uses_lower_of_percent_and_ceiling() -> None:
    assert target_pressure(30, "early").details["target_mmhg"] == 18
    assert target_pressure(20, "early").details["target_mmhg"] == 16
    assert target_pressure(22, "advanced").details["target_mmhg"] == 12


def test_hcq_standard_and_risk_factor_starts() -> None:
    standard = monitoring_plan(70, 300, 2)
    assert standard.details["monitoring_start_year"] == 5 and not standard.details["monitoring_due"]
    high_dose = monitoring_plan(60, 400, 1.5)
    assert high_dose.details["mg_per_kg_day"] == pytest.approx(6.67, abs=0.01)
    assert high_dose.details["monitoring_start_year"] == 1 and high_dose.details["monitoring_due"]
    assert monitoring_plan(80, 200, 2, tamoxifen=True).details["monitoring_start_year"] == 1
    assert monitoring_plan(80, 200, 2, egfr=45).details["monitoring_start_year"] == 1


def test_chloroquine_always_from_one_year_with_lower_limit() -> None:
    card = monitoring_plan(70, 250, 0.5, drug="chloroquine")
    assert card.details["limit_mg_per_kg_day"] == 2.3
    assert card.details["monitoring_start_year"] == 1


def test_hcq_rejects_implausible_values() -> None:
    with pytest.raises(ToolInputError):
        monitoring_plan(10, 200, 1)
    with pytest.raises(ToolInputError):
        monitoring_plan(70, 200, 1, drug="quinine")
