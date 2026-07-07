#!/usr/bin/env python3
"""CLI for the metadata-only filesystem collector."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from filesystem_collector.scanner import default_roots, platform_default_root_plan, scan_files, write_json, write_jsonl


def collect(args: argparse.Namespace) -> int:
    roots = [Path(root).expanduser() for root in args.root] if args.root else default_roots()
    extensions = set(args.extension or []) or None
    ignore_dirs = set(args.ignore_dir or []) or None
    events = scan_files(
        roots,
        extensions=extensions,
        ignore_dirs=ignore_dirs,
        max_size_mb=args.max_size_mb,
        limit=args.limit,
    )
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if out_dir:
        lake_path = out_dir / "lake" / "filesystem" / "events.jsonl"
        write_jsonl(lake_path, events)
        manifest = {
            "schema": "collectorx.filesystem_collect.manifest.v1",
            "collector": "filesystem",
            "event_count": len(events),
            "roots": [str(root) for root in roots],
            "kind_counts": dict(Counter(event["kind"] for event in events)),
            "content_read": False,
            "metadata_only": True,
            "platform_default_root_plan": platform_default_root_plan(),
            "collection_readiness": {
                "status": "events_collected" if events else "no_matching_files",
                "can_enter_finclaw": bool(events),
                "source_collection_scope": "authorized_roots",
                "content_read": False,
                "next_action": "Feed lake/filesystem/events.jsonl into research-documents lens.",
            },
        }
        write_json(out_dir / "manifest.json", manifest)
        (out_dir / "SUMMARY.md").write_text(
            "\n".join(
                [
                    "# 本地文件元数据采集包",
                    "",
                    f"- 事件数：{len(events)}",
                    "- 内容读取：false",
                    "- 边界：只采路径、大小、mtime、扩展名等元数据。",
                ]
            ),
            encoding="utf-8",
        )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if args.format == "json":
        print(json.dumps(events, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps({"event_count": len(events), "content_read": False}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect local file metadata without reading file content.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Scan authorized roots and output file metadata events.")
    p.add_argument("--root", action="append", help="Authorized root file/folder. Repeat for multiple roots.")
    p.add_argument("--extension", action="append", help="Allowed extension without dot. Repeatable.")
    p.add_argument("--ignore-dir", action="append", help="Additional directory basename to ignore.")
    p.add_argument("--max-size-mb", type=int, default=50)
    p.add_argument("--limit", type=int)
    p.add_argument("--out-dir")
    p.add_argument("--event-export")
    p.add_argument("--format", choices=["summary", "json"], default="summary")
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
