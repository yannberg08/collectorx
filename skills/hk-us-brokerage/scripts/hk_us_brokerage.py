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
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
