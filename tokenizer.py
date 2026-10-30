"""Clinical tokenizer for sparse retrieval.

General tokenizers split exactly the tokens ophthalmology depends on. This tokenizer keeps
Snellen fractions (6/12, 20/40), screening grades (R3A, M1), appraisal and guideline numbers
(TA824, NG82), registry ids (NCT03823287), pressures and thicknesses with units (24mmhg,
400um), lens powers (21.5d) and hyphenated drug names as single tokens, folds US spellings
to UK spellings and maps brand names to generics. It also emits concept tokens so that
"exudate within one disc diameter" and "M1" meet, and "anti vegf" and "aflibercept" meet.
"""

from __future__ import annotations

import re
from functools import lru_cache

from fovea.clinical.understanding import _lexicon, normalise

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "might",
        "more",
        "most",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "will",
        "with",
        "would",
        "you",
        "your",
        "about",
        "after",
        "also",
        "any",
        "before",
        "being",
        "both",
        "each",
        "few",
        "further",
        "here",
        "just",
        "less",
        "no",
        "nor",
        "not",
        "now",
        "only",
        "other",
        "over",
        "same",
        "some",
        "still",
        "through",
        "under",
        "until",
        "up",
        "very",
    ]
)

_TOKEN = re.compile(
    r"nct\d{8}"
    r"|(?:ta|ng|cg|qs|ipg|hst)\d{2,4}"
    r"|(?:6|20)/\d+(?:\.\d+)?"
    r"|r3[as]|r[0-2]|m[01]"
    r"|\d+(?:\.\d+)?(?:mmhg|um|mg|d|db|%)"
    r"|[a-z]+(?:-[a-z0-9]+)+"
    r"|[a-z][a-z0-9]*"
    r"|\d+(?:\.\d+)?"
)
# Long clinical phrases also emit their standard abbreviation, so "diabetic macular oedema"
# in a guideline meets "DMO" in a question.
ABBREVIATIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"age[- ]related macular degeneration"), "amd"),
    (re.compile(r"diabetic macular o?edema"), "dmo"),
    (re.compile(r"retinal vein occlusion"), "rvo"),
    (re.compile(r"central retinal vein occlusion"), "crvo"),
    (re.compile(r"branch retinal vein occlusion"), "brvo"),
    (re.compile(r"ocular hypertension"), "oht"),
    (re.compile(r"chronic open angle glaucoma"), "coag"),
    (re.compile(r"selective laser trabeculoplasty"), "slt"),
    (re.compile(r"proliferative diabetic retinopathy"), "pdr"),
    (re.compile(r"panretinal photocoagulation"), "prp"),
    (re.compile(r"optical coherence tomography"), "oct"),
    (re.compile(r"intraocular pressure"), "iop"),
    (re.compile(r"central (?:retinal|subfield) thickness"), "crt"),
    (re.compile(r"best corrected visual acuity"), "bcva"),
    (re.compile(r"choroidal neovascularisation"), "cnv"),
]
_UNIT_JOIN = re.compile(r"(\d)\s+(mm\s?hg|um|micrometres?|microns?|mg|dioptres?|db|%)\b")

CONCEPTS: dict[str, tuple[str, ...]] = {
    "concept_anti_vegf": (
        "aflibercept",
        "ranibizumab",
        "faricimab",
        "brolucizumab",
        "bevacizumab",
        "anti",
        "vegf",
    ),
    "concept_steroid_implant": ("ozurdex", "iluvien", "dexamethasone", "fluocinolone"),
    "concept_macular_oedema": ("dmo", "dme", "oedema", "m1", "thickening"),
    "concept_proliferative": ("r3a", "pdr", "proliferative", "neovascularisation", "nvd", "nve"),
    "concept_pressure": ("iop", "intraocular", "pressure", "mmhg", "tonometry"),
    "concept_slt": ("slt", "trabeculoplasty"),
    "concept_field": ("perimetry", "field", "fields", "deviation"),
    "concept_interval": ("extend", "interval", "intervals", "q8w", "q12w", "q16w", "weeks"),
    "concept_cataract": ("cataract", "phacoemulsification", "iol", "biometry"),
}


@lru_cache(maxsize=1)
def _brand_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for generic, spec in _lexicon()["drugs"].items():
        if " " in generic:
            continue
        for brand in spec.get("brands", []):
            if " " not in brand:
                out[brand] = generic
    return out


def tokenize(text: str, concepts: bool = True) -> list[str]:
    value = normalise(text)
    value = _UNIT_JOIN.sub(lambda m: m.group(1) + _unit(m.group(2)), value)
    for pattern, abbreviation in ABBREVIATIONS:
        value = pattern.sub(rf"\g<0> {abbreviation}", value)
    tokens: list[str] = []
    brands = _brand_map()
    for raw in _TOKEN.findall(value):
        token = raw.replace("anti-vegf", "anti vegf")
        if token in STOPWORDS:
            continue
        token = brands.get(token, token)
        token = stem(token)
        tokens.append(token)
    if concepts:
        present = set(tokens)
        for concept, members in CONCEPTS.items():
            if present.intersection(members):
                tokens.append(concept)
    return tokens


_KEEP = frozenset(
    {
        "uveitis",
        "keratitis",
        "iritis",
        "diabetes",
        "always",
        "lens",
        "focus",
        "status",
        "previous",
        "various",
        "serious",
        "bleeding",
    }
)
_DOUBLE = re.compile(r"([b-df-hj-np-tv-z])\1$")


def stem(token: str) -> str:
    """Light suffix stripping so stopped, stopping and stop meet, and injections meets injection."""
    if not token.isalpha() or token in _KEEP or len(token) <= 4:
        return token
    if token.endswith("ies") and len(token) > 5:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        token = token[:-1]
    for suffix in ("ing", "ed"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[: -len(suffix)]
            if _DOUBLE.search(token) and not token.endswith(("ll", "ss")):
                token = token[:-1]
            break
    return token


def _unit(unit: str) -> str:
    unit = unit.replace(" ", "")
    if unit.startswith("micro"):
        return "um"
    if unit.startswith("dioptre"):
        return "d"
    return unit
