#!/usr/bin/env python3
"""CLI for DingTalk/WeCom collaboration export collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from collaboration_exports.parser import (
    PLATFORMS,
    build_manifest,
    collect_from_inputs_with_audit,
    normalize_platform,
    now_iso,
    write_json,
    write_jsonl,
    write_summary,
)


def collect(args: argparse.Namespace) -> int:
    platform = normalize_platform(args.platform)
    collected_at = args.collected_at or now_iso()
    events, collection_audit = collect_from_inputs_with_audit(
        args.input or [],
        platform=platform,
        collected_at=collected_at,
        limit=args.limit,
        allow_source_platforms=args.allow_source_platform,
        deny_source_platforms=args.deny_source_platform,
        allow_record_kinds=args.allow_record_kind,
        deny_record_kinds=args.deny_record_kind,
        allow_chats=args.allow_chat,
        deny_chats=args.deny_chat,
        allow_senders=args.allow_sender,
        deny_senders=args.deny_sender,
        allow_participants=args.allow_participant,
        deny_participants=args.deny_participant,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser()
        write_jsonl(out_dir / "lake" / platform / "events.jsonl", events)
        manifest = build_manifest(events, platform=platform, collected_at=collected_at, collection_audit=collection_audit)
        write_json(out_dir / "manifest.json", manifest)
        write_summary(out_dir / "SUMMARY.md", manifest)
    print(json.dumps({"collector": platform, "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized DingTalk/WeCom collaboration exports into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse local collaboration exports.")
    p_collect.add_argument("--platform", required=True, choices=sorted(PLATFORMS), help="Collaboration platform to collect.")
    p_collect.add_argument("--input", action="append", help="Authorized export file or folder. Repeat for multiple inputs.")
    p_collect.add_argument("--out-dir", help="Output package directory.")
    p_collect.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    p_collect.add_argument("--allow-source-platform", action="append", help="Only keep records whose normalized source platform matches this term.")
    p_collect.add_argument("--deny-source-platform", action="append", help="Drop records whose normalized source platform matches this term.")
    p_collect.add_argument("--allow-record-kind", action="append", help="Only keep records whose kind matches this term, such as message, meeting, file, chat, or contact.")
    p_collect.add_argument("--deny-record-kind", action="append", help="Drop records whose kind matches this term.")
    p_collect.add_argument("--allow-chat", action="append", help="Only keep records whose chat/conversation surface matches this term.")
    p_collect.add_argument("--deny-chat", action="append", help="Drop records whose chat/conversation surface matches this term.")
    p_collect.add_argument("--allow-sender", action="append", help="Only keep records whose sender/receiver surface matches this term.")
    p_collect.add_argument("--deny-sender", action="append", help="Drop records whose sender/receiver surface matches this term.")
    p_collect.add_argument("--allow-participant", action="append", help="Only keep records whose participant surface matches this term.")
    p_collect.add_argument("--deny-participant", action="append", help="Drop records whose participant surface matches this term.")
    p_collect.add_argument("--allow-keyword", action="append", help="Only keep records whose title/content/file/link/tag surface matches this term.")
    p_collect.add_argument("--deny-keyword", action="append", help="Drop records whose title/content/file/link/tag surface matches this term.")
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
