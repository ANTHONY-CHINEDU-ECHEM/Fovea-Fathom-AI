import json

import httpx
import pytest

from fovea.domain import Document, EvidenceGrade, Licence, SourceType
from ingestion.pipeline import load_seed, process
from ingestion.processing import currency
from ingestion.processing.chunker import chunk_document
from ingestion.processing.cleaner import clean
from ingestion.processing.dedup import deduplicate, hamming, simhash
from ingestion.processing.grader import grade
from ingestion.processing.tagger import tag_document
from ingestion.sources.base import PoliteClient
from ingestion.sources.clinicaltrials import parse_study
from ingestion.sources.europepmc import parse_result
from ingestion.sources.openfda import parse_label
from ingestion.sources.pubmed import parse_efetch


def _doc(**kwargs) -> Document:  # type: ignore[no-untyped-def]
    base = dict(id="d1", source=SourceType.PUBMED, title="T", url="u", text="text")
    base.update(kwargs)
    return Document(**base)


def test_seed_snapshot_is_complete_and_traceable() -> None:
    docs = load_seed()
    assert len(docs) >= 50
    assert all(d.url.startswith("https://") for d in docs)
    assert all(d.verification for d in docs)
    ids = [d.id for d in docs]
    assert len(ids) == len(set(ids))


def test_cleaner_keeps_clinical_tokens() -> None:
    text = clean("<p>CRT &ge;400&nbsp;µm, 6/12, 24 mmHg, R3A</p><script>x()</script>")
    for token in ("≥400", "6/12", "24 mmHg", "R3A"):
        assert token in text
    assert "x()" not in text


def test_negation_aware_tagging() -> None:
    doc = tag_document(
        _doc(
            title="Retinal vein occlusion outcomes",
            text="Patients without diabetic macular oedema were included. Aflibercept was given.",
        )
    )
    assert "rvo" in doc.conditions and "dmo" not in doc.conditions
    assert doc.drugs == ["aflibercept"]


def test_grading_ladder() -> None:
    assert grade(SourceType.NICE_TA) == EvidenceGrade.UK_NATIONAL_GUIDANCE
    assert grade(SourceType.PUBMED, ["Meta-Analysis"]) == EvidenceGrade.SYSTEMATIC_REVIEW
    assert grade(SourceType.PUBMED, ["Randomized Controlled Trial"]) == EvidenceGrade.RANDOMISED_TRIAL
    assert grade(SourceType.PUBMED, ["Case Reports"]) == EvidenceGrade.CASE_SERIES
    assert grade(SourceType.CLINICAL_TRIAL) == EvidenceGrade.EXPERT_OPINION


def test_simhash_dedup() -> None:
    text = "Faricimab was non inferior to aflibercept in diabetic macular oedema at one year in two phase three trials."
    assert hamming(simhash(text), simhash(text + " ")) == 0
    a = _doc(id="a", text=text, grade=EvidenceGrade.RANDOMISED_TRIAL)
    b = _doc(id="b", source=SourceType.EUROPE_PMC, text=text)
    kept, removed = deduplicate([b, a])
    assert removed == 1 and kept[0].id == "a"
    same_pmid = [
        _doc(id="x", text="one", identifiers={"pmid": "1"}),
        _doc(id="y", text="two entirely different", identifiers={"pmid": "1"}),
    ]
    assert deduplicate(same_pmid)[1] == 1


def test_currency_marks_superseded() -> None:
    docs = [
        _doc(id="nice-ta349", source=SourceType.NICE_TA, identifiers={"guidance": "TA349"}),
        _doc(id="nice-ta824", identifiers={"guidance": "TA824"}),
    ]
    assert currency.apply(docs) == 1
    assert docs[0].superseded_by == "TA824" and docs[1].superseded_by is None


