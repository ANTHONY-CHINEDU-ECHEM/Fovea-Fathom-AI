"""Query understanding: entity extraction, normalisation and synonym expansion.

Turns a clinician's question into structured entities (conditions, medicines and their
classes, interventions, laterality, acuity, pressure, retinal thickness and age), maps brand
names to generics and US spellings to UK spellings, and builds two retrieval queries:

* a **recall query**: the question plus guideline synonyms, used for first stage retrieval
* a **precision query**: the normalised question itself, used for reranking
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from fovea import knowledge

_ACUITY = re.compile(
    r"\b(?:6|20)/\d+(?:\.\d+)?(?:\s?[+-]\d)?\b|\b\d{1,3}\s?(?:etdrs\s)?letters\b|\blogmar\s?-?\d(?:\.\d+)?\b|\b(?:cf|hm|pl|npl)\b",
    re.I,
)
_IOP = re.compile(
    r"\b(?:iop|intraocular pressure|pressure)\s*(?:of|is|was|at|=)?\s*(\d{1,2}(?:\.\d)?)\s*(?:mm\s?hg)?|\b(\d{1,2})\s?mm\s?hg\b",
    re.I,
)
_CST = re.compile(
    r"\b(?:cst|crt|central (?:retinal|subfield) thickness)\s*(?:of|is|was|=)?\s*(\d{3,4})\s*(?:µm|um|microns?|micrometres?)?|\b(\d{3,4})\s?(?:µm|um|microns?|micrometres?)\b",
    re.I,
)
_AGE = re.compile(r"\b(\d{1,3})\s?(?:year old|years old|yo|y/o|yr old)\b|\baged\s(\d{1,3})\b", re.I)
_GUIDANCE_ID = re.compile(r"\b(?:TA\s?\d{2,4}|NG\s?\d{2,3}|CG\s?\d{2,3}|NCT\d{8}|PMID:?\s?\d{6,9})\b", re.I)
_INJECTION_COUNT = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)?\s(?:injections?|doses?)\b", re.I)
_INTERVAL = re.compile(
    r"\b(\d{1,2})\s?(?:-|to)?\s?weeks?\b|\bq(\d{1,2})w\b|\bevery\s(\d{1,2})\sweeks\b", re.I
)


IMPLIED_CONDITIONS: dict[str, list[str]] = {
    "slt": ["coag", "oht"],
    "trabeculectomy": ["coag"],
    "iridotomy": ["angle_closure"],
    "prp": ["diabetic_retinopathy"],
    "cataract_surgery": ["cataract"],
    "crosslinking": ["keratitis"],
}


@dataclass
class Understanding:
    original: str
    normalised: str
    conditions: list[str] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)
    drug_classes: list[str] = field(default_factory=list)
    interventions: list[str] = field(default_factory=list)
    laterality: list[str] = field(default_factory=list)
    acuities: list[str] = field(default_factory=list)
    iop_values: list[float] = field(default_factory=list)
    cst_values: list[float] = field(default_factory=list)
    age: int | None = None
    guidance_ids: list[str] = field(default_factory=list)
    injection_count: int | None = None
    interval_weeks: float | None = None
    intents: list[str] = field(default_factory=list)
    recall_query: str = ""
    precision_query: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, Any]:
    return knowledge.load("lexicon").data


@lru_cache(maxsize=1)
def _term_index() -> dict[str, list[tuple[str, str]]]:
    """Map kind to (term, canonical id) pairs, longest terms first so phrases win over words."""
    lex = _lexicon()
    index: dict[str, list[tuple[str, str]]] = {
        "condition": [],
        "drug": [],
        "intervention": [],
        "laterality": [],
    }
    for cid, spec in lex["conditions"].items():
        for term in spec["terms"]:
            index["condition"].append((term, cid))
    for generic, spec in lex["drugs"].items():
        index["drug"].append((generic, generic))
        for brand in spec.get("brands", []):
            index["drug"].append((brand, generic))
    for iid, terms in lex["interventions"].items():
        for term in terms:
            index["intervention"].append((term, iid))
    for side, terms in lex["laterality"].items():
        for term in terms:
            index["laterality"].append((term, side))
    for kind in index:
        index[kind].sort(key=lambda pair: len(pair[0]), reverse=True)
    return index


def drug_class(generic: str) -> str | None:
    spec = _lexicon()["drugs"].get(generic)
    return spec.get("class") if spec else None


def classes_for(names: list[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        cls = drug_class(name)
        if cls and cls not in out:
            out.append(cls)
    return out


def normalise(text: str) -> str:
    """Lower case, UK spelling, unified dashes and whitespace."""
    value = text.lower()
    value = value.replace("–", " ").replace("—", " ").replace("‑", "-")
    value = value.replace("µm", " um").replace("μm", " um")
    for us, uk in _lexicon()["spelling"].items():
        value = re.sub(rf"\b{us}\b", uk, value)
    value = re.sub(r"anti[\s-]?vegf", "anti vegf", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _find_terms(text: str, kind: str) -> list[str]:
    found: list[str] = []
    consumed = text
    for term, canonical in _term_index()[kind]:
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        if re.search(pattern, consumed):
            if canonical not in found:
                found.append(canonical)
            consumed = re.sub(pattern, " ", consumed)
    return found


def find_conditions(text: str) -> list[str]:
    return _find_terms(normalise(text), "condition")


def find_drugs(text: str) -> list[str]:
    return _find_terms(normalise(text), "drug")


def understand(question: str, context_text: str = "") -> Understanding:
    norm = normalise(question)
    combined = f"{norm} {normalise(context_text)}".strip()
    u = Understanding(original=question, normalised=norm)
    u.conditions = _find_terms(combined, "condition")
    u.drugs = _find_terms(combined, "drug")
    u.drug_classes = classes_for(u.drugs)
    u.interventions = _find_terms(combined, "intervention")
    if not u.conditions:
        implied = [IMPLIED_CONDITIONS[i] for i in u.interventions if i in IMPLIED_CONDITIONS]
        u.conditions = list(dict.fromkeys(c for group in implied for c in group))
    u.laterality = _find_terms(norm, "laterality")
    u.acuities = [m.group(0) for m in _ACUITY.finditer(question)]
    for m in _IOP.finditer(norm):
        value = m.group(1) or m.group(2)
        if value and 3 <= float(value) <= 80:
            u.iop_values.append(float(value))
    for m in _CST.finditer(norm):
        value = m.group(1) or m.group(2)
        if value and 100 <= float(value) <= 1500:
            u.cst_values.append(float(value))
    age = _AGE.search(norm)
    if age:
        u.age = int(age.group(1) or age.group(2))
    u.guidance_ids = sorted(
        {re.sub(r"\s", "", g.upper()).replace("PMID:", "PMID") for g in _GUIDANCE_ID.findall(question)}
    )
    count = _INJECTION_COUNT.search(norm)
    if count:
        u.injection_count = int(count.group(1))
    interval = _INTERVAL.search(norm)
    if interval:
        u.interval_weeks = float(next(g for g in interval.groups() if g))
    u.intents = _intents(norm, u)
    u.precision_query = norm
    u.recall_query = _expand(norm, u)
    return u


def _intents(norm: str, u: Understanding) -> list[str]:
    intents: list[str] = []
    rules = [
        ("acuity_conversion", r"convert|logmar|letters|snellen|equivalent"),
        ("biometry", r"\biol\b|lens power|biometry|srk|a constant|axial length"),
        (
            "dr_grading",
            r"\br[0-3]a?s?\b|\bm[01]\b|grade|grading|screening outcome|irma|venous beading|new vessels",
        ),
        ("treat_and_extend", r"treat and extend|interval|extend|next injection|how often|weeks"),
        (
            "therapy_options",
            r"option|recommend|eligible|first line|second line|which (drug|treatment|agent)|switch|nice|should (we|i) (offer|start|treat)|offer|treatment for",
        ),
        ("glaucoma_target", r"target (iop|pressure)|target intraocular"),
        ("field_progression", r"progression|rate of loss|mean deviation|\bmd\b"),
        ("hcq_monitoring", r"hydroxychloroquine|plaquenil|chloroquine"),
        (
            "safety_screen",
            r"interaction|contraindicat|safe to|caution|allerg|with (asthma|copd)|taking|on (warfarin|apixaban|tamsulosin)",
        ),
        ("trials", r"\btrials?\b|recruiting|study for|clinical study"),
    ]
    for name, pattern in rules:
        if re.search(pattern, norm):
            intents.append(name)
    if u.iop_values and ("oht" in u.conditions or "coag" in u.conditions):
        intents.append("oht_threshold")
    return intents


def _expand(norm: str, u: Understanding) -> str:
    lex = _lexicon()
    extra: list[str] = []
    for phrase, synonyms in lex["guideline_synonyms"].items():
        if phrase in norm:
            extra.extend(synonyms)
    for cid in u.conditions:
        spec = lex["conditions"][cid]
        extra.append(spec["terms"][0])
        extra.extend(spec.get("synonyms", []))
    for generic in u.drugs:
        extra.append(generic)
    if "anti_vegf" in u.drug_classes or "anti vegf" in norm:
        extra.append("anti vegf intravitreal")
    seen: set[str] = set()
    terms = []
    for item in extra:
        if item not in seen and item not in norm:
            seen.add(item)
            terms.append(item)
    return f"{norm} {' '.join(terms)}".strip()
