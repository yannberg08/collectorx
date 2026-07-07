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
    collect_from_inputs,
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
    events = collect_from_inputs(args.input or [], collected_at=collected_at, limit=args.limit)
    if args.out_dir:
        out = Path(args.out_dir).expanduser()
        write_jsonl(out / "lake" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at)
        write_json(out / "manifest.json", manifest)
        write_json(out / "investor_wiki_evidence.v1.json", build_evidence(events, generated_at=collected_at))
        (out / "SUMMARY.md").write_text(
            "\n".join(
                [
                    "# 专业终端使用痕迹采集包",
                    "",
                    f"- collector：`{COLLECTOR}`",
                    f"- 事件数：{len(events)}",
                    f"- readiness：`{manifest['collection_readiness']['status']}`",
                    f"- observed_terminals：`{', '.join(manifest['terminal_coverage']['observed_terminals']) or 'none'}`",
                    f"- missing_expected_terminals：`{', '.join(manifest['terminal_coverage']['missing_expected_terminals']) or 'none'}`",
                    f"- observed_activities：`{', '.join(manifest['activity_coverage']['observed_activities']) or 'none'}`",
                    f"- missing_activities：`{', '.join(manifest['activity_coverage']['missing_expected_activities']) or 'none'}`",
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
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