def test_chunker_respects_sections_and_inherits_provenance() -> None:
    long = " ".join(f"Sentence number {i} about aflibercept in wet AMD." for i in range(60))
    doc = _doc(
        sections=[("Treatment", long), ("Monitoring", "Both eyes are monitored with OCT.")],
        licence=Licence.CC_BY,
        year=2020,
        metadata={"acronym": "VIEW"},
    )
    chunks = chunk_document(doc, target_chars=400)
    assert len(chunks) > 3
    assert chunks[-1].section == "VIEW: Monitoring" and "Both eyes" in chunks[-1].text
    assert all(len(c.text) < 600 for c in chunks)
    assert all(c.licence == Licence.CC_BY for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_process_end_to_end_on_seed() -> None:
    docs, chunks, stats = process(load_seed())
    assert stats["superseded_documents"] >= 3
    assert stats["chunks"] == len(chunks) > len(docs) * 0.9


PUBMED_XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><Journal><ISOAbbreviation>Lancet</ISOAbbreviation>
<JournalIssue><PubDate><Year>2022</Year></PubDate></JournalIssue></Journal><ArticleTitle>Faricimab in DMO</ArticleTitle>
<Abstract><AbstractText Label="BACKGROUND">Background text.</AbstractText><AbstractText Label="FINDINGS">Non inferior to aflibercept.</AbstractText></Abstract>
<PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""


def test_pubmed_parser() -> None:
    [doc] = parse_efetch(PUBMED_XML)
    assert doc.id == "pubmed-123" and doc.year == 2022 and doc.grade == EvidenceGrade.RANDOMISED_TRIAL
    assert doc.sections[1] == ("Findings", "Non inferior to aflibercept.")


def test_europepmc_licence_filter() -> None:
    item = {"pmcid": "PMC1", "license": "cc by", "abstractText": "Abstract", "title": "T", "pubYear": "2021"}
    assert parse_result(item).licence == Licence.CC_BY
    assert parse_result({**item, "license": "cc by-nc"}) is None


def test_clinicaltrials_parser() -> None:
    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT01234567",
                "briefTitle": "Faricimab in Diabetic Macular Edema",
            },
            "statusModule": {"overallStatus": "RECRUITING", "startDateStruct": {"date": "2024-01"}},
            "descriptionModule": {"briefSummary": "A study."},
            "eligibilityModule": {"minimumAge": "18 Years", "sex": "ALL"},
            "designModule": {"phases": ["PHASE3"]},
            "conditionsModule": {"conditions": ["Diabetic Macular Edema"]},
            "armsInterventionsModule": {"interventions": [{"name": "Faricimab"}]},
            "contactsLocationsModule": {"locations": [{"country": "United Kingdom"}]},
        }
    }
    doc = parse_study(study)
    assert (
        doc.metadata["status"] == "RECRUITING"
        and doc.metadata["uk_sites"] is True
        and doc.metadata["min_age"] == 18
    )
    assert "dmo" in doc.conditions and doc.drugs == ["faricimab"]


def test_openfda_never_indexes_dosage() -> None:
    doc = parse_label(
        "aflibercept",
        {
            "warnings_and_cautions": ["Endophthalmitis."],
            "dosage_and_administration": ["2 mg every 8 weeks"],
            "set_id": "abc",
        },
    )
    assert "Endophthalmitis" in doc.text and "every 8 weeks" not in doc.text


def test_polite_client_retries_and_honours_retry_after() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "3"})
        return httpx.Response(200, json={"ok": True})

    client = PoliteClient(rate_per_second=1000, transport=httpx.MockTransport(handler), sleep=sleeps.append)
    assert client.get("https://example.org/api").json() == {"ok": True}
    assert calls["n"] == 3 and all(s >= 3 for s in sleeps)


def test_polite_client_gives_up_on_client_errors() -> None:
    client = PoliteClient(
        rate_per_second=1000,
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
        sleep=lambda s: None,
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://example.org/missing")


def test_robots_respected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="ok")

    client = PoliteClient(rate_per_second=1000, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert client.get("https://site.org/public", check_robots=True).text == "ok"
    with pytest.raises(PermissionError):
        client.get("https://site.org/private/page", check_robots=True)


def test_seed_files_are_valid_json() -> None:
    from fovea.config import SEED_DIR

    for path in SEED_DIR.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)


def test_trial_publication_and_registry_record_are_not_duplicates() -> None:
    paper = _doc(
        id="pubmed-1",
        text="Phase 3 results of faricimab.",
        grade=EvidenceGrade.RANDOMISED_TRIAL,
        identifiers={"pmid": "1", "nct": "NCT00000001"},
    )
    record = _doc(
        id="ctgov-nct00000001",
        source=SourceType.CLINICAL_TRIAL,
        text="Registry record for a faricimab study.",
        identifiers={"nct": "NCT00000001"},
    )
    kept, removed = deduplicate([paper, record])
    assert removed == 0 and len(kept) == 2
