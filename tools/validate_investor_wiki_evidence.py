#!/usr/bin/env python3
"""Validate a FinClaw Investor Wiki evidence package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectorx.investor_wiki import validate_evidence_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate finclaw.investor_wiki_evidence.v1 packages.")
    parser.add_argument("path", help="Path to investor_wiki_evidence.v1.json")
    parser.add_argument("--allow-route-only", action="store_true", help="Do not require the canonical 7/20 dimension tree.")
    args = parser.parse_args()

    errors = validate_evidence_file(Path(args.path), require_dimensions=not args.allow_route_only)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Investor Wiki evidence contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
