"""Visual acuity parsing and conversion.

Converts between Snellen (metric 6/x and imperial 20/x), decimal, logMAR and ETDRS letter
scores, and recognises the low vision categories counting fingers, hand movements, perception
of light and no perception of light.

Conversions:
* logMAR = log10(denominator / numerator) for Snellen fractions.
* Snellen modifiers such as ``6/12+2`` or ``6/9-1`` adjust logMAR by 0.02 per letter, the value
  of one letter on a five letter per line logMAR chart.
* ETDRS letters = 85 - 50 x logMAR, the standard approximation used in trial reporting, bounded
  to 0 to 100 letters.
* Counting fingers and hand movements have no exact logMAR. Published conventions differ; the
  defaults below (1.9 and 2.3) are configurable and every converted value is flagged as a
  convention. Perception of light and no perception of light are never given a number.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from fovea.clinical import ToolCard, ToolInputError

LOW_VISION_LOGMAR = {"CF": 1.9, "HM": 2.3}
LOW_VISION_NAMES = {
    "CF": "counting fingers",
    "HM": "hand movements",
    "PL": "perception of light",
    "NPL": "no perception of light",
}
_LOW_VISION_ALIASES = {
    "cf": "CF",
    "count fingers": "CF",
    "counting fingers": "CF",
    "fc": "CF",
    "hm": "HM",
    "hand movements": "HM",
    "hand motion": "HM",
    "hmm": "HM",
    "pl": "PL",
    "lp": "PL",
    "perception of light": "PL",
    "light perception": "PL",
    "pl only": "PL",
    "npl": "NPL",
    "nlp": "NPL",
    "no perception of light": "NPL",
    "no light perception": "NPL",
}
NICE_AMD_BEST = 0.30103  # 6/12
NICE_AMD_WORST = 1.20412  # 6/96

_SNELLEN = re.compile(r"^\s*(6|20|3|1)\s*/\s*(\d+(?:\.\d+)?)\s*(?:([+-])\s*(\d))?\s*$")
_LOGMAR = re.compile(r"^\s*(?:logmar\s*)?(-?\d+(?:\.\d+)?)\s*(?:logmar)?\s*$", re.I)
_LETTERS = re.compile(r"^\s*(\d{1,3})\s*(?:etdrs\s*)?letters?\s*$", re.I)
_DECIMAL = re.compile(r"^\s*decimal\s*(\d+(?:\.\d+)?)\s*$", re.I)


@dataclass
class Acuity:
    raw: str
    notation: str
    logmar: float | None
    category: str | None = None
    convention: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def is_numeric(self) -> bool:
        return self.logmar is not None

    @property
    def decimal(self) -> float | None:
        return None if self.logmar is None else round(10 ** (-self.logmar), 3)

    @property
    def snellen_metric(self) -> str | None:
        if self.logmar is None:
            return None
        return f"6/{_nice_denominator(6 * 10**self.logmar, _METRIC_LINES)}"

    @property
    def snellen_imperial(self) -> str | None:
        if self.logmar is None:
            return None
        return f"20/{_nice_denominator(20 * 10**self.logmar, _IMPERIAL_LINES)}"

    @property
    def etdrs_letters(self) -> int | None:
        if self.logmar is None:
            return None
        return int(round(min(100.0, max(0.0, 85.0 - 50.0 * self.logmar))))

    def within_nice_amd_window(self) -> bool | None:
        """True when 6/12 to 6/96 inclusive, the window used in TA155, TA294, TA672 and TA800."""
        if self.logmar is None:
            return False if self.category in {"PL", "NPL", "CF", "HM"} else None
        return NICE_AMD_BEST - 1e-6 <= self.logmar <= NICE_AMD_WORST + 1e-6


_METRIC_LINES = [
    3,
    3.8,
    4,
    4.8,
    5,
    6,
    7.5,
    9,
    9.5,
    12,
    15,
    18,
    19,
    24,
    30,
    36,
    38,
    48,
    60,
    76,
    95,
    96,
    120,
    150,
    190,
    240,
    300,
]
_IMPERIAL_LINES = [
    10,
    12.5,
    15,
    16,
    20,
    25,
    30,
    32,
    40,
    50,
    60,
    63,
    70,
    80,
    100,
    125,
    160,
    200,
    250,
    320,
    400,
    500,
    630,
    800,
    1000,
]


def _nice_denominator(value: float, lines: list[float]) -> str:
    """Snap to a printed chart line when within 2 percent, otherwise round to one decimal."""
    nearest = min(lines, key=lambda line: abs(line - value))
    if abs(nearest - value) / nearest <= 0.02:
        value = nearest
    rounded = round(value, 1)
    return str(int(rounded)) if abs(rounded - round(rounded)) < 0.05 else f"{rounded:.1f}"


def parse(value: str | float | int) -> Acuity:
    """Parse any common acuity notation into an :class:`Acuity`."""
    if isinstance(value, (int, float)):
        value = str(value)
    raw = str(value).strip()
    text = raw.lower().replace("snellen", "").strip()
    if not text:
        raise ToolInputError("Visual acuity is empty")

    if text in _LOW_VISION_ALIASES:
        code = _LOW_VISION_ALIASES[text]
        logmar = LOW_VISION_LOGMAR.get(code)
        notes = [f"{LOW_VISION_NAMES[code]} has no exact logMAR equivalent."]
        if logmar is not None:
            notes.append(f"A conventional value of {logmar} logMAR is used; published conventions differ.")
        return Acuity(raw, "low_vision", logmar, category=code, convention=logmar is not None, notes=notes)

    match = _SNELLEN.match(text)
    if match:
        numerator = float(match.group(1))
        denominator = float(match.group(2))
        if denominator <= 0:
            raise ToolInputError("Snellen denominator must be positive")
        logmar = math.log10(denominator / numerator)
        notes = []
        if match.group(3):
            letters = int(match.group(4))
            adjustment = 0.02 * letters
            logmar = logmar - adjustment if match.group(3) == "+" else logmar + adjustment
            notes.append(f"Letter modifier {match.group(3)}{letters} applied at 0.02 logMAR per letter.")
        return Acuity(raw, "snellen", logmar, notes=notes)

    match = _LETTERS.match(text)
    if match:
        letters = int(match.group(1))
        if not 0 <= letters <= 100:
            raise ToolInputError("ETDRS letter score must be between 0 and 100")
        logmar = (85 - letters) / 50
        notes = ["Converted with logMAR = (85 minus letters) / 50."]
        if letters == 0:
            notes.append("A score of 0 letters means worse than 1.7 logMAR; the logMAR value is a floor.")
        return Acuity(raw, "etdrs_letters", logmar, notes=notes)

    match = _DECIMAL.match(text)
    if match:
        decimal = float(match.group(1))
        if decimal <= 0:
            raise ToolInputError("Decimal acuity must be positive")
        return Acuity(raw, "decimal", -math.log10(decimal))

    match = _LOGMAR.match(text)
    if match:
        logmar = float(match.group(1))
        if not -0.4 <= logmar <= 3.0:
            raise ToolInputError("logMAR must be between minus 0.4 and 3.0")
        return Acuity(raw, "logmar", round(logmar, 3))

    raise ToolInputError(f"Unrecognised visual acuity notation: {raw!r}")


def convert(value: str | float | int, eye: str | None = None) -> ToolCard:
    acuity = parse(value)
    card = ToolCard(
        tool="acuity",
        title="Visual acuity conversion",
        summary="",
        eye=eye,
        provenance="Standard optotype relationships; low vision conventions configurable",
    )
    if acuity.logmar is None:
        name = LOW_VISION_NAMES.get(acuity.category or "", acuity.raw)
        card.summary = f"{acuity.raw} recorded as {name}; no numeric equivalent is assigned."
        card.details = {"category": acuity.category, "within_nice_amd_window": False}
    else:
        card.summary = (
            f"{acuity.raw} is {acuity.logmar:.2f} logMAR, Snellen {acuity.snellen_metric} "
            f"({acuity.snellen_imperial}), decimal {acuity.decimal}, about {acuity.etdrs_letters} ETDRS letters."
        )
        card.details = {
            "logmar": round(acuity.logmar, 3),
            "snellen_metric": acuity.snellen_metric,
            "snellen_imperial": acuity.snellen_imperial,
            "decimal": acuity.decimal,
            "etdrs_letters": acuity.etdrs_letters,
            "within_nice_amd_window": acuity.within_nice_amd_window(),
            "convention": acuity.convention,
        }
        card.working = [
            f"Input notation: {acuity.notation}",
            f"logMAR = {acuity.logmar:.3f}",
            f"Snellen metric = 6 x 10^{acuity.logmar:.3f} = {acuity.snellen_metric}",
            f"ETDRS letters = 85 minus 50 x {acuity.logmar:.3f} = {acuity.etdrs_letters}",
        ]
    for note in acuity.notes:
        card.warn("info", note)
    if acuity.convention:
        card.warn(
            "caution",
            "Low vision conversions are conventions; do not use them to judge NICE treatment windows.",
        )
    card.references = [
        "NICE TA155, TA294, TA672 and TA800 acuity window 6/12 to 6/96",
        "ETDRS letter score approximation: letters = 85 minus 50 x logMAR",
    ]
    return card


def letter_change(before: str, after: str) -> int | None:
    """Change in ETDRS letters from ``before`` to ``after`` (positive means improvement)."""
    a, b = parse(before), parse(after)
    if a.logmar is None or b.logmar is None:
        return None
    return int(round((a.logmar - b.logmar) * 50))
