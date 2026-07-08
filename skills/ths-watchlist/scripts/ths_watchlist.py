#!/usr/bin/env python3
"""CLI for Tonghuashun watchlist collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ths_watchlist.parser import (
    THS_WATCHLIST_SCOPE_POLICY_KEYS,
    build_evidence,
    build_local_scan_report,
    build_manifest,
    collect_from_inputs_with_audit,
    find_local_watchlist_files,
    now_iso,
    write_json,
    write_jsonl,
    write_summary,
)


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    local_scan_files = find_local_watchlist_files(container_root=args.container_root, platform=args.platform) if args.local_scan else []
    if args.probe_export:
        write_json(
            Path(args.probe_export).expanduser(),
            build_local_scan_report(platform=args.platform, container_root=args.container_root, files=local_scan_files),
        )
    events, audit = collect_from_inputs_with_audit(
        args.input or [],
        collected_at=collected_at,
        limit=args.limit,
        local_scan=args.local_scan,
        platform=args.platform,
        container_root=args.container_root,
        scope_policy=scope_policy_from_args(args),
    )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser()
        write_jsonl(out_dir / "lake" / "ths-watchlist" / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at, collection_audit=audit)
        write_json(out_dir / "manifest.json", manifest)
        write_json(out_dir / "investor_wiki_evidence.v1.json", build_evidence(events, generated_at=collected_at))
        write_summary(out_dir / "SUMMARY.md", manifest)
    print(json.dumps({"collector": "ths-watchlist", "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized Tonghuashun watchlist exports or local watchlist files into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse local Tonghuashun watchlist exports or run an authorized local scan.")
    p_collect.add_argument("--input", action="append", help="Authorized watchlist export file or folder.")
    p_collect.add_argument("--local-scan", action="store_true", help="Scan authorized local Tonghuashun roots for likely watchlist files.")
    p_collect.add_argument("--platform", choices=["auto", "mac", "windows", "linux", "generic"], default="auto", help="Local scan platform adapter.")
    p_collect.add_argument("--container-root", help="Authorized local scan root; defaults to known Tonghuashun app data roots for the platform.")
    p_collect.add_argument("--probe-export", help="Write a local scan probe report JSON path.")
    p_collect.add_argument("--out-dir", help="Output package directory.")
    p_collect.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    add_scope_policy_args(p_collect)
    p_collect.set_defaults(func=collect)
    return parser


def add_scope_policy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-symbol", action="append", help="Only keep matching symbols/codes; repeat or comma-separate.")
    parser.add_argument("--deny-symbol", action="append", help="Exclude matching symbols/codes; repeat or comma-separate.")
    parser.add_argument("--allow-market", action="append", help="Only keep matching markets such as SH/SZ/BJ.")
    parser.add_argument("--deny-market", action="append", help="Exclude matching markets such as SH/SZ/BJ.")
    parser.add_argument("--allow-group", action="append", help="Only keep matching watchlist groups.")
    parser.add_argument("--deny-group", action="append", help="Exclude matching watchlist groups.")
    parser.add_argument("--allow-industry", action="append", help="Only keep matching industries/sectors.")
    parser.add_argument("--deny-industry", action="append", help="Exclude matching industries/sectors.")
    parser.add_argument("--allow-tag", action="append", help="Only keep matching tags.")
    parser.add_argument("--deny-tag", action="append", help="Exclude matching tags.")
    parser.add_argument("--allow-keyword", action="append", help="Only keep records whose symbol/name/group/industry/reason/tag/raw fields match keyword.")
    parser.add_argument("--deny-keyword", action="append", help="Exclude records whose symbol/name/group/industry/reason/tag/raw fields match keyword.")
    parser.add_argument("--allow-source", action="append", help="Only keep matching source paths, archive members, or source labels.")
    parser.add_argument("--deny-source", action="append", help="Exclude matching source paths, archive members, or source labels.")
    parser.add_argument("--allow-source-platform", action="append", help="Only keep matching local scan platforms such as mac/windows/linux.")
    parser.add_argument("--deny-source-platform", action="append", help="Exclude matching local scan platforms such as mac/windows/linux.")


def scope_policy_from_args(args: argparse.Namespace) -> dict:
    return {key: getattr(args, key, None) for key in THS_WATCHLIST_SCOPE_POLICY_KEYS}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
