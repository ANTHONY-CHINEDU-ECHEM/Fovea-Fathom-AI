from pathlib import Path

import yaml

from evaluation.harness import GOLDEN, evaluate, gate, load_golden
from evaluation.metrics import aggregate, fact_recall, retrieval
from fovea import knowledge
from fovea.audit import AuditLog
from fovea.cache import MemoryCache, cache_key
from fovea.config import REPO_ROOT, Settings, load_settings


def test_audit_never_stores_question_text(tmp_path: Path) -> None:
    log = AuditLog(str(tmp_path / "a.jsonl"), str(tmp_path / "f.jsonl"), "salt")
    final = {
        "request_id": "r1",
        "question": "secret question text",
        "status": "answered",
        "grounding": {
            "citation_coverage": 1.0,
            "claim_support": 1.0,
            "unsupported_figures": [],
            "grounded": True,
            "cited_sources": [1],
        },
    }
    log.record_answer(final)
    raw = (tmp_path / "a.jsonl").read_text()
    assert "secret question text" not in raw
    assert log.question_hash("secret question text") in raw
    assert log.question_hash("x") != AuditLog("a", "b", "other").question_hash("x")
    summary = log.summary()
    assert summary["answers"] == 1 and summary["grounded_rate"] == 1.0


def test_cache_expiry_and_lru() -> None:
    cache = MemoryCache(max_items=2)
    cache.set("a", {"v": 1}, ttl=60)
    cache.set("b", {"v": 2}, ttl=60)
    cache.get("a")
    cache.set("c", {"v": 3}, ttl=60)
    assert cache.get("b") is None and cache.get("a") == {"v": 1}
    cache.set("d", {"v": 4}, ttl=-1)
    assert cache.get("d") is None
    assert (
        cache_key("Q", {}, None, "v1")
        == cache_key(" q ", {}, None, "v1")
        != cache_key("q", {}, "openai", "v1")
    )


def test_settings_from_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FF_TOP_K_FINAL", "5")
    monkeypatch.setenv("FF_LLM_FALLBACKS", "ollama, extractive")
    monkeypatch.setenv("FF_LOG_JSON", "true")
    settings = load_settings()
    assert (
        settings.top_k_final == 5 and settings.llm_fallbacks == ["ollama", "extractive"] and settings.log_json
    )
    assert Settings(llm_provider="ollama", llm_fallbacks=["ollama", "openai"]).provider_chain() == [
        "ollama",
        "openai",
        "extractive",
    ]


def test_rule_files_are_versioned_and_consistent() -> None:
    manifest = knowledge.manifest()
    assert all(entry["version"] != "unversioned" for entry in manifest)
    matrix = knowledge.load("therapy_matrix").data["options"]
    lexicon = knowledge.load("lexicon").data
    statuses = {
        "recommended",
        "recommended_with_criteria",
        "research_only",
        "not_recommended",
        "terminated",
        "check_appraisal",
    }
    for option in matrix:
        assert option["condition"] in lexicon["conditions"], option["id"]
        assert option["status"] in statuses
    ids = [o["id"] for o in matrix]
    assert len(ids) == len(set(ids))


def test_emergency_rules_compile_and_have_actions() -> None:
    import re

    for rule in knowledge.load("emergencies").data["emergencies"]:
        assert rule["action"] and rule["any"]
        for pattern in rule["any"]:
            re.compile(pattern)


def test_metric_helpers() -> None:
    assert retrieval(["a"], ["b", "a"]) == (True, 0.5)
    assert retrieval([], ["a"]) == (None, None)
    assert fact_recall(["400 micrometres"], "needs 400 micrometres") == 1.0


def test_golden_set_shape() -> None:
    golden = load_golden(GOLDEN)
    assert len(golden) >= 50
    assert {g["expected_status"] for g in golden} >= {"answered", "abstained", "out_of_scope", "any"}
    assert sum(1 for g in golden if g["expected_emergency"]) >= 4


def test_evaluation_gate_passes_offline(pipeline) -> None:  # type: ignore[no-untyped-def]
    results, _ = evaluate(pipeline, load_golden())
    summary = aggregate(results)
    thresholds = yaml.safe_load((REPO_ROOT / "evaluation" / "thresholds.yaml").read_text())
    assert gate(summary, thresholds) == []
