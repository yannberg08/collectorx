#!/usr/bin/env python3
"""CLI for generic calendar collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from calendar_collector.parser import build_manifest, collect_from_inputs_with_audit, now_iso


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_summary(path: Path, manifest: dict) -> None:
    lines = [
        "# Calendar Collector Package",
        "",
        "- collector: `calendar`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- observed_platforms: `{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
        f"- missing_expected_platforms: `{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- meeting_url_events: {manifest['time_surface_summary']['events_with_meeting_url']}",
        f"- reminder_events: {manifest['time_surface_summary']['events_with_reminders']}",
        f"- duration_events: {manifest['time_surface_summary']['events_with_duration_minutes']}",
        f"- invalid_time_ranges: {manifest['time_surface_summary']['events_with_invalid_time_range']}",
        f"- conflict_pairs: {manifest['time_surface_summary']['time_conflict_summary']['conflict_pair_count']}",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
        "",
        "Generic calendar events are not written to the investor Wiki directly. Use the task-calendar-investor lens.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events, collection_audit = collect_from_inputs_with_audit(
        args.input or [],
        collected_at=collected_at,
        limit=args.limit,
        allow_source_platforms=args.allow_source_platform,
        deny_source_platforms=args.deny_source_platform,
        allow_calendars=args.allow_calendar,
        deny_calendars=args.deny_calendar,
        allow_attendees=args.allow_attendee,
        deny_attendees=args.deny_attendee,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if out_dir:
        write_jsonl(out_dir / "lake" / "calendar" / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
        write_json(out_dir / "manifest.json", manifest)
        write_summary(out_dir / "SUMMARY.md", manifest)
    print(json.dumps({"collector": "calendar", "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized calendar exports into CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse ICS/JSON/CSV/TSV/ZIP calendar exports.")
    p_collect.add_argument("--input", action="append", help="Authorized calendar export file/folder.")
    p_collect.add_argument("--out-dir", help="Output package directory.")
    p_collect.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    add_calendar_scope_policy_args(p_collect)
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


def add_calendar_scope_policy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-source-platform", action="append", help="Only keep events from this source platform. Repeat or comma-separate.")
    parser.add_argument("--deny-source-platform", action="append", help="Drop events from this source platform. Repeat or comma-separate.")
    parser.add_argument("--allow-calendar", action="append", help="Only keep events whose calendar name/path contains this text. Repeat or comma-separate.")
    parser.add_argument("--deny-calendar", action="append", help="Drop events whose calendar name/path contains this text. Repeat or comma-separate.")
    parser.add_argument("--allow-attendee", action="append", help="Only keep events whose organizer/attendee contains this text. Repeat or comma-separate.")
    parser.add_argument("--deny-attendee", action="append", help="Drop events whose organizer/attendee contains this text. Repeat or comma-separate.")
    parser.add_argument("--allow-keyword", action="append", help="Only keep events whose title/description/location contains this text. Repeat or comma-separate.")
    parser.add_argument("--deny-keyword", action="append", help="Drop events whose title/description/location contains this text. Repeat or comma-separate.")


if __name__ == "__main__":
    raise SystemExit(main())
