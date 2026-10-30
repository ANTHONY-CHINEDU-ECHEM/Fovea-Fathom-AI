"""Ingestion command line: ``fovea-ingest seed | run | build | stats``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fovea.config import get_settings
from fovea.logging_setup import configure_logging
from ingestion.pipeline import build_index, harvest_all, load_seed, read_checkpoints


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fovea-ingest", description="Build the Fovea Fathom AI knowledge index"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="index the verified seed snapshot only")
    run = sub.add_parser("run", help="harvest every source, then build the index")
    run.add_argument("--quick", action="store_true", help="capped harvest for development")
    run.add_argument("--only", nargs="*", help="harvest only these sources")
    sub.add_parser("build", help="rebuild the index from checkpoints and the seed snapshot")
    sub.add_parser("stats", help="print the build manifest")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    out = Path(settings.index_dir)
    if args.command == "seed":
        _, manifest = build_index(settings, load_seed(), out)
    elif args.command == "run":
        harvest_all(settings, quick=args.quick, only=args.only)
        _, manifest = build_index(settings, load_seed() + read_checkpoints(), out)
    elif args.command == "build":
        _, manifest = build_index(settings, load_seed() + read_checkpoints(), out)
    else:
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    summary = {k: v for k, v in manifest.items() if k != "verification"}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
