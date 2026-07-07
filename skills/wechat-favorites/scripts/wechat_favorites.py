#!/usr/bin/env python3
"""CLI for collecting WeChat favorites and public-account articles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wechat_favorites.events import (
    COLLECTOR,
    build_manifest,
    favorite_to_event,
    gap_event,
    now_iso,
    write_json,
    write_jsonl,
    write_summary,
)
from wechat_favorites.parser import iter_paths, parse_path


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events = []
    paths = list(iter_paths(args.input or []))
    if not paths:
        events = [gap_event(collected_at=collected_at, reason="wechat_favorites_input_missing")]
    else:
        for path in paths:
            for row, record in enumerate(parse_path(path), start=1):
                events.append(favorite_to_event(record, path=path, row=row, collected_at=collected_at))
                if args.limit is not None and len(events) >= args.limit:
                    break
            if args.limit is not None and len(events) >= args.limit:
                break

    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser()
        write_jsonl(out_dir / "lake" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at)
        write_json(out_dir / "manifest.json", manifest)
        write_summary(out_dir / "SUMMARY.md", manifest)

    print(json.dumps({"collector": COLLECTOR, "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized WeChat favorites/public-account articles into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse local WeChat favorites/article exports or ZIP packages.")
    p_collect.add_argument("--input", action="append", help="Authorized file, folder, or ZIP package. Repeat for multiple inputs.")
    p_collect.add_argument("--out-dir", help="Output package directory.")
    p_collect.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
