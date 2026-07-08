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
    events, collection_audit = collect_from_inputs_with_audit(args.input or [], collected_at=collected_at, limit=args.limit)
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
                    f"- archive_member_events：{manifest['source_audit']['archive_member_event_count']}",
                    f"- skipped_archive_members：{manifest['source_audit'].get('skipped_archive_member_count', 0)}",
                    f"- browser_history_events：{manifest['source_audit']['browser_history_event_count']}",
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
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
