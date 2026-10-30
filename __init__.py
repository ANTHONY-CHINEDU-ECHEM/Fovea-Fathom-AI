"""Loader for the reviewed, version controlled rule files.

Rule files are plain YAML so clinicians can review them in a pull request without reading
Python. Each file carries a version and a review date, which are surfaced in every tool card
and in ``GET /v1/knowledge`` so an auditor can tie an answer to the exact rules in force.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from fovea.config import KNOWLEDGE_DIR

RULE_FILES = {
    "lexicon": "lexicon.yaml",
    "therapy_matrix": "therapy_matrix.yaml",
    "emergencies": "emergencies.yaml",
    "safety_rules": "safety_rules.yaml",
    "supersession": "supersession.yaml",
    "injection_regimens": "injection_regimens.yaml",
    "screening_and_targets": "screening_and_targets.yaml",
}


@dataclass(frozen=True)
class RuleFile:
    name: str
    path: Path
    version: str
    review_date: str
    data: dict[str, Any]

    @property
    def provenance(self) -> str:
        return f"{self.name} v{self.version}, reviewed {self.review_date}"


@cache
def load(name: str) -> RuleFile:
    if name not in RULE_FILES:
        raise KeyError(f"Unknown rule file: {name}")
    path = KNOWLEDGE_DIR / RULE_FILES[name]
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return RuleFile(
        name=name,
        path=path,
        version=str(data.get("version", "unversioned")),
        review_date=str(data.get("review_date", "unknown")),
        data=data,
    )


def manifest() -> list[dict[str, str]]:
    """Version and review date of every rule file, for the knowledge endpoint and audit."""
    return [
        {"name": rf.name, "file": rf.path.name, "version": rf.version, "review_date": rf.review_date}
        for rf in (load(name) for name in RULE_FILES)
    ]
