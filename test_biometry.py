import pytest

from fovea.clinical import ToolInputError
from fovea.clinical.biometry import (
    BiometryInput,
    calculate,
    srk2_power,
    srkt_power,
    srkt_predicted_refraction,
)


def test_srkt_agrees_with_srk2_for_an_average_eye() -> None:
    # For an average eye (23.5 mm, 44 D, A 118.4) the two formulae agree closely.
    assert srkt_power(23.5, 44.0, 118.4) == pytest.approx(20.04, abs=0.05)
    assert srk2_power(23.5, 44.0, 118.4) == pytest.approx(20.05, abs=0.05)


@pytest.mark.parametrize(
    ("al", "k"), [(21.5, 45.5), (23.0, 43.0), (24.2, 43.5), (24.3, 43.5), (26.5, 42.0), (29.0, 41.5)]
)
def test_predicted_refraction_inverts_power(al: float, k: float) -> None:
    for target in (-2.0, -0.5, 0.0, 0.5):
        power = srkt_power(al, k, 118.7, target)
        assert srkt_predicted_refraction(al, k, 118.7, power) == pytest.approx(target, abs=1e-6)


def test_longer_eyes_need_weaker_lenses_and_steeper_corneas_too() -> None:
    assert srkt_power(26.0, 43.5, 118.4) < srkt_power(23.0, 43.5, 118.4)
    assert srkt_power(23.5, 46.0, 118.4) < srkt_power(23.5, 42.0, 118.4)


def test_long_eye_correction_is_continuous_at_24_2_mm() -> None:
    below = srkt_power(24.2, 43.5, 118.4)
    above = srkt_power(24.2001, 43.5, 118.4)
    assert abs(below - above) < 0.05


def test_card_offers_half_dioptre_table_and_choice() -> None:
    card = calculate(BiometryInput(23.5, 43.5, 44.25, 118.4, -0.5), eye="right")
    powers = [row["iol_power_d"] for row in card.details["table"]]
    assert powers == sorted(powers) and all((p * 2).is_integer() for p in powers)
    assert card.eye == "right"
    assert card.details["suggested_iol_d"] in powers


def test_recheck_triggers() -> None:
    card = calculate(BiometryInput(20.8, 47.6, 48.0, 118.4, 0.0, fellow_axial_length_mm=21.8))
    messages = " ".join(f.message for f in card.findings)
    assert "outside 21.20 to 26.60" in messages
    assert "outside 41 to 47" in messages
    assert "fellow eye by more than 0.7 mm" in messages


def test_toric_prompt_for_corneal_cylinder() -> None:
    card = calculate(BiometryInput(23.5, 42.5, 44.0))
    assert any("toric" in f.message for f in card.findings)


@pytest.mark.parametrize(
    "kwargs",
    [dict(axial_length_mm=15.0), dict(k1_d=60.0), dict(a_constant=100.0), dict(target_refraction_d=-12.0)],
)
def test_implausible_inputs_rejected(kwargs: dict) -> None:
    base = dict(axial_length_mm=23.5, k1_d=44.0, k2_d=44.0, a_constant=118.4, target_refraction_d=0.0)
    base.update(kwargs)
    with pytest.raises(ToolInputError):
        calculate(BiometryInput(**base))
