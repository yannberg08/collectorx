#!/usr/bin/env python3
"""CLI for collecting non-broker investor evidence into CollectorX events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from investor_sources.events import (
    build_investor_wiki_evidence,
    build_manifest,
    now_iso,
    write_json,
    write_jsonl,
)
from investor_sources.parser import collect_events_with_audit
from investor_sources.profiles import all_profiles, assert_profiles_cover_dimensions, get_profile


def list_sources(args: argparse.Namespace) -> int:
    profiles = all_profiles()
    if args.format == "json":
        print(json.dumps(profiles, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    for profile in profiles:
        print(
            f"{profile['id']}\t{profile.get('collector_class', 'unknown')}\t"
            f"{profile['priority']}\t{profile['display_name']}\t{profile['evidence_level']}"
        )
    return 0


def collect(args: argparse.Namespace) -> int:
    assert_profiles_cover_dimensions()
    profile = get_profile(args.source)
    collected_at = args.collected_at or now_iso()
    out_dir = Path(args.out_dir).expanduser()
    result = collect_events_with_audit(
        args.source,
        args.input or [],
        collected_at=collected_at,
        include_content=args.include_content,
        limit=args.limit,
        min_score=args.min_score,
        include_non_matches=args.include_non_matches,
        allow_chats=args.allow_chat,
        deny_chats=args.deny_chat,
        allow_senders=args.allow_sender,
        deny_senders=args.deny_sender,
    )
    events = result.events

    lake_path = out_dir / "lake" / args.source / "events.jsonl"
    manifest_path = out_dir / "manifest.json"
    evidence_path = out_dir / "investor_wiki_evidence.v1.json"
    summary_path = out_dir / "SUMMARY.md"

    write_jsonl(lake_path, events)
    manifest = build_manifest(args.source, events, collected_at=collected_at, collection_audit=result.audit)
    evidence = build_investor_wiki_evidence(events, generated_at=collected_at)
    write_json(manifest_path, manifest)
    write_json(evidence_path, evidence)
    write_summary(summary_path, profile, manifest, evidence)

    print(json.dumps({"out_dir": str(out_dir), "event_count": len(events), "status": manifest["collection_readiness"]["status"]}, ensure_ascii=False, sort_keys=True))
    return 0


def write_summary(path: Path, profile: Dict[str, Any], manifest: Dict[str, Any], evidence: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    coverage = evidence.get("coverage_summary", {})
    lines = [
        f"# {profile['display_name']}采集包",
        "",
        f"- collector：`{manifest['collector']}`",
        f"- 优先级：`{profile['priority']}`",
        f"- 事件数：{manifest['event_count']}",
        f"- readiness：`{manifest['collection_readiness']['status']}`",
        f"- 七大维度数：{coverage.get('dimension_count')}",
        f"- 子维度数：{coverage.get('subdimension_count')}",
        "",
        "本包只写入 CollectorX lake 和投资分身证据包，不直接写最终 Wiki。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect investor-avatar evidence from authorized non-broker sources.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-sources", help="List supported investor source profiles.")
    p_list.add_argument("--format", choices=["table", "json"], default="table")
    p_list.set_defaults(func=list_sources)

    p_collect = sub.add_parser("collect", help="Collect one source profile from local inputs.")
    p_collect.add_argument("--source", required=True, help="Source profile id, e.g. xueqiu-investor-activity.")
    p_collect.add_argument("--input", action="append", help="Authorized input file or folder. Repeat for multiple inputs.")
    p_collect.add_argument("--out-dir", required=True, help="Output directory.")
    p_collect.add_argument("--include-content", action="store_true", help="Include full text content for text files.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--min-score", type=float, default=0.30, help="Minimum investment relevance score for lens sources.")
    p_collect.add_argument("--include-non-matches", action="store_true", help="Audit mode: include readable non-matching records with classification metadata.")
    p_collect.add_argument("--allow-chat", action="append", help="Only keep records whose chat/source contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--deny-chat", action="append", help="Drop records whose chat/source contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--allow-sender", action="append", help="Only keep records whose sender/author contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--deny-sender", action="append", help="Drop records whose sender/author contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
