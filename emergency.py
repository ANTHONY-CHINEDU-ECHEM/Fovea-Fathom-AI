"""Eye emergency triage, run before retrieval on every question.

A match produces an action banner that is streamed as the first content event, is never
served from cache and is never suppressed by the answerability gate.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

from fovea import knowledge

_NEGATION = re.compile(r"\b(?:no|denies|denied|without|not|nil|negative for|absence of)\b[^.;]{0,40}$", re.I)


@dataclass
class EmergencyAlert:
    id: str
    name: str
    urgency: str
    action: str
    guidance: str
    matched: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache(maxsize=1)
def _rules() -> list[dict[str, Any]]:
    rules = knowledge.load("emergencies").data["emergencies"]
    compiled = []
    for rule in rules:
        compiled.append(
            {
                **rule,
                "_any": [re.compile(p, re.I) for p in rule.get("any", [])],
                "_all": [re.compile(p, re.I) for p in rule.get("all", [])],
            }
        )
    return compiled


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - 50) : start]
    return bool(_NEGATION.search(window))


def triage(text: str) -> list[EmergencyAlert]:
    alerts: list[EmergencyAlert] = []
    for rule in _rules():
        hit = None
        for pattern in rule["_any"]:
            for m in pattern.finditer(text):
                if not _negated(text, m.start()):
                    hit = m
                    break
            if hit:
                break
        if not hit:
            continue
        if rule["_all"] and not all(p.search(text) for p in rule["_all"]):
            continue
        alerts.append(
            EmergencyAlert(
                id=rule["id"],
                name=rule["name"],
                urgency=rule["urgency"],
                action=" ".join(rule["action"].split()),
                guidance=rule["guidance"],
                matched=hit.group(0),
            )
        )
    return alerts


def guidance_query(alerts: list[EmergencyAlert]) -> str:
    """Terms added to the retrieval query so matching emergency guidance is retrieved."""
    return " ".join(a.name.lower() for a in alerts)
