"""Command line access to the assistant and every deterministic tool.

Examples::

    fovea ask "Is faricimab recommended for diabetic macular oedema?"
    fovea acuity 6/18
    fovea iol 23.45 43.25 44.00 --a 118.7 --target -0.25
    fovea grade irma exudate_within_1dd
    fovea interval faricimab dmo 6 12 --fluid
    fovea iop 26 --cct 530
    fovea hcq 62 400 3 --tamoxifen
    fovea screen timolol --conditions asthma
    fovea serve
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from fovea.clinical import (
    ToolCard,
    ToolInputError,
    acuity,
    biometry,
    glaucoma,
    injections,
    safety_screen,
    screening,
    toxicity,
)
from fovea.domain import PatientContext


def _print_card(card: ToolCard) -> None:
    print(f"\n{card.title}{f' ({card.eye} eye)' if card.eye else ''}\n{'=' * len(card.title)}")
    print(card.summary)
    for line in card.working:
        print(f"  working: {line}")
    for finding in card.findings:
        print(
            f"  {finding.severity.upper()}: {finding.message}"
            + (f" [{finding.reference}]" if finding.reference else "")
        )
    if card.missing:
        print("  missing: " + ", ".join(card.missing))
    print(f"  rules: {card.provenance}")


def _ask(question: str, provider: str | None) -> None:
    from fovea.container import get_container
    from fovea.generation.pipeline import AskInput

    result: dict[str, Any] = get_container().pipeline.ask(AskInput(question, provider=provider))
    for alert in result["emergencies"]:
        print(f"\nEMERGENCY: {alert['name']}\n{alert['action']}")
    for card in result["tools"]:
        print(f"\n[tool] {card['title']}: {card['summary']}")
    final = result["final"]
    print(f"\n{final['answer']}\n")
    for source in result["sources"]:
        if final.get("grounding") and source["number"] in final["grounding"]["cited_sources"]:
            print(
                f"  [{source['number']}] {source['title']} ({source['source_label']}, {source['year']}) {source['url']}"
            )
    print(
        f"\nstatus={final['status']} provider={final['provider']} grounding={json.dumps(final['grounding'])}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fovea", description="Fovea Fathom AI command line")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ask", help="ask a cited question")
    p.add_argument("question")
    p.add_argument("--provider", choices=["anthropic", "openai", "ollama", "extractive"])

    p = sub.add_parser("acuity", help="convert a visual acuity")
    p.add_argument("value")

    p = sub.add_parser("iol", help="SRK/T lens power")
    p.add_argument("axial_length", type=float)
    p.add_argument("k1", type=float)
    p.add_argument("k2", type=float)
    p.add_argument("--a", type=float, default=118.4, dest="a_constant")
    p.add_argument("--target", type=float, default=0.0)

    p = sub.add_parser("grade", help="diabetic eye screening grade from feature flags")
    p.add_argument("features", nargs="*")
    p.add_argument("--va", default=None)

    p = sub.add_parser("interval", help="treat and extend plan")
    p.add_argument("agent")
    p.add_argument("condition")
    p.add_argument("injections", type=int)
    p.add_argument("interval", type=float, nargs="?")
    p.add_argument("--fluid", action="store_true")
    p.add_argument("--haemorrhage", action="store_true")

    p = sub.add_parser("iop", help="NG81 ocular hypertension threshold")
    p.add_argument("iop", type=float)
    p.add_argument("--cct", type=float)

    p = sub.add_parser("hcq", help="hydroxychloroquine monitoring plan")
    p.add_argument("weight", type=float)
    p.add_argument("daily_dose", type=float)
    p.add_argument("years", type=float)
    p.add_argument("--tamoxifen", action="store_true")
    p.add_argument("--egfr", type=float)

    p = sub.add_parser("screen", help="medication safety screen")
    p.add_argument("planned", nargs="+")
    p.add_argument("--medicines", nargs="*", default=[])
    p.add_argument("--conditions", nargs="*", default=[])
    p.add_argument("--allergies", nargs="*", default=[])

    p = sub.add_parser("serve", help="run the API")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    try:
        if args.command == "ask":
            _ask(args.question, args.provider)
        elif args.command == "acuity":
            _print_card(acuity.convert(args.value))
        elif args.command == "iol":
            _print_card(
                biometry.calculate(
                    biometry.BiometryInput(args.axial_length, args.k1, args.k2, args.a_constant, args.target)
                )
            )
        elif args.command == "grade":
            flags: dict[str, Any] = {f: True for f in args.features}
            if args.va:
                flags["best_va"] = args.va
            _print_card(screening.grade(screening.ScreeningFeatures.from_dict(flags)))
        elif args.command == "interval":
            activity = injections.VisitActivity(
                intraretinal_fluid=args.fluid, new_haemorrhage=args.haemorrhage
            )
            _print_card(injections.plan(args.agent, args.condition, args.injections, args.interval, activity))
        elif args.command == "iop":
            _print_card(glaucoma.oht_assessment(args.iop, args.cct))
        elif args.command == "hcq":
            _print_card(
                toxicity.monitoring_plan(
                    args.weight, args.daily_dose, args.years, tamoxifen=args.tamoxifen, egfr=args.egfr
                )
            )
        elif args.command == "screen":
            ctx = PatientContext(
                medicines=args.medicines, conditions=args.conditions, allergies=args.allergies
            )
            _print_card(safety_screen.screen(safety_screen.ScreenInput(args.planned, ctx)))
        elif args.command == "serve":
            import uvicorn

            uvicorn.run("fovea.main:app", host=args.host, port=args.port)
    except ToolInputError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
