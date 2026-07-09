#!/usr/bin/env python3
"""CLI for professional terminal usage collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pro_terminal_usage.parser import (
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
        allow_terminals=args.allow_terminal,
        deny_terminals=args.deny_terminal,
        allow_activities=args.allow_activity,
        deny_activities=args.deny_activity,
        allow_workspaces=args.allow_workspace,
        deny_workspaces=args.deny_workspace,
        allow_projects=args.allow_project,
        deny_projects=args.deny_project,
        allow_datasets=args.allow_dataset,
        deny_datasets=args.deny_dataset,
        allow_fields=args.allow_field,
        deny_fields=args.deny_field,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    if args.out_dir:
        out = Path(args.out_dir).expanduser()
        write_jsonl(out / "lake" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
        write_json(out / "manifest.json", manifest)
        write_json(out / "investor_wiki_evidence.v1.json", build_evidence(events, generated_at=collected_at, collection_audit=collection_audit))
        (out / "SUMMARY.md").write_text(
            "\n".join(
                [
                    "# 专业终端使用痕迹采集包",
                    "",
                    f"- collector：`{COLLECTOR}`",
                    f"- 事件数：{len(events)}",
                    f"- 可用工作流事件数：{manifest['usable_event_count']}",
                    f"- gap事件数：{manifest['gap_event_count']}",
                    f"- readiness：`{manifest['collection_readiness']['status']}`",
                    f"- business_lake_ready：`{manifest['collection_readiness']['can_enter_pro_terminal_usage_lake']}`",
                    f"- data_quality_lake_ready：`{manifest['collection_readiness']['can_enter_data_quality_lake']}`",
                    f"- wiki_evidence_ready：`{manifest['collection_readiness']['can_feed_investor_wiki_evidence']}`",
                    f"- observed_terminals：`{', '.join(manifest['terminal_coverage']['observed_terminals']) or 'none'}`",
                    f"- missing_expected_terminals：`{', '.join(manifest['terminal_coverage']['missing_expected_terminals']) or 'none'}`",
                    f"- observed_activities：`{', '.join(manifest['activity_coverage']['observed_activities']) or 'none'}`",
                    f"- missing_activities：`{', '.join(manifest['activity_coverage']['missing_expected_activities']) or 'none'}`",
                    f"- workflow_boundary_proof：`{manifest['workflow_boundary_proof']['proof_level']}`",
                    f"- licensed_content_mirrored：`{manifest['workflow_boundary_proof']['license_boundary']['licensed_content_mirrored']}`",
                    f"- scope_policy_enabled：{manifest['source_audit']['pro_terminal_scope_policy'].get('enabled', False)}",
                    f"- scope_policy_filtered：{manifest['source_audit'].get('scope_policy_filtered_record_count', 0)} / "
                    f"{manifest['source_audit'].get('candidate_record_count', manifest['source_audit'].get('parsed_record_count', 0))}",
                    f"- archive_member_events：{manifest['source_audit']['archive_member_event_count']}",
                    f"- skipped_archive_members：{manifest['source_audit'].get('skipped_archive_member_count', 0)}",
                    f"- source_section_events：{manifest['source_audit']['source_section_event_count']}",
                    f"- license_boundary：`{manifest['license_policy']['license_boundary']}`",
                    "- 边界：只采用户工作流元数据，不复制厂商数据库内容。",
                ]
            ),
            encoding="utf-8",
        )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    print(json.dumps({"event_count": len(events), "collector": COLLECTOR}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized professional terminal workflow traces.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Parse Wind/Choice/iFinD/Bloomberg workflow exports or ZIP packages.")
    p.add_argument("--input", action="append", help="Authorized file, folder, or ZIP package. Repeat for multiple inputs.")
    p.add_argument("--out-dir")
    p.add_argument("--event-export")
    p.add_argument("--limit", type=int)
    p.add_argument("--collected-at")
    p.add_argument("--allow-terminal", action="append", help="Only collect matching terminals, e.g. wind, choice, ifind, bloomberg.")
    p.add_argument("--deny-terminal", action="append", help="Exclude matching terminals.")
    p.add_argument("--allow-activity", action="append", help="Only collect matching workflow activities, e.g. workspace, watchlist, search, download, model_template, factor_attention.")
    p.add_argument("--deny-activity", action="append", help="Exclude matching workflow activities.")
    p.add_argument("--allow-workspace", action="append", help="Only collect matching workspace names.")
    p.add_argument("--deny-workspace", action="append", help="Exclude matching workspace names.")
    p.add_argument("--allow-project", action="append", help="Only collect matching project, strategy, or portfolio names.")
    p.add_argument("--deny-project", action="append", help="Exclude matching project, strategy, or portfolio names.")
    p.add_argument("--allow-dataset", action="append", help="Only collect records with matching datasets.")
    p.add_argument("--deny-dataset", action="append", help="Exclude records with matching datasets.")
    p.add_argument("--allow-field", action="append", help="Only collect records with matching terminal fields or indicators.")
    p.add_argument("--deny-field", action="append", help="Exclude records with matching terminal fields or indicators.")
    p.add_argument("--allow-keyword", action="append", help="Only collect records whose workflow metadata contains a keyword.")
    p.add_argument("--deny-keyword", action="append", help="Exclude records whose workflow metadata contains a keyword.")
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
