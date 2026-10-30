"""Text cleaning that never destroys clinical tokens.

Removes markup, scripts, navigation residue and repeated whitespace while preserving tokens
such as 6/12, ≥400 µm, 24 mmHg, R3A, TA824, q8w, 0.5 mg and NCT identifiers.
"""

from __future__ import annotations

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", re.S | re.I)
_WS = re.compile(r"[ \t\f\v]+")
_NEWLINES = re.compile(r"\n{3,}")
_BOILERPLATE = re.compile(
    r"(back to top|skip to (main )?content|cookies? (policy|settings)|share this page|print this page|"
    r"©\s?nice \d{4}\. all rights reserved\.?.*?$|subject to notice of rights.*?$)",
    re.I | re.M,
)


def clean(text: str) -> str:
    if not text:
        return ""
    value = _SCRIPT.sub(" ", text)
    value = re.sub(r"<\s*br\s*/?>|</p>|</li>|</h\d>", "\n", value, flags=re.I)
    value = _TAG.sub(" ", value)
    value = html.unescape(value)
    value = unicodedata.normalize("NFKC", value)
    value = value.replace(" ", " ").replace(" ", " ")
    value = _BOILERPLATE.sub(" ", value)
    value = _WS.sub(" ", value)
    value = "\n".join(line.strip() for line in value.splitlines())
    value = _NEWLINES.sub("\n\n", value)
    return value.strip()
