"""Treat and extend planner for intravitreal anti VEGF therapy.

Given the agent, the condition, the number of injections given, the current interval and the
disease activity at today's visit, the planner returns the next interval according to the
configured regimen in ``injection_regimens.yaml``. Activity means any of: new or persistent
intraretinal or subretinal fluid, new macular haemorrhage, or a loss of five or more ETDRS
letters attributed to disease activity. The planner never chooses the agent; that remains a
decision for the clinician within NICE guidance.
"""

from __future__ import annotations

from dataclasses import dataclass

from fovea import knowledge
from fovea.clinical import ToolCard, ToolInputError

AGENT_ALIASES = {
    "eylea": "aflibercept",
    "aflibercept": "aflibercept",
    "lucentis": "ranibizumab",
    "ranibizumab": "ranibizumab",
    "byooviz": "ranibizumab",
    "ongavia": "ranibizumab",
    "vabysmo": "faricimab",
    "faricimab": "faricimab",
    "beovu": "brolucizumab",
    "brolucizumab": "brolucizumab",
}
CONDITION_ALIASES = {
    "wet_amd": "wet_amd",
    "namd": "wet_amd",
    "dmo": "dmo",
    "rvo": "rvo",
    "myopic_cnv": "myopic_cnv",
}


@dataclass
class VisitActivity:
    intraretinal_fluid: bool = False
    subretinal_fluid: bool = False
    new_haemorrhage: bool = False
    letters_lost: int = 0
    intraocular_inflammation: bool = False

    @property
    def active(self) -> bool:
        return (
            self.intraretinal_fluid or self.subretinal_fluid or self.new_haemorrhage or self.letters_lost >= 5
        )

    def reasons(self) -> list[str]:
        out = []
        if self.intraretinal_fluid:
            out.append("intraretinal fluid")
        if self.subretinal_fluid:
            out.append("subretinal fluid")
        if self.new_haemorrhage:
            out.append("new haemorrhage")
        if self.letters_lost >= 5:
            out.append(f"loss of {self.letters_lost} letters")
        return out


def plan(
    agent: str,
    condition: str,
    injections_given: int,
    current_interval_weeks: float | None,
    activity: VisitActivity,
    eye: str | None = None,
    consecutive_dry_at_max: int = 0,
) -> ToolCard:
    rules = knowledge.load("injection_regimens")
    agent_key = AGENT_ALIASES.get(agent.strip().lower())
    condition_key = CONDITION_ALIASES.get(condition.strip().lower())
    if not agent_key:
        raise ToolInputError(f"No treat and extend regimen is configured for {agent!r}")
    if not condition_key:
        raise ToolInputError(f"No treat and extend regimen is configured for condition {condition!r}")
    regimen = rules.data["regimens"].get(agent_key, {}).get(condition_key)
    if regimen is None:
        raise ToolInputError(f"No configured regimen for {agent_key} in {condition_key}")
    if injections_given < 0:
        raise ToolInputError("Injections given cannot be negative")

    card = ToolCard(
        tool="treat_and_extend",
        title=f"Treat and extend plan: {agent_key}",
        summary="",
        eye=eye,
        provenance=rules.provenance,
        references=[
            f"{agent_key.capitalize()} SmPC section 4.2 (posology)",
            "Local medical retina treat and extend protocol",
        ],
    )
    loading = int(regimen["loading_doses"])
    lo, hi = float(regimen["min_interval"]), float(regimen["max_interval"])
    step_up, step_down = float(regimen["extend_step"]), float(regimen["shorten_step"])
    card.working.append(regimen["note"])

    if activity.intraocular_inflammation:
        card.summary = (
            "Intraocular inflammation recorded: do not inject today; assess and treat the inflammation first."
        )
        card.warn(
            "contraindication",
            "Active intraocular inflammation is a contraindication to anti VEGF injection.",
            f"{agent_key} SmPC section 4.3",
        )
        if agent_key == "brolucizumab":
            card.warn(
                "major",
                "With brolucizumab, intraocular inflammation can precede retinal vasculitis or occlusion; review continuation.",
                "Brolucizumab SmPC section 4.4",
            )
        card.details = {"phase": "withheld", "next_interval_weeks": None}
        return card

    if injections_given < loading:
        next_interval = float(regimen["loading_interval"])
        phase = "loading"
        card.working.append(
            f"Loading phase: injection {injections_given + 1} of {loading}, every {next_interval:g} weeks."
        )
    else:
        phase = "maintenance"
        current = current_interval_weeks if current_interval_weeks is not None else lo
        if current_interval_weeks is None:
            card.missing.append("current interval in weeks (assumed to be the minimum interval)")
        if activity.active:
            next_interval = max(lo, current - step_down)
            card.working.append(
                f"Active disease ({', '.join(activity.reasons())}): shorten by {step_down:g} weeks to {next_interval:g}."
            )
            if current <= lo:
                card.warn(
                    "caution",
                    "Disease is active at the minimum interval. NG82 notes that switching agents may be considered for practical reasons but clinical benefit is likely to be limited.",
                    "NICE NG82",
                )
        else:
            next_interval = min(hi, current + step_up)
            card.working.append(f"Inactive disease: extend by {step_up:g} weeks to {next_interval:g}.")
            if next_interval >= hi:
                card.working.append(f"Maximum configured interval of {hi:g} weeks reached.")
                if consecutive_dry_at_max >= 2:
                    card.warn(
                        "info",
                        "Stable at the maximum interval on repeated visits; NG82 supports considering observation for stable disease, decided with the patient.",
                        "NICE NG82",
                    )

    card.summary = f"{phase.capitalize()} phase. Next injection in {next_interval:g} weeks."
    card.details = {
        "agent": agent_key,
        "condition": condition_key,
        "phase": phase,
        "disease_active": activity.active,
        "activity_reasons": activity.reasons(),
        "next_interval_weeks": next_interval,
        "min_interval_weeks": lo,
        "max_interval_weeks": hi,
    }
    card.warn(
        "info",
        "Regimen values are local protocol defaults summarised from the SmPC; confirm against the current SmPC.",
    )
    return card
