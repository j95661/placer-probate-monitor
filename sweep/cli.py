"""CLI: python -m sweep run [--case S-PR-...] [--since YYYY-MM-DD] [--max-searches N] [--refresh]."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sweep",
        description="Dual Affidavit of Death sweep for Placer probate listings (read-only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the affidavit sweep pipeline")
    run.add_argument("--case", help="Limit to one case number (or comma-separated list)")
    run.add_argument("--since", help="Only listings with last_seen >= YYYY-MM-DD")
    run.add_argument("--max-searches", type=int, default=40, help="Hard cap on live recorder searches")
    run.add_argument("--refresh", action="store_true", help="Ignore caches / TTLs")
    run.add_argument(
        "--fixtures",
        type=Path,
        help="Offline fixture directory (CI / acceptance). Skips live HA + CountyFusion.",
    )
    run.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root for data/ and out/ (default: repo root)",
    )
    run.add_argument("--top", type=int, default=25, help="Top N leads in leads.md")
    run.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("version", help="Print package version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        from . import __version__

        print(__version__)
        return 0

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Never let requests/urllib3 log Authorization headers.
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if args.command != "run":
        parser.error(f"unknown command {args.command}")

    from .pipeline import SweepRunner
    from .sources.ha import load_dotenv

    load_dotenv()
    root = Path(args.root) if args.root else _repo_root()
    fixtures = Path(args.fixtures) if args.fixtures else None
    # Default acceptance fixtures when HA_TOKEN missing and fixtures exist.
    if fixtures is None and not __import__("os").environ.get("HA_TOKEN"):
        default_fix = Path(__file__).resolve().parent / "tests" / "fixtures"
        if (default_fix / "listings" / "listings.json").exists():
            logging.getLogger(__name__).info(
                "HA_TOKEN unset; using bundled fixtures at %s", default_fix
            )
            fixtures = default_fix

    runner = SweepRunner(
        root,
        fixtures_dir=fixtures,
        max_searches=args.max_searches,
        refresh=args.refresh,
        offline=fixtures is not None,
    )
    try:
        results = runner.run(case=args.case, since=args.since, top_n=args.top)
    finally:
        runner.close()

    yes = sum(1 for r in results if r.dual.dual_signal == "yes")
    maybe = sum(1 for r in results if r.dual.dual_signal == "maybe")
    sold = sum(1 for r in results if r.dual.dual_signal == "sold")
    print(
        f"Sweep complete: {len(results)} cases "
        f"(yes={yes}, maybe={maybe}, sold={sold}). "
        f"Outputs in {root / 'out'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
