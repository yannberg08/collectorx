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
        include_image_ocr=args.include_image_ocr,
        limit=args.limit,
        min_score=args.min_score,
        include_non_matches=args.include_non_matches,
        allow_chats=args.allow_chat,
        deny_chats=args.deny_chat,
        allow_senders=args.allow_sender,
        deny_senders=args.deny_sender,
        allow_email_sender_domains=args.allow_email_sender_domain,
        deny_email_sender_domains=args.deny_email_sender_domain,
        allow_email_folders=args.allow_email_folder,
        deny_email_folders=args.deny_email_folder,
        allow_email_mailboxes=args.allow_email_mailbox,
        deny_email_mailboxes=args.deny_email_mailbox,
        allow_email_subjects=args.allow_email_subject,
        deny_email_subjects=args.deny_email_subject,
        allow_email_attachments=args.allow_email_attachment,
        deny_email_attachments=args.deny_email_attachment,
        allow_email_surfaces=args.allow_email_surface,
        deny_email_surfaces=args.deny_email_surface,
        allow_email_keywords=args.allow_email_keyword,
        deny_email_keywords=args.deny_email_keyword,
        allow_social_platforms=args.allow_social_platform,
        deny_social_platforms=args.deny_social_platform,
        allow_social_actions=args.allow_social_action,
        deny_social_actions=args.deny_social_action,
        allow_social_source_apps=args.allow_social_source_app,
        deny_social_source_apps=args.deny_social_source_app,
        allow_social_domains=args.allow_social_domain,
        deny_social_domains=args.deny_social_domain,
        allow_social_creators=args.allow_social_creator,
        deny_social_creators=args.deny_social_creator,
        allow_social_topics=args.allow_social_topic,
        deny_social_topics=args.deny_social_topic,
        allow_social_keywords=args.allow_social_keyword,
        deny_social_keywords=args.deny_social_keyword,
        allow_extensions=args.allow_extension,
        deny_extensions=args.deny_extension,
        allow_paths=args.allow_path,
        deny_paths=args.deny_path,
        allow_file_names=args.allow_file_name,
        deny_file_names=args.deny_file_name,
        allow_parsers=args.allow_parser,
        deny_parsers=args.deny_parser,
        allow_research_surfaces=args.allow_research_surface,
        deny_research_surfaces=args.deny_research_surface,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
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
    p_collect.add_argument("--include-image-ocr", action="store_true", help="Run an explicitly authorized image OCR adapter for screenshots/images when available.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--min-score", type=float, default=0.30, help="Minimum investment relevance score for lens sources.")
    p_collect.add_argument("--include-non-matches", action="store_true", help="Audit mode: include readable non-matching records with classification metadata.")
    p_collect.add_argument("--allow-chat", action="append", help="Only keep records whose chat/source contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--deny-chat", action="append", help="Drop records whose chat/source contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--allow-sender", action="append", help="Only keep records whose sender/author contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--deny-sender", action="append", help="Drop records whose sender/author contains this name. Repeat or comma-separate.")
    p_collect.add_argument("--allow-email-sender-domain", action="append", help="Email research: only keep matching sender domains.")
    p_collect.add_argument("--deny-email-sender-domain", action="append", help="Email research: exclude matching sender domains.")
    p_collect.add_argument("--allow-email-folder", action="append", help="Email research: only keep matching mailbox folders.")
    p_collect.add_argument("--deny-email-folder", action="append", help="Email research: exclude matching mailbox folders.")
    p_collect.add_argument("--allow-email-mailbox", action="append", help="Email research: only keep matching mailbox/account identifiers.")
    p_collect.add_argument("--deny-email-mailbox", action="append", help="Email research: exclude matching mailbox/account identifiers.")
    p_collect.add_argument("--allow-email-subject", action="append", help="Email research: only keep matching subjects.")
    p_collect.add_argument("--deny-email-subject", action="append", help="Email research: exclude matching subjects.")
    p_collect.add_argument("--allow-email-attachment", action="append", help="Email research: only keep matching attachment filenames.")
    p_collect.add_argument("--deny-email-attachment", action="append", help="Email research: exclude matching attachment filenames.")
    p_collect.add_argument("--allow-email-surface", action="append", help="Email research: only keep matching surfaces such as broker_research_report or roadshow_invite.")
    p_collect.add_argument("--deny-email-surface", action="append", help="Email research: exclude matching surfaces.")
    p_collect.add_argument("--allow-email-keyword", action="append", help="Email research: only keep records whose sender/subject/preview/attachment metadata match keyword.")
    p_collect.add_argument("--deny-email-keyword", action="append", help="Email research: exclude records whose sender/subject/preview/attachment metadata match keyword.")
    p_collect.add_argument("--allow-social-platform", action="append", help="Social influence: only keep matching platforms such as weibo, bilibili, or xiaohongshu.")
    p_collect.add_argument("--deny-social-platform", action="append", help="Social influence: exclude matching platforms.")
    p_collect.add_argument("--allow-social-action", action="append", help="Social influence: only keep matching activity actions such as watch, like, favorite, follow, comment, or share.")
    p_collect.add_argument("--deny-social-action", action="append", help="Social influence: exclude matching activity actions.")
    p_collect.add_argument("--allow-social-source-app", action="append", help="Social influence: only keep matching source apps such as chromium_history or safari_history.")
    p_collect.add_argument("--deny-social-source-app", action="append", help="Social influence: exclude matching source apps.")
    p_collect.add_argument("--allow-social-domain", action="append", help="Social influence: only keep records whose URL domain matches this domain.")
    p_collect.add_argument("--deny-social-domain", action="append", help="Social influence: exclude records whose URL domain matches this domain.")
    p_collect.add_argument("--allow-social-creator", action="append", help="Social influence: only keep records whose creator/author/account matches this pattern.")
    p_collect.add_argument("--deny-social-creator", action="append", help="Social influence: exclude records whose creator/author/account matches this pattern.")
    p_collect.add_argument("--allow-social-topic", action="append", help="Social influence: only keep matching social topics such as market_strategy or industry_theme.")
    p_collect.add_argument("--deny-social-topic", action="append", help="Social influence: exclude matching social topics.")
    p_collect.add_argument("--allow-social-keyword", action="append", help="Social influence: only keep records whose social metadata or preview matches keyword.")
    p_collect.add_argument("--deny-social-keyword", action="append", help="Social influence: exclude records whose social metadata or preview matches keyword.")
    p_collect.add_argument("--allow-extension", action="append", help="Research documents: only keep matching file extensions, e.g. pdf, xlsx, md.")
    p_collect.add_argument("--deny-extension", action="append", help="Research documents: exclude matching file extensions.")
    p_collect.add_argument("--allow-path", action="append", help="Research documents: only keep records whose path/source contains this pattern.")
    p_collect.add_argument("--deny-path", action="append", help="Research documents: exclude records whose path/source contains this pattern.")
    p_collect.add_argument("--allow-file-name", action="append", help="Research documents: only keep records whose file name contains this pattern.")
    p_collect.add_argument("--deny-file-name", action="append", help="Research documents: exclude records whose file name contains this pattern.")
    p_collect.add_argument("--allow-parser", action="append", help="Research documents: only keep records parsed by this parser, e.g. text, openpyxl, pdfplumber.")
    p_collect.add_argument("--deny-parser", action="append", help="Research documents: exclude records parsed by this parser.")
    p_collect.add_argument("--allow-research-surface", action="append", help="Research documents: only keep matching surfaces, e.g. valuation_model, financial_statement.")
    p_collect.add_argument("--deny-research-surface", action="append", help="Research documents: exclude matching research surfaces.")
    p_collect.add_argument("--allow-keyword", action="append", help="Research documents: only keep records whose metadata/content contains this keyword.")
    p_collect.add_argument("--deny-keyword", action="append", help="Research documents: exclude records whose metadata/content contains this keyword.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
