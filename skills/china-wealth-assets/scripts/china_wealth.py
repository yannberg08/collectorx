#!/usr/bin/env python3
"""CLI for China fund and wealth asset collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from china_wealth.parser import build_evidence, build_manifest, collect_from_inputs, now_iso


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
    events = collect_from_inputs(args.input or [], collected_at=collected_at, limit=args.limit)
    if args.out_dir:
        out = Path(args.out_dir).expanduser()
        write_jsonl(out / "lake" / "china-wealth-assets" / "events.jsonl", events)
        write_json(out / "manifest.json", build_manifest(events))
        write_json(out / "investor_wiki_evidence.v1.json", build_evidence(events, generated_at=collected_at))
        (out / "SUMMARY.md").write_text(
            "\n".join(
                [
                    "# 中国基金理财资产采集包",
                    "",
                    f"- 事件数：{len(events)}",
                    "- 用途：补齐券商账户之外的基金、理财和现金管理资产边界。",
                    "- 边界：不采支付密码、银行密码、消费流水。",
                ]
            ),
            encoding="utf-8",
        )
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    print(json.dumps({"event_count": len(events), "collector": "china-wealth-assets"}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized China fund and wealth assets.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Parse fund/wealth exports.")
    p.add_argument("--input", action="append", help="Authorized export file/folder.")
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
