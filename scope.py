"""Scope check: decline questions with no eye care content without spending a model call."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fovea.clinical.understanding import Understanding

EYE_WORDS = re.compile(
    r"\b(eye|eyes|ocular|ophthalm\w*|retina\w*|macula\w*|fovea\w*|vision|visual|sight|cornea\w*|lens|cataract\w*|glaucoma|"
    r"intraocular|iop|optic|uveitis|iritis|vitre\w*|choroid\w*|conjunctiv\w*|eyelid|orbit\w*|pupil\w*|acuity|snellen|logmar|"
    r"oct|angiograph\w*|anti ?vegf|intravitreal|injection interval|diabetic eye|screening grade|biometry|iol|keratitis|"
    r"blind\w*|floaters|flashes|squint|strabismus|amblyopia|diplopia|double vision|tonometry|perimetry|field)\b",
    re.I,
)


@dataclass
class ScopeDecision:
    in_scope: bool
    reason: str


def check(
    u: Understanding,
    has_context: bool,
    in_scope_conversation: bool = False,
    known_ids: set[str] | None = None,
) -> ScopeDecision:
    if u.conditions or u.interventions:
        return ScopeDecision(True, "eye condition or intervention named")
    if any(
        d
        for d in u.drugs
        if d not in {"aspirin", "warfarin", "apixaban", "rivaroxaban", "salbutamol", "bisoprolol"}
    ):
        return ScopeDecision(True, "eye treatment medicine named")
    if EYE_WORDS.search(u.normalised):
        return ScopeDecision(True, "eye care vocabulary")
    if u.acuities or u.iop_values:
        return ScopeDecision(True, "ophthalmic measurement")
    if known_ids and any(g in known_ids for g in u.guidance_ids):
        return ScopeDecision(True, "names guidance or a trial in the index")
    if has_context:
        return ScopeDecision(True, "ophthalmic patient context supplied")
    if in_scope_conversation:
        return ScopeDecision(True, "follow up in an eye care conversation")
    return ScopeDecision(False, "no eye care content")
