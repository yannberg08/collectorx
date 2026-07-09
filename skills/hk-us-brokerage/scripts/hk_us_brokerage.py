#!/usr/bin/env python3
"""CLI for HK/US brokerage collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hk_us_brokerage.parser import (
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
        allow_brokers=args.allow_broker,
        deny_brokers=args.deny_broker,
        allow_accounts=args.allow_account,
        deny_accounts=args.deny_account,
        allow_subtypes=args.allow_subtype,
        deny_subtypes=args.deny_subtype,
        allow_symbols=args.allow_symbol,
        deny_symbols=args.deny_symbol,
        allow_markets=args.allow_market,
        deny_markets=args.deny_market,
        allow_currencies=args.allow_currency,
        deny_currencies=args.deny_currency,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    if args.out_dir:
        out = Path(args.out_dir).expanduser()
        write_jsonl(out / "lake" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
        write_json(out / "manifest.json", manifest)
        write_json(
            out / "investor_wiki_evidence.v1.json",
            build_evidence(events, generated_at=collected_at, collection_audit=collection_audit),
        )
        (out / "SUMMARY.md").write_text(
            "\n".join(
                [
                    "# 港美股券商采集包",
                    "",
                    f"- collector：`{COLLECTOR}`",
                    f"- 事件数：{len(events)}",
                    f"- readiness：`{manifest['collection_readiness']['status']}`",
                    f"- observed_brokers：`{', '.join(manifest['broker_coverage']['observed_brokers']) or 'none'}`",
                    f"- missing_expected_brokers：`{', '.join(manifest['broker_coverage']['missing_expected_brokers']) or 'none'}`",
                    f"- observed_trade_surfaces：`{', '.join(manifest['trade_surface_coverage']['observed_subtypes']) or 'none'}`",
                    f"- missing_trade_surfaces：`{', '.join(manifest['trade_surface_coverage']['missing_expected_subtypes']) or 'none'}`",
                    f"- asset_currencies：`{', '.join(manifest['asset_value_summary']['currencies_observed']) or 'none'}`",
                    f"- cashflow_events：{manifest['cashflow_activity_summary']['cashflow_event_count']}, "
                    f"dividend_events：{manifest['cashflow_activity_summary']['dividend_event_count']}, "
                    f"fx_events：{manifest['cashflow_activity_summary']['fx_event_count']}",
                    f"- order_statuses：`{', '.join(manifest['order_execution_summary']['status_counts'].keys()) or 'none'}`",
                    f"- scope_policy_enabled：{manifest['source_audit']['brokerage_scope_policy'].get('enabled', False)}",
                    f"- scope_policy_filtered：{manifest['source_audit'].get('scope_policy_filtered_record_count', 0)} / "
                    f"{manifest['source_audit'].get('candidate_record_count', manifest['source_audit'].get('parsed_record_count', 0))}",
                    f"- brokerage_boundary_proof：`{manifest['brokerage_boundary_proof']['proof_level']}`",
                    f"- complete_boundary_claimed：`{manifest['brokerage_boundary_proof']['false_claims']['complete_hk_us_trade_boundary_claimed']}`",
                    f"- archive_member_events：{manifest['source_audit']['archive_member_event_count']}",
                    f"- skipped_archive_members：{manifest['source_audit'].get('skipped_archive_member_count', 0)}",
                    f"- source_section_events：{manifest['source_audit']['source_section_event_count']}",
                    "- 边界：只读资产、持仓、成交、委托、资金流水；不下单、不撤单。",
                ]
            ),
            encoding="utf-8",
        )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    print(json.dumps({"event_count": len(events), "collector": COLLECTOR}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized Futu/Tiger/IBKR read-only brokerage exports.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Parse HK/US brokerage read-only exports or ZIP packages.")
    p.add_argument("--input", action="append", help="Authorized file, folder, or ZIP package. Repeat for multiple inputs.")
    p.add_argument("--out-dir")
    p.add_argument("--event-export")
    p.add_argument("--limit", type=int)
    p.add_argument("--collected-at")
    p.add_argument("--allow-broker", action="append", help="Only collect matching brokers, e.g. futu, tiger, ibkr.")
    p.add_argument("--deny-broker", action="append", help="Exclude matching brokers.")
    p.add_argument("--allow-account", action="append", help="Only collect matching account IDs.")
    p.add_argument("--deny-account", action="append", help="Exclude matching account IDs.")
    p.add_argument("--allow-subtype", action="append", help="Only collect matching strong-trade subtypes, e.g. asset_snapshot, position, execution, order, cashflow, dividend, fx.")
    p.add_argument("--deny-subtype", action="append", help="Exclude matching strong-trade subtypes.")
    p.add_argument("--allow-symbol", action="append", help="Only collect matching symbols.")
    p.add_argument("--deny-symbol", action="append", help="Exclude matching symbols.")
    p.add_argument("--allow-market", action="append", help="Only collect matching markets, e.g. HK or US.")
    p.add_argument("--deny-market", action="append", help="Exclude matching markets.")
    p.add_argument("--allow-currency", action="append", help="Only collect records with matching currencies.")
    p.add_argument("--deny-currency", action="append", help="Exclude records with matching currencies.")
    p.add_argument("--allow-keyword", action="append", help="Only collect records whose broker/account/symbol/name/status/source fields contain a keyword.")
    p.add_argument("--deny-keyword", action="append", help="Exclude records whose broker/account/symbol/name/status/source fields contain a keyword.")
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
