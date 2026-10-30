from fovea.domain import Chunk, EvidenceGrade, ScoredChunk, SourceType
from fovea.generation.citations import figures_in, split_sentences, validate
from fovea.generation.faithfulness import assess
from fovea.generation.laterality import check, eyes_named


def _passage(text: str, drugs: list[str] | None = None) -> ScoredChunk:
    chunk = Chunk(
        id="c",
        doc_id="d",
        text=text,
        title="Faricimab for treating diabetic macular oedema",
        url="u",
        source=SourceType.NICE_TA,
        grade=EvidenceGrade.UK_NATIONAL_GUIDANCE,
        drugs=drugs or ["faricimab"],
        conditions=["dmo"],
    )
    return ScoredChunk(chunk=chunk, score=1.0)


SOURCE = _passage(
    "Faricimab is recommended only if the eye has a central retinal thickness of 400 micrometres or more at the start of treatment."
)


def test_split_reattaches_trailing_citations() -> None:
    assert split_sentences("First fact. [1] Second fact [2].") == ["First fact. [1]", "Second fact [2]."]


def test_invalid_citations_removed() -> None:
    report = validate("Faricimab needs a central retinal thickness of 400 micrometres [1][7].", [SOURCE])
    assert report.invalid_citations == [7]
    assert "[7]" not in report.answer


def test_supported_figure_passes_numerically() -> None:
    report = validate(
        "Faricimab needs a central retinal thickness of 400.0 micrometres or more [1].", [SOURCE]
    )
    assert report.unsupported_figures == []
    assert report.coverage == 1.0


def test_unsupported_figure_flagged_in_answer() -> None:
    report = validate("Faricimab needs a central retinal thickness of 350 micrometres or more [1].", [SOURCE])
    assert report.unsupported_figures == ["350 micrometres"]
    assert "figure not found in the cited source" in report.answer


def test_uncited_sentence_lowers_coverage() -> None:
    report = validate(
        "Faricimab is recommended for DMO [1]. It is given every eight weeks forever.", [SOURCE]
    )
    assert report.coverage == 0.5


def test_clinical_judgement_line_not_counted() -> None:
    report = validate(
        "Faricimab is recommended for diabetic macular oedema [1].\n\nClinical judgement: check the SmPC.",
        [SOURCE],
    )
    assert report.coverage == 1.0


def test_figure_patterns() -> None:
    labels = [
        label
        for label, _ in figures_in("6/12 vision, 24 mmHg, 16 weeks, 5 mg/kg, hazard ratio 0.44, 45 percent")
    ]
    assert "6/12" in labels and "24 mmHg" in labels and "16 weeks" in labels and "hazard ratio 0.44" in labels


def test_faithfulness_detects_drug_swap() -> None:
    supported = assess(
        validate("Faricimab is recommended when central retinal thickness is 400 micrometres [1].", [SOURCE]),
        [SOURCE],
    )
    swapped = assess(
        validate("Brolucizumab is preferred over aflibercept in uveitis for all patients [1].", [SOURCE]),
        [SOURCE],
    )
    assert supported.score == 1.0
    assert swapped.score == 0.0


def test_laterality() -> None:
    assert eyes_named("Treat the RE today; OS stable") == {"right", "left"}
    assert "both" in eyes_named("bilateral disease")
    assert eyes_named("The cost of treatment") == set()
    assert not check("Plan for the left eye?", [], "Inject the right eye [1].").consistent
    assert check("Plan for the left eye?", [], "Inject the left eye [1].").consistent
    assert check("Plan for both eyes?", [], "Right eye first, then the left eye [1].").consistent
