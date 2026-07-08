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
    events, collection_audit = collect_from_inputs_with_audit(
        args.input or [],
        collected_at=collected_at,
        limit=args.limit,
        allow_platforms=args.allow_platform,
        deny_platforms=args.deny_platform,
        allow_actions=args.allow_action,
        deny_actions=args.deny_action,
        allow_source_apps=args.allow_source_app,
        deny_source_apps=args.deny_source_app,
        allow_domains=args.allow_domain,
        deny_domains=args.deny_domain,
        allow_creators=args.allow_creator,
        deny_creators=args.deny_creator,
        allow_topics=args.allow_topic,
        deny_topics=args.deny_topic,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
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
    p = sub.add_parser("collect", help="Parse Weibo/Bilibili/Xiaohongshu activity exports, browser-history copies, or ZIP packages.")
    p.add_argument("--input", action="append", help="Authorized file, folder, browser-history copy, or ZIP package. Repeat for multiple inputs.")
    p.add_argument("--out-dir", help="Output package directory.")
    p.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p.add_argument("--limit", type=int, help="Maximum events to write.")
    p.add_argument("--collected-at", help="Override collection timestamp.")
    p.add_argument("--allow-platform", action="append", help="Only collect matching platforms, e.g. weibo, bilibili, xiaohongshu.")
    p.add_argument("--deny-platform", action="append", help="Exclude matching platforms.")
    p.add_argument("--allow-action", action="append", help="Only collect matching actions, e.g. follow, like, favorite, watch, comment, share.")
    p.add_argument("--deny-action", action="append", help="Exclude matching actions.")
    p.add_argument("--allow-source-app", action="append", help="Only collect matching source apps, e.g. chromium_history or safari_history.")
    p.add_argument("--deny-source-app", action="append", help="Exclude matching source apps.")
    p.add_argument("--allow-domain", action="append", help="Only collect matching domains or subdomains.")
    p.add_argument("--deny-domain", action="append", help="Exclude matching domains or subdomains.")
    p.add_argument("--allow-creator", action="append", help="Only collect matching creator names.")
    p.add_argument("--deny-creator", action="append", help="Exclude matching creator names.")
    p.add_argument("--allow-topic", action="append", help="Only collect records with matching social influence topics.")
    p.add_argument("--deny-topic", action="append", help="Exclude records with matching social influence topics.")
    p.add_argument("--allow-keyword", action="append", help="Only collect records whose social activity metadata contains a keyword.")
    p.add_argument("--deny-keyword", action="append", help="Exclude records whose social activity metadata contains a keyword.")
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
