#!/usr/bin/env python3
"""CLI for the metadata-only filesystem collector."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from filesystem_collector.scanner import (
    default_roots,
    now_iso,
    platform_default_root_plan,
    scan_files_with_audit,
    stable_id,
    write_json,
    write_jsonl,
)


def build_filesystem_gap_event(source_audit: dict, *, readiness_status: str) -> dict:
    timestamp = now_iso()
    policy = source_audit.get("filesystem_scope_policy") or {}
    filtered_all = bool(source_audit.get("filesystem_scope_policy_filtered_all"))
    gap = "filesystem_scope_policy_filtered_all" if filtered_all else "filesystem_no_metadata_events_collected"
    status = "scope_policy_filtered_all" if filtered_all else readiness_status
    data = {
        "subtype": "collector_gap",
        "gap": gap,
        "status": status,
        "profile_type": gap,
        "root_count": source_audit.get("root_count", 0),
        "resolved_root_count": source_audit.get("resolved_root_count", 0),
        "missing_root_count": source_audit.get("missing_root_count", 0),
        "scanned_file_count": source_audit.get("scanned_file_count", 0),
        "candidate_file_count": policy.get("candidate_file_count", 0),
        "retained_event_count": 0,
        "filtered_file_count": policy.get("filtered_file_count", 0),
        "filter_reason_counts": policy.get("filter_reason_counts", {}),
        "skipped_file_count": source_audit.get("skipped_file_count", 0),
        "skipped_directory_count": source_audit.get("skipped_directory_count", 0),
        "skipped_reason_counts": source_audit.get("skipped_reason_counts", {}),
        "policy_is_user_authorization_scope": bool(policy.get("policy_is_user_authorization_scope", True)),
        "policy_does_not_assert_investment_relevance": True,
        "metadata_only": True,
        "file_content_collected": False,
        "file_metadata_events_written": False,
        "whole_disk_scan_claimed": False,
        "investment_relevance_claimed": False,
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(
            gap,
            data["root_count"],
            data["scanned_file_count"],
            data["candidate_file_count"],
            data["filtered_file_count"],
            data["skipped_file_count"],
        ),
        "collector": "filesystem",
        "source": "本地文件元数据采集边界",
        "owner_scope": "personal",
        "kind": "profile",
        "time": timestamp,
        "collected_at": timestamp,
        "data": data,
        "raw_ref": {
            "metadata_only": True,
            "scope_policy_enabled": bool(policy.get("enabled")),
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["file_metadata", "collection_gap"],
        },
        "wiki_targets": ["investor.data_quality.collection_gaps"],
    }


def collect(args: argparse.Namespace) -> int:
    roots = [Path(root).expanduser() for root in args.root] if args.root else default_roots()
    extensions = set(args.extension or []) or None
    allow_extensions = [*(args.extension or []), *(args.allow_extension or [])] or None
    ignore_dirs = set(args.ignore_dir or []) or None
    events, source_audit = scan_files_with_audit(
        roots,
        extensions=extensions,
        ignore_dirs=ignore_dirs,
        allow_extensions=allow_extensions,
        deny_extensions=args.deny_extension,
        allow_paths=args.allow_path,
        deny_paths=args.deny_path,
        allow_file_names=args.allow_file_name,
        deny_file_names=args.deny_file_name,
        allow_directories=args.allow_directory,
        deny_directories=args.deny_directory,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
        max_size_mb=args.max_size_mb,
        limit=args.limit,
    )
    metadata_events = list(events)
    extension_counts = Counter((event.get("data") or {}).get("extension") or "<none>" for event in metadata_events)
    total_size_bytes = sum(int((event.get("data") or {}).get("size_bytes") or 0) for event in metadata_events)
    readiness_status = "events_collected" if events else "no_matching_files"
    if not events and source_audit.get("filesystem_scope_policy_filtered_all"):
        readiness_status = "scope_policy_filtered_all"
    output_events = events if events else [build_filesystem_gap_event(source_audit, readiness_status=readiness_status)]
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if out_dir:
        lake_path = out_dir / "lake" / "filesystem" / "events.jsonl"
        write_jsonl(lake_path, output_events)
        manifest = {
            "schema": "collectorx.filesystem_collect.manifest.v1",
            "collector": "filesystem",
            "event_count": len(output_events),
            "roots": [str(root) for root in roots],
            "kind_counts": dict(Counter(event["kind"] for event in output_events)),
            "extension_counts": dict(sorted(extension_counts.items())),
            "file_surface_summary": {
                "metadata_event_count": len(metadata_events),
                "content_read_event_count": 0,
                "gap_event_count": max(0, len(output_events) - len(metadata_events)),
                "total_size_bytes": total_size_bytes,
                "extension_counts": dict(sorted(extension_counts.items())),
            },
            "source_audit": source_audit,
            "filesystem_boundary_proof": {
                "source_type": "authorized_local_filesystem_metadata",
                "metadata_only": True,
                "content_read": False,
                "root_count": source_audit.get("root_count", 0),
                "resolved_root_count": source_audit.get("resolved_root_count", 0),
                "missing_root_count": source_audit.get("missing_root_count", 0),
                "scanned_file_count": source_audit.get("scanned_file_count", 0),
                "emitted_event_count": source_audit.get("emitted_event_count", 0),
                "gap_event_count": max(0, len(output_events) - len(metadata_events)),
                "skipped_file_count": source_audit.get("skipped_file_count", 0),
                "skipped_directory_count": source_audit.get("skipped_directory_count", 0),
                "authorization_scope_boundary": source_audit.get("filesystem_scope_policy", {}),
                "complete_filesystem_claimed": False,
                "whole_disk_scan_claimed": False,
                "file_content_collected": False,
                "investment_relevance_claimed": False,
            },
            "content_read": False,
            "metadata_only": True,
            "platform_default_root_plan": platform_default_root_plan(),
            "collection_readiness": {
                "status": readiness_status,
                "can_enter_finclaw": bool(metadata_events),
                "source_collection_scope": "authorized_roots",
                "source_audit_status": "available",
                "filesystem_scope_policy_filtered_all": bool(source_audit.get("filesystem_scope_policy_filtered_all")),
                "content_read": False,
                "next_action": (
                    "Review filesystem scope-policy allow/deny filters."
                    if readiness_status == "scope_policy_filtered_all"
                    else (
                        "Review authorized roots and supported file extensions."
                        if not metadata_events
                        else "Feed lake/filesystem/events.jsonl into research-documents lens."
                    )
                ),
            },
        }
        write_json(out_dir / "manifest.json", manifest)
        (out_dir / "SUMMARY.md").write_text(
            "\n".join(
                [
                    "# 本地文件元数据采集包",
                    "",
                    f"- 事件数：{len(output_events)}",
                    f"- 文件元数据事件数：{len(metadata_events)}",
                    f"- 扫描文件数：{source_audit.get('scanned_file_count', 0)}",
                    f"- 跳过文件数：{source_audit.get('skipped_file_count', 0)}",
                    "- 内容读取：false",
                    "- 边界：只采路径、大小、mtime、扩展名等元数据。",
                ]
            ),
            encoding="utf-8",
        )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), output_events)
    if args.format == "json":
        print(json.dumps(output_events, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "event_count": len(output_events),
                    "metadata_event_count": len(metadata_events),
                    "content_read": False,
                    "skipped_file_count": source_audit.get("skipped_file_count", 0),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect local file metadata without reading file content.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Scan authorized roots and output file metadata events.")
    p.add_argument("--root", action="append", help="Authorized root file/folder. Repeat for multiple roots.")
    p.add_argument("--extension", action="append", help="Backward-compatible alias for --allow-extension.")
    p.add_argument("--allow-extension", action="append", help="Only keep matching file extensions without dot. Repeat or comma-separate.")
    p.add_argument("--deny-extension", action="append", help="Exclude matching file extensions without dot. Repeat or comma-separate.")
    p.add_argument("--allow-path", action="append", help="Only keep files whose metadata path contains this pattern.")
    p.add_argument("--deny-path", action="append", help="Exclude files whose metadata path contains this pattern.")
    p.add_argument("--allow-file-name", action="append", help="Only keep files whose file name contains this pattern.")
    p.add_argument("--deny-file-name", action="append", help="Exclude files whose file name contains this pattern.")
    p.add_argument("--allow-directory", action="append", help="Only keep files whose parent directory path contains this pattern.")
    p.add_argument("--deny-directory", action="append", help="Exclude files whose parent directory path contains this pattern.")
    p.add_argument("--allow-keyword", action="append", help="Only keep files whose metadata path/name/extension contains this keyword.")
    p.add_argument("--deny-keyword", action="append", help="Exclude files whose metadata path/name/extension contains this keyword.")
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
