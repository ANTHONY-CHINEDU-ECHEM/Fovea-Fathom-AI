import pytest

from fovea.clinical import ToolInputError
from fovea.clinical.injections import VisitActivity, plan
from fovea.clinical.screening import ScreeningFeatures, grade, worst_eye


def _grade(**flags):  # type: ignore[no-untyped-def]
    return grade(ScreeningFeatures.from_dict(flags)).details


@pytest.mark.parametrize(
    ("flags", "outcome"),
    [
        ({}, "R0M0"),
        ({"microaneurysms": True}, "R1M0"),
        ({"irma": True}, "R2M0"),
        ({"venous_beading": True, "exudate_within_1dd": True}, "R2M1"),
        ({"new_vessels_disc": True}, "R3AM0"),
        ({"vitreous_haemorrhage": True, "exudate_group_in_macula": True}, "R3AM1"),
        ({"laser_scars_stable": True}, "R3SM0"),
        ({"ungradable": True}, "U"),
    ],
)
def test_grading_outcomes(flags: dict, outcome: str) -> None:
    assert _grade(**flags)["outcome"] == outcome


def test_r3a_wins_over_stable_treated() -> None:
    assert _grade(laser_scars_stable=True, new_vessels_elsewhere=True)["outcome"] == "R3AM0"


def test_macular_microaneurysm_needs_acuity_6_12_or_worse() -> None:
    worse = _grade(microaneurysms=True, microaneurysms_or_haemorrhage_within_1dd=True, best_va="6/18")
    better = _grade(microaneurysms=True, microaneurysms_or_haemorrhage_within_1dd=True, best_va="6/9")
    at_limit = _grade(microaneurysms=True, microaneurysms_or_haemorrhage_within_1dd=True, best_va="6/12")
    assert worse["maculopathy"] == "M1" and at_limit["maculopathy"] == "M1"
    assert better["maculopathy"] == "M0"


def test_missing_acuity_is_reported() -> None:
    card = grade(
        ScreeningFeatures.from_dict(
            {"microaneurysms": True, "microaneurysms_or_haemorrhage_within_1dd": True}
        )
    )
    assert card.missing


def test_urgency_and_worst_eye() -> None:
    details = _grade(new_vessels_disc=True, exudate_within_1dd=True)
    assert details["urgent"] and details["urgency_rank"] == 1
    assert worst_eye(["R1M0", "R2M1", "R0M0"]) == "R2M1"
    assert worst_eye(["U", "R3SM0"]) == "U"


def test_loading_phase() -> None:
    card = plan("Eylea", "wet_amd", 1, None, VisitActivity())
    assert card.details["phase"] == "loading" and card.details["next_interval_weeks"] == 4


def test_extend_when_dry_and_cap_at_maximum() -> None:
    assert plan("aflibercept", "wet_amd", 6, 10, VisitActivity()).details["next_interval_weeks"] == 12
    assert plan("aflibercept", "wet_amd", 9, 16, VisitActivity()).details["next_interval_weeks"] == 16


def test_shorten_when_active_and_floor_at_minimum() -> None:
    active = VisitActivity(subretinal_fluid=True)
    assert plan("faricimab", "dmo", 8, 12, active).details["next_interval_weeks"] == 8
    floor = plan("aflibercept", "wet_amd", 8, 8, active)
    assert floor.details["next_interval_weeks"] == 8
    assert any("switching" in f.message for f in floor.findings)


def test_letter_loss_counts_as_activity() -> None:
    assert VisitActivity(letters_lost=5).active
    assert not VisitActivity(letters_lost=4).active


def test_inflammation_withholds_injection() -> None:
    card = plan("brolucizumab", "wet_amd", 5, 12, VisitActivity(intraocular_inflammation=True))
    assert card.details["next_interval_weeks"] is None
    assert {f.severity for f in card.findings} >= {"contraindication", "major"}


def test_unknown_regimen_rejected() -> None:
    with pytest.raises(ToolInputError):
        plan("bevacizumab", "wet_amd", 3, 8, VisitActivity())
    with pytest.raises(ToolInputError):
        plan("brolucizumab", "rvo", 3, 8, VisitActivity())
