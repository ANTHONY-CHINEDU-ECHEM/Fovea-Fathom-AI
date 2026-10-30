import math

import pytest

from fovea.clinical import ToolInputError
from fovea.clinical.acuity import convert, letter_change, parse


@pytest.mark.parametrize(
    ("value", "logmar"),
    [
        ("6/6", 0.0),
        ("6/12", 0.30103),
        ("6/60", 1.0),
        ("20/40", 0.30103),
        ("20/200", 1.0),
        ("6/96", 1.20412),
        ("6/3", -0.30103),
    ],
)
def test_snellen_to_logmar(value: str, logmar: float) -> None:
    assert parse(value).logmar == pytest.approx(logmar, abs=1e-4)


def test_letter_modifiers_adjust_by_point_zero_two_per_letter() -> None:
    assert parse("6/12+2").logmar == pytest.approx(0.30103 - 0.04, abs=1e-4)
    assert parse("6/9-1").logmar == pytest.approx(math.log10(1.5) + 0.02, abs=1e-4)


def test_etdrs_letters_round_trip() -> None:
    acuity = parse("70 letters")
    assert acuity.logmar == pytest.approx(0.3)
    assert acuity.etdrs_letters == 70
    assert parse("6/12").etdrs_letters == 70
    assert parse("6/60").etdrs_letters == 35


def test_decimal_and_explicit_logmar() -> None:
    assert parse("decimal 0.5").logmar == pytest.approx(0.30103, abs=1e-4)
    assert parse("logMAR 0.48").logmar == pytest.approx(0.48)
    assert parse("0.2 logmar").logmar == pytest.approx(0.2)


def test_snellen_output_snaps_to_chart_lines() -> None:
    card = convert("6/96")
    assert card.details["snellen_metric"] == "6/96"
    assert card.details["snellen_imperial"] == "20/320"
    assert convert("logMAR 1.0").details["snellen_metric"] == "6/60"


def test_low_vision_categories_are_conventions_or_non_numeric() -> None:
    cf = parse("CF")
    assert cf.convention and cf.logmar == pytest.approx(1.9)
    pl = parse("PL")
    assert pl.logmar is None and pl.category == "PL"
    card = convert("NPL")
    assert card.details["within_nice_amd_window"] is False


def test_nice_amd_window_is_inclusive() -> None:
    assert parse("6/12").within_nice_amd_window() is True
    assert parse("6/96").within_nice_amd_window() is True
    assert parse("6/9").within_nice_amd_window() is False
    assert parse("6/120").within_nice_amd_window() is False


def test_letter_change_positive_means_improvement() -> None:
    assert letter_change("6/24", "6/12") == 15
    assert letter_change("6/12", "6/24") == -15


@pytest.mark.parametrize("bad", ["", "six twelve", "6/0", "logmar 4", "120 letters"])
def test_invalid_inputs_raise(bad: str) -> None:
    with pytest.raises(ToolInputError):
        parse(bad)
