#!/usr/bin/env python3
"""CLI for generic calendar collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from calendar_collector.parser import build_manifest, collect_from_inputs, now_iso


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_summary(path: Path, manifest: dict) -> None:
    lines = [
        "# Calendar Collector Package",
        "",
        "- collector: `calendar`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- observed_platforms: `{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
        f"- missing_expected_platforms: `{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
        "",
        "Generic calendar events are not written to the investor Wiki directly. Use the task-calendar-investor lens.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events = collect_from_inputs(args.input or [], collected_at=collected_at, limit=args.limit)
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if out_dir:
        write_jsonl(out_dir / "lake" / "calendar" / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at)
        write_json(out_dir / "manifest.json", manifest)
        write_summary(out_dir / "SUMMARY.md", manifest)
    print(json.dumps({"collector": "calendar", "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized calendar exports into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse ICS/JSON/CSV/TSV/ZIP calendar exports.")
    p_collect.add_argument("--input", action="append", help="Authorized calendar export file/folder.")
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
