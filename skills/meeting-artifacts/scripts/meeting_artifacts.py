#!/usr/bin/env python3
"""CLI for collecting local meeting artifacts into CollectorX events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from meeting_artifacts.events import (
    COLLECTOR,
    artifact_to_event,
    build_manifest,
    gap_event,
    now_iso,
    write_json,
    write_jsonl,
    write_summary,
)
from meeting_artifacts.parser import finalize_collection_audit, iter_paths, new_collection_audit, parse_path


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events = []
    inputs = args.input or []
    paths = list(iter_paths(inputs))
    collection_audit = new_collection_audit(inputs, paths, limit=args.limit)
    if not paths:
        events = [gap_event(collected_at=collected_at, reason="meeting_artifact_input_missing")]
    else:
        for path in paths:
            path_result = {
                "path": str(path),
                "extension": path.suffix.lower() or "<none>",
                "parsed_record_count": 0,
                "emitted_event_count": 0,
                "status": "parsed",
            }
            collection_audit["path_results"].append(path_result)
            records = parse_path(path, audit=collection_audit)
            path_result["parsed_record_count"] = len(records)
            collection_audit["parsed_record_count"] += len(records)
            for record in records:
                events.append(artifact_to_event(record, path=path, collected_at=collected_at))
                path_result["emitted_event_count"] += 1
                if args.limit is not None and len(events) >= args.limit:
                    break
            if args.limit is not None and len(events) >= args.limit:
                break
    collection_audit["emitted_event_count"] = len(events)
    finalize_collection_audit(collection_audit)

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
    parser = argparse.ArgumentParser(description="Collect user-authorized meeting minutes/transcripts into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse local meeting artifact files or ZIP packages.")
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
