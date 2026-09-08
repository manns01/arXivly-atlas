"""Orchestrator: fetch today's papers, build the atlas, render the site.

    python build.py                 # fetch -> atlas -> generate
    python build.py --date 2026-09-07   # skip fetch, rebuild from existing data/raw/

Any stage returning non-zero stops the run and propagates that exit code, so a
failed fetch never publishes a half-built site.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import build_atlas
import fetch_arxiv
import generate_site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", metavar="YYYY-MM-DD",
        help="skip the network fetch and rebuild the atlas + site from the "
             "existing data/raw/ files (the named day's file must already exist)",
    )
    args = parser.parse_args(argv)

    if args.date:
        raw = Path("data/raw") / f"{args.date}.json"
        if not raw.exists():
            print(f"{raw} does not exist -- nothing to rebuild", file=sys.stderr)
            return 1
        print(f"--date {args.date}: skipping fetch")
    else:
        rc = fetch_arxiv.main()
        if rc != 0:
            return rc

    rc = build_atlas.main()
    if rc != 0:
        return rc

    return generate_site.main()


if __name__ == "__main__":
    raise SystemExit(main())
