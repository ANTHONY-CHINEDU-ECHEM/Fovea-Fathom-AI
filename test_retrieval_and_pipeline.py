from pathlib import Path

from fovea.clinical.understanding import understand
from fovea.config import Settings
from fovea.domain import PatientContext
from fovea.generation.pipeline import AnswerPipeline, AskInput
from fovea.retrieval.hybrid import HybridRetriever
from fovea.retrieval.index import KnowledgeIndex


def _top_docs(index: KnowledgeIndex, settings: Settings, question: str, k: int = 3) -> list[str]:
    return [
        p.chunk.doc_id
        for p in HybridRetriever(index, settings).retrieve(understand(question), top_k=k).passages
    ]


def test_index_built_from_seed(index: KnowledgeIndex) -> None:
    assert len(index) > 50
    assert index.manifest["superseded_chunks"] >= 3
    assert index.trials


def test_index_round_trip(index: KnowledgeIndex, settings: Settings) -> None:
    loaded = KnowledgeIndex.load(Path(settings.index_dir), settings)
    assert len(loaded) == len(index)
    assert _top_docs(loaded, settings, "faricimab diabetic macular oedema")[0] == "nice-ta799"


def test_condition_priors_keep_dmo_and_amd_apart(index: KnowledgeIndex, settings: Settings) -> None:
    assert _top_docs(index, settings, "Is faricimab recommended for wet AMD?")[0] == "nice-ta800"
    assert (
        _top_docs(index, settings, "Is faricimab recommended for diabetic macular oedema?")[0] == "nice-ta799"
    )


def test_superseded_guidance_demoted(index: KnowledgeIndex, settings: Settings) -> None:
    docs = _top_docs(index, settings, "dexamethasone intravitreal implant diabetic macular oedema", k=5)
    assert docs.index("nice-ta824") < docs.index("nice-ta349")


def test_named_trial_is_retrieved(index: KnowledgeIndex, settings: Settings) -> None:
    assert "pubmed-12049574" in _top_docs(index, settings, "What did OHTS show?", k=3)
    assert "pubmed-25692915" in _top_docs(index, settings, "Protocol T results", k=3)


def test_max_two_chunks_per_document(index: KnowledgeIndex, settings: Settings) -> None:
    docs = _top_docs(index, settings, "NG82 anti VEGF stopping switching referral monitoring", k=8)
    assert max(docs.count(d) for d in docs) <= 2


def test_answer_is_cited_and_grounded(pipeline: AnswerPipeline) -> None:
    final = pipeline.ask(AskInput("Is faricimab recommended for diabetic macular oedema?"))["final"]
    assert final["status"] == "answered"
    assert final["grounding"]["grounded"]
    assert "[1]" in final["answer"]
    assert final["answer"].rstrip().splitlines()[-1].startswith("Clinical judgement:")


def test_emergency_streams_before_sources(pipeline: AnswerPipeline) -> None:
    events = [e.type for e in pipeline.events(AskInput("Bleach splashed in the right eye"))]
    assert events[:2] == ["meta", "emergency"]
    assert events.index("emergency") < events.index("sources")


def test_abstains_on_unknown_topic(pipeline: AnswerPipeline) -> None:
    final = pipeline.ask(AskInput("Is pegcetacoplan recommended for geographic atrophy?"))["final"]
    assert final["status"] == "abstained"


def test_out_of_scope(pipeline: AnswerPipeline) -> None:
    assert pipeline.ask(AskInput("Best way to treat a sprained ankle?"))["final"]["status"] == "out_of_scope"


def test_redaction_happens_before_anything_else(pipeline: AnswerPipeline) -> None:
    result = pipeline.ask(
        AskInput("Mrs Ann Lee, NHS number 943 476 5919: is aflibercept recommended for wet AMD?")
    )
    assert "943 476 5919" not in result["meta"]["redacted_question"]
    assert "Ann Lee" not in result["final"]["question"]


def test_tools_run_per_eye(pipeline: AnswerPipeline) -> None:
    ctx = PatientContext.model_validate(
        {
            "right": {"diagnosis": "wet AMD", "bcva": "6/18"},
            "left": {"diagnosis": "diabetic macular oedema", "central_subfield_thickness_um": 450},
        }
    )
    tools = pipeline.ask(AskInput("Which NICE options apply to each eye?", ctx))["tools"]
    eyes = {(t["tool"], t["eye"]) for t in tools}
    assert ("therapy_options", "right") in eyes and ("therapy_options", "left") in eyes
    left = next(t for t in tools if t["tool"] == "therapy_options" and t["eye"] == "left")
    assert left["details"]["condition"] == "dmo"


def test_source_filters(pipeline: AnswerPipeline) -> None:
    result = pipeline.ask(
        AskInput("faricimab diabetic macular oedema evidence", filters={"source": ["pubmed"]})
    )
    assert result["sources"] and all(s["source"] == "pubmed" for s in result["sources"])


def test_question_findings_complete_structured_eye_context(pipeline: AnswerPipeline) -> None:
    ctx = PatientContext.model_validate({"right": {"diagnosis": "wet AMD", "bcva": "6/18"}})
    question = (
        "Right eye on aflibercept, 6 injections, interval 10 weeks, subretinal fluid today. Next interval?"
    )
    tools = pipeline.ask(AskInput(question, ctx))["tools"]
    plan = next(t for t in tools if t["tool"] == "treat_and_extend")
    assert plan["eye"] == "right"
    assert plan["details"]["disease_active"] is True
    assert plan["details"]["next_interval_weeks"] == 8
    assert not plan["missing"]


def test_negated_fluid_is_not_activity(pipeline: AnswerPipeline) -> None:
    question = "Wet AMD on faricimab, 8 injections, interval 12 weeks, no subretinal fluid. Next interval?"
    plan = next(t for t in pipeline.ask(AskInput(question))["tools"] if t["tool"] == "treat_and_extend")
    assert plan["details"]["next_interval_weeks"] == 16
