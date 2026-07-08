#!/usr/bin/env python3
"""CLI for social activity collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from social_activity.parser import (
    COLLECTOR,
    build_manifest,
    collect_from_inputs_with_audit,
    now_iso,
    write_json,
    write_jsonl,
    write_summary,
)


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events, collection_audit = collect_from_inputs_with_audit(args.input or [], collected_at=collected_at, limit=args.limit)
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser()
        write_jsonl(out_dir / "lake" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
        write_json(out_dir / "manifest.json", manifest)
        write_summary(out_dir / "SUMMARY.md", manifest)
    print(json.dumps({"collector": COLLECTOR, "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized social platform activities into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Parse Weibo/Bilibili/Xiaohongshu activity exports or ZIP packages.")
    p.add_argument("--input", action="append", help="Authorized file, folder, or ZIP package. Repeat for multiple inputs.")
    p.add_argument("--out-dir", help="Output package directory.")
    p.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p.add_argument("--limit", type=int, help="Maximum events to write.")
    p.add_argument("--collected-at", help="Override collection timestamp.")
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
