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
    build_meeting_scope_policy,
    finalize_meeting_scope_policy_audit,
    gap_event,
    meeting_scope_policy_filter_reason,
    now_iso,
    write_json,
    write_jsonl,
    write_summary,
)
from meeting_artifacts.parser import finalize_collection_audit, new_collection_audit, parse_path, resolve_input_paths


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events = []
    inputs = args.input or []
    paths, input_audit = resolve_input_paths(inputs)
    collection_audit = new_collection_audit(inputs, paths, limit=args.limit, input_audit=input_audit)
    meeting_scope_policy = build_meeting_scope_policy(
        allow_source_platforms=args.allow_source_platform,
        deny_source_platforms=args.deny_source_platform,
        allow_participants=args.allow_participant,
        deny_participants=args.deny_participant,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    collection_audit["candidate_record_count"] = 0
    collection_audit["meeting_scope_policy"] = meeting_scope_policy
    collection_audit["meeting_scope_policy_filtered_all"] = False
    if not paths:
        events = [gap_event(collected_at=collected_at, reason="meeting_artifact_input_missing")]
    else:
        for path in paths:
            path_result = {
                "path": str(path),
                "extension": path.suffix.lower() or "<none>",
                "candidate_record_count": 0,
                "parsed_record_count": 0,
                "emitted_event_count": 0,
                "scope_policy_filtered_record_count": 0,
                "status": "parsed",
            }
            collection_audit["path_results"].append(path_result)
            records = parse_path(path, audit=collection_audit)
            path_result["candidate_record_count"] = len(records)
            path_result["parsed_record_count"] = len(records)
            collection_audit["candidate_record_count"] += len(records)
            collection_audit["parsed_record_count"] += len(records)
            for record in records:
                event = artifact_to_event(record, path=path, collected_at=collected_at)
                filter_reason = meeting_scope_policy_filter_reason(event, meeting_scope_policy)
                if filter_reason:
                    meeting_scope_policy["filtered_record_count"] += 1
                    reason_counts = meeting_scope_policy.setdefault("filter_reason_counts", {})
                    reason_counts[filter_reason] = int(reason_counts.get(filter_reason, 0)) + 1
                    path_result["scope_policy_filtered_record_count"] += 1
                    continue
                events.append(event)
                path_result["emitted_event_count"] += 1
                if args.limit is not None and len(events) >= args.limit:
                    break
            if path_result["candidate_record_count"] and path_result["scope_policy_filtered_record_count"] == path_result["candidate_record_count"]:
                path_result["status"] = "filtered_by_scope_policy"
            if args.limit is not None and len(events) >= args.limit:
                break
    collection_audit["emitted_event_count"] = len(events)
    finalize_collection_audit(collection_audit)
    finalize_meeting_scope_policy_audit(collection_audit)

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
    p_collect.add_argument("--allow-source-platform", action="append", help="Only keep meeting artifacts whose normalized platform matches this term. Repeat or use comma-separated terms.")
    p_collect.add_argument("--deny-source-platform", action="append", help="Drop meeting artifacts whose normalized platform matches this term. Repeat or use comma-separated terms.")
    p_collect.add_argument("--allow-participant", action="append", help="Only keep meeting artifacts whose organizer/participant surface matches this term.")
    p_collect.add_argument("--deny-participant", action="append", help="Drop meeting artifacts whose organizer/participant surface matches this term.")
    p_collect.add_argument("--allow-keyword", action="append", help="Only keep meeting artifacts whose title/text/action/decision/risk surface matches this term.")
    p_collect.add_argument("--deny-keyword", action="append", help="Drop meeting artifacts whose title/text/action/decision/risk surface matches this term.")
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
