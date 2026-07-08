#!/usr/bin/env python3
"""CLI for financial-news usage collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from financial_news_usage.parser import (
    COLLECTOR,
    build_evidence,
    build_manifest,
    collect_from_inputs_with_audit,
    now_iso,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


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
        allow_topics=args.allow_topic,
        deny_topics=args.deny_topic,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    if args.out_dir:
        out = Path(args.out_dir).expanduser()
        write_jsonl(out / "lake" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
        write_json(out / "manifest.json", manifest)
        write_json(out / "investor_wiki_evidence.v1.json", build_evidence(events, generated_at=collected_at))
        (out / "SUMMARY.md").write_text(
            "\n".join(
                [
                    "# 财经资讯使用痕迹采集包",
                    "",
                    f"- collector：`{COLLECTOR}`",
                    f"- 事件数：{len(events)}",
                    f"- readiness：`{manifest['collection_readiness']['status']}`",
                    f"- observed_platforms：`{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
                    f"- missing_expected_platforms：`{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
                    f"- observed_actions：`{', '.join(manifest['action_coverage']['observed_actions']) or 'none'}`",
                    f"- missing_expected_actions：`{', '.join(manifest['action_coverage']['missing_expected_actions']) or 'none'}`",
                    f"- field_coverage_missing：`{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
                    f"- behavior_fields：alert_condition={manifest['usage_behavior_summary']['events_with_alert_condition']}, "
                    f"subscription_target={manifest['usage_behavior_summary']['events_with_subscription_target']}, "
                    f"query_terms={manifest['usage_behavior_summary']['events_with_query_terms']}",
                    f"- scope_policy_enabled：{manifest['source_audit']['financial_news_scope_policy'].get('enabled', False)}",
                    f"- scope_policy_filtered：{manifest['source_audit'].get('scope_policy_filtered_record_count', 0)} / "
                    f"{manifest['source_audit'].get('candidate_record_count', manifest['source_audit'].get('parsed_record_count', 0))}",
                    f"- archive_member_events：{manifest['source_audit']['archive_member_event_count']}",
                    f"- skipped_archive_members：{manifest['source_audit'].get('skipped_archive_member_count', 0)}",
                    f"- browser_history_events：{manifest['source_audit']['browser_history_event_count']}",
                    f"- usage_boundary_proof：`{manifest['usage_boundary_proof']['proof_level']}`",
                    "- 边界：只采用户动作，不采公共新闻库。",
                ]
            ),
            encoding="utf-8",
        )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    print(json.dumps({"event_count": len(events), "collector": COLLECTOR}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized CLS/WallstreetCN/Gelonghui usage traces.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Parse financial news usage exports, saved pages, browser history, or ZIP packages.")
    p.add_argument("--input", action="append", help="Authorized file, folder, browser history copy, or ZIP package. Repeat for multiple inputs.")
    p.add_argument("--out-dir")
    p.add_argument("--event-export")
    p.add_argument("--limit", type=int)
    p.add_argument("--collected-at")
    p.add_argument("--allow-platform", action="append", help="Only collect matching platforms, e.g. cls, wallstreetcn, gelonghui.")
    p.add_argument("--deny-platform", action="append", help="Exclude matching platforms.")
    p.add_argument("--allow-action", action="append", help="Only collect matching actions, e.g. read, favorite, search, subscribe, alert.")
    p.add_argument("--deny-action", action="append", help="Exclude matching actions.")
    p.add_argument("--allow-source-app", action="append", help="Only collect matching source apps, e.g. cls_app, chromium_history, safari_history.")
    p.add_argument("--deny-source-app", action="append", help="Exclude matching source apps.")
    p.add_argument("--allow-domain", action="append", help="Only collect matching domains or subdomains.")
    p.add_argument("--deny-domain", action="append", help="Exclude matching domains or subdomains.")
    p.add_argument("--allow-topic", action="append", help="Only collect matching usage topics.")
    p.add_argument("--deny-topic", action="append", help="Exclude matching usage topics.")
    p.add_argument("--allow-keyword", action="append", help="Only collect records whose title/query/tags/symbols/text preview contain a keyword.")
    p.add_argument("--deny-keyword", action="append", help="Exclude records whose title/query/tags/symbols/text preview contain a keyword.")
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
