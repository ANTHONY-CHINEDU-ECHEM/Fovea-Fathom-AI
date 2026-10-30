"""Evaluation harness and continuous integration gate.

``python -m evaluation.harness --offline --gate`` runs the golden set against the verified seed
snapshot with the hashing embedder, the lexical reranker and the extractive generator, which is
exactly what continuous integration runs without network access. ``--live`` uses the configured
index and model, where citation coverage, figure checks and claim support measure the model.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from evaluation.metrics import QuestionResult, aggregate, fact_recall, retrieval
from fovea.config import REPO_ROOT, get_settings, override_settings
from fovea.domain import PatientContext
from fovea.generation.pipeline import AnswerPipeline, AskInput
from fovea.llm.router import LLMRouter
from fovea.retrieval.index import KnowledgeIndex

EVAL_DIR = REPO_ROOT / "evaluation"
GOLDEN = EVAL_DIR / "golden_set.jsonl"
THRESHOLDS = EVAL_DIR / "thresholds.yaml"
REPORTS = EVAL_DIR / "reports"


def load_golden(path: Path = GOLDEN) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def offline_pipeline() -> AnswerPipeline:
    from ingestion.pipeline import build_index, load_seed

    tmp = Path(tempfile.mkdtemp(prefix="fovea_eval_"))
    settings = override_settings(
        llm_provider="extractive",
        llm_fallbacks=[],
        embedding_backend="hashing",
        reranker_backend="lexical",
        vector_backend="memory",
        index_dir=str(tmp),
        audit_path=str(tmp / "audit.jsonl"),
        feedback_path=str(tmp / "feedback.jsonl"),
    )
    index, _ = build_index(settings, load_seed(), tmp)
    return AnswerPipeline(index, LLMRouter(settings), settings)


def live_pipeline() -> AnswerPipeline:
    settings = get_settings()
    index = KnowledgeIndex.load(Path(settings.index_dir), settings)
    return AnswerPipeline(index, LLMRouter(settings), settings)


def evaluate(
    pipeline: AnswerPipeline, golden: list[dict[str, Any]]
) -> tuple[list[QuestionResult], list[dict[str, Any]]]:
    results: list[QuestionResult] = []
    details: list[dict[str, Any]] = []
    for item in golden:
        started = time.perf_counter()
        response = pipeline.ask(
            AskInput(item["question"], PatientContext.model_validate(item.get("context") or {}))
        )
        final = response["final"]
        retrieved = [s["doc_id"] for s in response["sources"]]
        hit, rr = retrieval(item["expected_sources"], retrieved)
        alerts = [a["id"] for a in response["emergencies"]]
        expected_emergency = item.get("expected_emergency")
        emergency_ok = (expected_emergency in alerts) if expected_emergency else not alerts
        tools = [c["tool"] for c in response["tools"]]
        tools_ok = all(t in tools for t in item["expected_tools"]) if item["expected_tools"] else None
        redactions = response.get("meta", {}).get("redactions", {})
        redaction_ok = (
            all(r in redactions for r in item["expected_redactions"]) if item["expected_redactions"] else None
        )
        expected_status = item["expected_status"]
        scope_ok = (final["status"] == "out_of_scope") == (expected_status == "out_of_scope")
        grounding = final.get("grounding") or {}
        laterality = final.get("laterality") or {}
        result = QuestionResult(
            id=item["id"],
            status=final["status"],
            expected_status=expected_status,
            hit_at_5=hit,
            reciprocal_rank=rr,
            fact_recall=fact_recall(item["expected_facts"], final["answer"])
            if final["status"] == "answered"
            else None,
            citation_coverage=grounding.get("citation_coverage"),
            claim_support=grounding.get("claim_support"),
            unsupported_figures=len(grounding.get("unsupported_figures") or []),
            emergency_ok=emergency_ok,
            tools_ok=tools_ok,
            redaction_ok=redaction_ok,
            scope_ok=scope_ok,
            laterality_ok=laterality.get("consistent", True),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        results.append(result)
        details.append(
            {
                "id": item["id"],
                "status": final["status"],
                "expected_status": expected_status,
                "retrieved": retrieved[:5],
                "tools": tools,
                "emergencies": alerts,
                "answer": final["answer"][:600],
                "grounding": grounding,
            }
        )
    return results, details


def gate(summary: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    failures = []
    for metric, rule in thresholds["gates"].items():
        value = summary.get(metric)
        if value is None:
            continue
        if "min" in rule and value < rule["min"]:
            failures.append(f"{metric} = {value} is below {rule['min']}")
        if "max" in rule and value > rule["max"]:
            failures.append(f"{metric} = {value} is above {rule['max']}")
    return failures


def write_report(summary: dict[str, Any], details: list[dict[str, Any]], mode: str) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = REPORTS / f"{mode}_latest"
    stem.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "questions": details}, indent=2), encoding="utf-8"
    )
    lines = [f"# Evaluation report ({mode})", "", "Metric | Value", "--- | ---"]
    lines += [f"{k} | {v}" for k, v in summary.items()]
    lines += ["", "## Questions", "", "Id | Status | Expected | Retrieved top 3", "--- | --- | --- | ---"]
    lines += [
        f"{d['id']} | {d['status']} | {d['expected_status']} | {', '.join(d['retrieved'][:3])}"
        for d in details
    ]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fovea-eval")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", default=True)
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--gate", action="store_true", help="exit non zero when a threshold is missed")
    args = parser.parse_args(argv)

    pipeline = live_pipeline() if args.live else offline_pipeline()
    results, details = evaluate(pipeline, load_golden())
    summary = aggregate(results)
    stem = write_report(summary, details, "live" if args.live else "offline")
    print(json.dumps(summary, indent=2))
    print(f"report: {stem}.md")
    if args.gate:
        failures = gate(summary, yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8")))
        if failures:
            print("EVALUATION GATE FAILED:\n  " + "\n  ".join(failures), file=sys.stderr)
            return 1
        print("evaluation gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
