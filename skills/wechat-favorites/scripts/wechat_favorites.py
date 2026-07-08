#!/usr/bin/env python3
"""CLI for collecting WeChat favorites and public-account articles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wechat_favorites.events import (
    COLLECTOR,
    build_manifest,
    build_wechat_favorites_scope_policy,
    favorite_to_event,
    finalize_wechat_favorites_scope_policy_audit,
    gap_event,
    now_iso,
    wechat_favorites_scope_policy_filter_reason,
    write_json,
    write_jsonl,
    write_summary,
)
from wechat_favorites.parser import collect_records_with_audit


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events = []
    records, collection_audit = collect_records_with_audit(args.input or [], limit=args.limit)
    wechat_favorites_scope_policy = build_wechat_favorites_scope_policy(
        allow_source_accounts=args.allow_source_account,
        deny_source_accounts=args.deny_source_account,
        allow_source_account_types=args.allow_source_account_type,
        deny_source_account_types=args.deny_source_account_type,
        allow_actions=args.allow_action,
        deny_actions=args.deny_action,
        allow_tags=args.allow_tag,
        deny_tags=args.deny_tag,
        allow_domains=args.allow_domain,
        deny_domains=args.deny_domain,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    collection_audit["candidate_record_count"] = len(records)
    collection_audit["wechat_favorites_scope_policy"] = wechat_favorites_scope_policy
    collection_audit["wechat_favorites_scope_policy_filtered_all"] = False
    for result in collection_audit.get("path_results") or []:
        result["candidate_record_count"] = int(result.get("parsed_record_count") or 0)
        result["scope_policy_filtered_record_count"] = 0
    if not records:
        events = [gap_event(collected_at=collected_at, reason="wechat_favorites_input_missing")]
    else:
        row_counts: dict[str, int] = {}
        for path, record in records:
            key = str(path)
            row_counts[key] = row_counts.get(key, 0) + 1
            event = favorite_to_event(record, path=path, row=row_counts[key], collected_at=collected_at)
            filter_reason = wechat_favorites_scope_policy_filter_reason(event, wechat_favorites_scope_policy)
            if filter_reason:
                wechat_favorites_scope_policy["filtered_record_count"] += 1
                reason_counts = wechat_favorites_scope_policy.setdefault("filter_reason_counts", {})
                reason_counts[filter_reason] = int(reason_counts.get(filter_reason, 0)) + 1
                increment_path_scope_filter_count(collection_audit, path)
                continue
            events.append(event)
    collection_audit["emitted_event_count"] = len(events)
    finalize_path_scope_policy_status(collection_audit)
    finalize_wechat_favorites_scope_policy_audit(collection_audit)

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
    parser = argparse.ArgumentParser(description="Collect user-authorized WeChat favorites/public-account articles into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse local WeChat favorites/article exports or ZIP packages.")
    p_collect.add_argument("--input", action="append", help="Authorized file, folder, or ZIP package. Repeat for multiple inputs.")
    p_collect.add_argument("--out-dir", help="Output package directory.")
    p_collect.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    p_collect.add_argument("--allow-source-account", action="append", help="Only keep records whose public account/author/source matches this term.")
    p_collect.add_argument("--deny-source-account", action="append", help="Drop records whose public account/author/source matches this term.")
    p_collect.add_argument("--allow-source-account-type", action="append", help="Only keep records whose normalized source account type matches this term.")
    p_collect.add_argument("--deny-source-account-type", action="append", help="Drop records whose normalized source account type matches this term.")
    p_collect.add_argument("--allow-action", action="append", help="Only keep records whose action matches this term, such as favorite, read, share, or saved_file.")
    p_collect.add_argument("--deny-action", action="append", help="Drop records whose action matches this term.")
    p_collect.add_argument("--allow-tag", action="append", help="Only keep records whose tag surface matches this term.")
    p_collect.add_argument("--deny-tag", action="append", help="Drop records whose tag surface matches this term.")
    p_collect.add_argument("--allow-domain", action="append", help="Only keep records whose URL domain matches this term.")
    p_collect.add_argument("--deny-domain", action="append", help="Drop records whose URL domain matches this term.")
    p_collect.add_argument("--allow-keyword", action="append", help="Only keep records whose title/source/text/reason/share/symbol surface matches this term.")
    p_collect.add_argument("--deny-keyword", action="append", help="Drop records whose title/source/text/reason/share/symbol surface matches this term.")
    p_collect.set_defaults(func=collect)
    return parser


def increment_path_scope_filter_count(collection_audit: dict, path: Path) -> None:
    target = str(path)
    for result in collection_audit.get("path_results") or []:
        if result.get("path") == target:
            result["scope_policy_filtered_record_count"] = int(result.get("scope_policy_filtered_record_count") or 0) + 1
            return


def finalize_path_scope_policy_status(collection_audit: dict) -> None:
    for result in collection_audit.get("path_results") or []:
        candidate_count = int(result.get("candidate_record_count") or 0)
        filtered_count = int(result.get("scope_policy_filtered_record_count") or 0)
        if candidate_count > 0 and filtered_count == candidate_count:
            result["status"] = "filtered_by_scope_policy"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
