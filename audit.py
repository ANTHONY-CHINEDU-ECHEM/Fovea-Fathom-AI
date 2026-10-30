"""Audit log, clinician feedback and the governance summary.

Audit records never contain patient text. The redacted question is stored only as a keyed
hash (HMAC SHA 256 with a deployment secret), alongside the sources used, the grounding report,
the provider chain and latency, so a clinical safety officer can reconstruct how an answer was
produced without the log becoming a store of patient data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fovea.guardrails.pii import redact

FEEDBACK_REASONS = {
    "incorrect",
    "outdated",
    "unsafe",
    "wrong_eye",
    "missing_evidence",
    "unclear",
    "helpful",
    "accurate",
    "other",
}


class AuditLog:
    def __init__(self, audit_path: str, feedback_path: str, salt: str) -> None:
        self.audit_path = Path(audit_path)
        self.feedback_path = Path(feedback_path)
        self.salt = salt.encode("utf-8")
        self._lock = threading.Lock()

    def question_hash(self, redacted_question: str) -> str:
        return hmac.new(
            self.salt, redacted_question.strip().lower().encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def record_answer(self, final: dict[str, Any]) -> dict[str, Any]:
        grounding = final.get("grounding") or {}
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": final["request_id"],
            "question_hash": self.question_hash(final.get("question", "")),
            "status": final["status"],
            "conditions": final.get("conditions", []),
            "emergencies": final.get("emergencies", []),
            "tools": final.get("tools", []),
            "sources": final.get("source_doc_ids", []),
            "cited": grounding.get("cited_sources", []),
            "citation_coverage": grounding.get("citation_coverage"),
            "unsupported_figures": len(grounding.get("unsupported_figures", []) or []),
            "claim_support": grounding.get("claim_support"),
            "grounded": grounding.get("grounded"),
            "laterality_consistent": (final.get("laterality") or {}).get("consistent"),
            "superseded_cited": final.get("superseded_cited", []),
            "provider": final.get("provider"),
            "fallbacks": final.get("fallbacks", []),
            "latency_ms": final.get("latency_ms"),
        }
        self._append(self.audit_path, record)
        return record

    def record_feedback(
        self, request_id: str, rating: int, reasons: list[str], comment: str | None
    ) -> dict[str, Any]:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "rating": rating,
            "reasons": [r for r in reasons if r in FEEDBACK_REASONS],
            "comment": redact(comment).text[:2000] if comment else None,
        }
        self._append(self.feedback_path, record)
        return record

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def summary(self) -> dict[str, Any]:
        answers = self._read(self.audit_path)
        feedback = self._read(self.feedback_path)
        answered = [a for a in answers if a["status"] == "answered"]
        total = len(answers) or 1

        def mean(key: str) -> float | None:
            values = [a[key] for a in answered if isinstance(a.get(key), (int, float))]
            return round(sum(values) / len(values), 4) if values else None

        return {
            "answers": len(answers),
            "by_status": dict(Counter(a["status"] for a in answers)),
            "abstention_rate": round(sum(1 for a in answers if a["status"] == "abstained") / total, 4),
            "grounded_rate": round(sum(1 for a in answered if a.get("grounded")) / (len(answered) or 1), 4),
            "mean_citation_coverage": mean("citation_coverage"),
            "mean_claim_support": mean("claim_support"),
            "answers_with_unsupported_figures": sum(1 for a in answered if a.get("unsupported_figures")),
            "laterality_flags": sum(1 for a in answered if a.get("laterality_consistent") is False),
            "emergencies": dict(Counter(e for a in answers for e in a.get("emergencies", []))),
            "tool_use": dict(Counter(t for a in answers for t in a.get("tools", []))),
            "superseded_cited": sum(1 for a in answers if a.get("superseded_cited")),
            "providers": dict(Counter(a.get("provider") or "none" for a in answers)),
            "feedback": {
                "count": len(feedback),
                "negative": sum(1 for f in feedback if f["rating"] < 0),
                "reasons": dict(Counter(r for f in feedback for r in f.get("reasons", []))),
            },
        }
