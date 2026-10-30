"""Redaction of patient identifiers before any text reaches retrieval, a model, the cache or logs.

Identifiers are replaced with typed placeholders such as ``[NHS_NUMBER]`` and ``[NAME]``.
NHS numbers are redacted only when they pass the modulus 11 check digit, so a ten digit
measurement survives. Clinical tokens that look like dates or numbers (6/12, 24 mmHg, R3A,
TA824) are never redacted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TITLE_NAME = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Sir|Dame|Master)\.?\s+(?:[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?)(?:\s+[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?){0,2}"
)
_NAMED = re.compile(r"\b(?:patient|named|called|name is|name:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")
_NHS_CANDIDATE = re.compile(r"(?<!\d)(\d{3})[\s-]?(\d{3})[\s-]?(\d{4})(?!\d)")
_HOSPITAL = re.compile(
    r"\b(?:hospital (?:number|no\.?)|mrn|hosp(?:ital)? no\.?|unit number|crn)\s*[:#]?\s*([A-Z]{0,3}\d{5,10})\b",
    re.I,
)
_POSTCODE = re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}\b")
_DOB = re.compile(
    r"\b(?:dob|d\.o\.b\.?|date of birth|born(?: on)?)\s*[:]?\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4})",
    re.I,
)
_FULL_DATE = re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.](?:19|20)\d{2}\b")
_PHONE = re.compile(
    r"(?<!\d)(?:\+44\s?7\d{3}|07\d{3}|\+44\s?\(?0?\)?\s?\d{2,4}|0\d{2,4})[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_ADDRESS = re.compile(
    r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Close|Drive|Dr|Way|Court|Crescent|Place|Terrace|Gardens|Grove)\b"
)


def nhs_number_valid(digits: str) -> bool:
    """Modulus 11 check used by NHS numbers."""
    if len(digits) != 10 or not digits.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(digits[:9], range(10, 1, -1), strict=True))
    check = 11 - (total % 11)
    if check == 11:
        check = 0
    if check == 10:
        return False
    return check == int(digits[9])


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def redacted(self) -> bool:
        return bool(self.counts)


def redact(text: str) -> RedactionResult:
    counts: dict[str, int] = {}

    def sub(pattern: re.Pattern[str], label: str, value: str, group: int | None = None) -> str:
        def repl(m: re.Match[str]) -> str:
            counts[label] = counts.get(label, 0) + 1
            if group is None:
                return f"[{label}]"
            whole = m.group(0)
            return whole.replace(m.group(group), f"[{label}]")

        return pattern.sub(repl, value)

    out = sub(_EMAIL, "EMAIL", text)
    out = sub(_DOB, "DATE_OF_BIRTH", out, group=1)

    def nhs(m: re.Match[str]) -> str:
        digits = "".join(m.groups())
        if nhs_number_valid(digits):
            counts["NHS_NUMBER"] = counts.get("NHS_NUMBER", 0) + 1
            return "[NHS_NUMBER]"
        return m.group(0)

    out = _NHS_CANDIDATE.sub(nhs, out)
    out = sub(_HOSPITAL, "HOSPITAL_NUMBER", out, group=1)
    out = sub(_PHONE, "PHONE", out)
    out = sub(_ADDRESS, "ADDRESS", out)
    out = sub(_POSTCODE, "POSTCODE", out)
    out = sub(_FULL_DATE, "DATE", out)
    out = sub(_TITLE_NAME, "NAME", out)
    out = sub(_NAMED, "NAME", out, group=1)
    return RedactionResult(out, counts)


def redact_list(values: list[str]) -> list[str]:
    return [redact(v).text for v in values]
