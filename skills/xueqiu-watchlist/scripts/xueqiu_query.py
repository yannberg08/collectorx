#!/usr/bin/env python3
"""CLI for Xueqiu watchlist collection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from xueqiu.parser import build_manifest, collect_from_inputs, now_iso, parse_watchlist_csv, write_json, write_jsonl, write_summary

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events = collect_from_inputs(args.input or [], collected_at=collected_at, limit=args.limit)
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser()
        write_jsonl(out_dir / "lake" / "xueqiu-watchlist" / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at)
        write_json(out_dir / "manifest.json", manifest)
        write_summary(out_dir / "SUMMARY.md", manifest)
    print(json.dumps({"collector": "xueqiu-watchlist", "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def legacy(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.file:
        parser.print_help()
        return 2
    records = parse_watchlist_csv(args.file)
    print(f"解析完成: {len(records)} 只股票")
    if args.list:
        print("\n关注列表")
        print("=" * 40)
        for record in records:
            print(f"{record.get('symbol') or record.get('code')} {record.get('name', '')} {record.get('industry', '')} {record.get('note', '')}")
    if args.export:
        Path(args.export).expanduser().write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"导出完成: {args.export}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="雪球关注列表采集")
    sub = parser.add_subparsers(dest="command")
    p_collect = sub.add_parser("collect", help="Parse authorized Xueqiu watchlist exports into CollectorX events.")
    p_collect.add_argument("--input", action="append", help="Authorized watchlist export file or folder.")
    p_collect.add_argument("--out-dir", help="Output package directory.")
    p_collect.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    p_collect.set_defaults(func=collect)

    parser.add_argument("--file", help="Legacy mode: watchlist CSV/JSON file path.")
    parser.add_argument("--export", help="Legacy mode: export normalized JSON path.")
    parser.add_argument("--list", action="store_true", help="Legacy mode: print watchlist.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        return args.func(args)
    return legacy(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
