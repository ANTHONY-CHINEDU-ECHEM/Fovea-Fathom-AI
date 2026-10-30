from fovea.clinical.safety_screen import ScreenInput, screen
from fovea.clinical.therapy import TherapyQuery, match
from fovea.domain import EyeContext, PatientContext


def _options(card):  # type: ignore[no-untyped-def]
    return {o["id"]: o for o in card.details["options"]}


def test_wet_amd_eye_meeting_every_criterion() -> None:
    eye = EyeContext(bcva="6/18", permanent_foveal_damage=False, lesion_disc_areas=4, recent_progression=True)
    options = _options(match(TherapyQuery("wet_amd", eye)))
    for oid in ("wet_amd_aflibercept", "wet_amd_ranibizumab", "wet_amd_faricimab", "wet_amd_brolucizumab"):
        assert options[oid]["eligibility"] == "meets_criteria"
    assert options["wet_amd_outside_window"]["eligibility"] == "not_applicable"


def test_wet_amd_outside_acuity_window() -> None:
    eye = EyeContext(
        bcva="6/120", permanent_foveal_damage=False, lesion_disc_areas=4, recent_progression=True
    )
    options = _options(match(TherapyQuery("wet_amd", eye)))
    assert options["wet_amd_aflibercept"]["eligibility"] == "does_not_meet"
    assert (
        "better seeing eye" in " ".join(options["wet_amd_outside_window"]["unmet"])
        or options["wet_amd_outside_window"]["unmet"]
    )


def test_missing_information_listed() -> None:
    card = match(TherapyQuery("wet_amd", EyeContext(bcva="6/24")))
    assert "lesion size in disc areas" in card.missing


def test_dmo_thickness_threshold() -> None:
    thin = _options(
        match(TherapyQuery("dmo", EyeContext(central_subfield_thickness_um=380, lens_status="phakic")))
    )
    thick = _options(
        match(TherapyQuery("dmo", EyeContext(central_subfield_thickness_um=420, lens_status="phakic")))
    )
    assert thin["dmo_faricimab"]["eligibility"] == "does_not_meet"
    assert thick["dmo_faricimab"]["eligibility"] == "meets_criteria"


def test_dexamethasone_dmo_requires_prior_failure() -> None:
    eye = EyeContext(lens_status="phakic")
    unknown = _options(match(TherapyQuery("dmo", eye)))
    known = _options(match(TherapyQuery("dmo", eye, prior_failure="non_corticosteroid")))
    assert unknown["dmo_dexamethasone"]["eligibility"] == "unknown"
    assert known["dmo_dexamethasone"]["eligibility"] == "meets_criteria"


def test_rvo_subtype_routing() -> None:
    options = _options(match(TherapyQuery("rvo", EyeContext(), subtype="brvo")))
    assert options["rvo_aflibercept_crvo"]["eligibility"] == "not_applicable"
    assert options["rvo_faricimab"]["status"] == "recommended"


def test_glaucoma_slt_and_pigment_dispersion() -> None:
    eye = EyeContext(iop_mmhg=26)
    assert _options(match(TherapyQuery("oht", eye)))["oht_slt"]["eligibility"] == "meets_criteria"
    blocked = _options(match(TherapyQuery("oht", eye, pigment_dispersion=True)))
    assert blocked["oht_slt"]["eligibility"] == "does_not_meet"
    assert (
        _options(match(TherapyQuery("oht", EyeContext(iop_mmhg=21))))["oht_slt"]["eligibility"]
        == "does_not_meet"
    )


def test_unknown_condition_returns_empty_card() -> None:
    assert "No NICE guidance options" in match(TherapyQuery("keratoconus")).summary


def _severities(card):  # type: ignore[no-untyped-def]
    return {f.message.split(":")[0]: f.severity for f in card.findings}


def test_brand_name_beta_blocker_in_asthma() -> None:
    card = screen(ScreenInput(["Timoptol"], PatientContext(conditions=["Asthma"])))
    assert (
        _severities(card)["Topical beta blocker with asthma or reactive airways disease"]
        == "contraindication"
    )


def test_sulfonamide_allergy_and_renal_function() -> None:
    ctx = PatientContext(allergies=["sulphonamide"], egfr=22)
    found = _severities(screen(ScreenInput(["Diamox"], ctx)))
    assert "Carbonic anhydrase inhibitor with sulfonamide hypersensitivity" in found
    assert "Acetazolamide with severe renal impairment" in found


def test_cataract_surgery_with_tamsulosin_and_anticoagulant() -> None:
    ctx = PatientContext(medicines=["tamsulosin 400 micrograms", "apixaban 5 mg"])
    found = _severities(screen(ScreenInput(["cataract surgery"], ctx)))
    assert found["Cataract surgery with a systemic alpha one blocker"] == "major"
    assert "Eye procedure in a person taking an anticoagulant or antiplatelet" in found


def test_brimonidine_infant_and_pga_pregnancy() -> None:
    assert "Brimonidine in children under two years" in _severities(
        screen(ScreenInput(["brimonidine"], PatientContext(age=1)))
    )
    assert "Prostaglandin analogue in pregnancy" in _severities(
        screen(ScreenInput(["latanoprost"], PatientContext(pregnant=True)))
    )


def test_hcq_with_tamoxifen_needs_both_medicines() -> None:
    both = _severities(
        screen(ScreenInput(["review"], PatientContext(medicines=["hydroxychloroquine", "tamoxifen"])))
    )
    one = _severities(screen(ScreenInput(["review"], PatientContext(medicines=["hydroxychloroquine"]))))
    assert "Hydroxychloroquine with tamoxifen" in both
    assert "Hydroxychloroquine with tamoxifen" not in one


def test_clean_screen() -> None:
    card = screen(
        ScreenInput(["latanoprost"], PatientContext(medicines=["ramipril"], conditions=["hypertension"]))
    )
    assert card.summary.startswith("No configured safety rule fired")
