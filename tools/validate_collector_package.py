#!/usr/bin/env python3
"""Validate a CollectorX package directory for FinClaw ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectorx.investor_wiki import validate_evidence_contract


EVENT_REQUIRED_KEYS = {
    "schema",
    "id",
    "collector",
    "source",
    "owner_scope",
    "kind",
    "time",
    "collected_at",
    "data",
    "raw_ref",
    "privacy",
}

DATA_QUALITY_GAP_TARGET = "collectorx.data_quality.collection_gaps"

DEDICATED_USABLE_COUNT_KEYS = {
    "activity_event_count",
    "asset_event_count",
    "brokerage_event_count",
    "calendar_event_count",
    "collaboration_event_count",
    "email_event_count",
    "email_research_event_count",
    "favorite_event_count",
    "feishu_event_count",
    "file_event_count",
    "filesystem_event_count",
    "meeting_artifact_event_count",
    "note_event_count",
    "research_document_event_count",
    "social_activity_event_count",
    "social_influence_event_count",
    "strong_trade_event_count",
    "task_event_count",
    "usage_event_count",
    "wechat_favorite_event_count",
    "watchlist_event_count",
    "workflow_event_count",
}

PRIMARY_USABLE_COUNT_KEY_BY_COLLECTOR = {
    "china-wealth-assets": "asset_event_count",
    "collaboration-exports": "collaboration_event_count",
    "email-research": "email_research_event_count",
    "feishu": "feishu_event_count",
    "filesystem": "filesystem_event_count",
    "financial-news-usage": "usage_event_count",
    "hk-us-brokerage": "brokerage_event_count",
    "meeting-artifacts": "meeting_artifact_event_count",
    "pro-terminal-usage": "workflow_event_count",
    "research-documents": "research_document_event_count",
    "social-activity": "social_activity_event_count",
    "social-investment-influence": "social_influence_event_count",
    "ths-watchlist": "watchlist_event_count",
    "wechat-favorites": "wechat_favorite_event_count",
    "xueqiu-investor-activity": "activity_event_count",
    "xueqiu-watchlist": "watchlist_event_count",
}


def load_json(path: Path) -> tuple[Any | None, list[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [f"{path}: invalid JSON: {exc}"]
    except OSError as exc:
        return None, [f"{path}: cannot read file: {exc}"]


def is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def declared_count(container: dict[str, Any], label: str, key: str, errors: list[str]) -> int | None:
    if key not in container:
        return None
    value = container.get(key)
    if not is_non_negative_int(value):
        errors.append(f"{label}.{key} must be a non-negative integer")
        return None
    return int(value)


def event_is_gap(event: dict[str, Any]) -> bool:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    privacy = event.get("privacy") if isinstance(event.get("privacy"), dict) else {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    markers = {
        data.get("subtype"),
        data.get("activity_type"),
        data.get("action_type"),
        data.get("signal_type"),
        payload.get("subtype"),
        payload.get("activity_type"),
        payload.get("action_type"),
        payload.get("signal_type"),
    }
    if any(str(marker) in {"collector_gap", "collector_preflight_gap"} for marker in markers):
        return True
    profile_type = str(data.get("profile_type") or "")
    if profile_type.endswith("collection_gap"):
        return True
    gap_reason = data.get("gap")
    if gap_reason not in (None, "", False):
        return True
    payload_gap = payload.get("gap")
    if payload_gap not in (None, "", False):
        return True
    contains = privacy.get("contains") if isinstance(privacy.get("contains"), list) else []
    return "collection_gap" in {str(item) for item in contains}


def event_targets(event: dict[str, Any]) -> list[str]:
    targets = event.get("wiki_targets")
    if not isinstance(targets, list):
        return []
    return [str(target) for target in targets]


def event_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    gap_events = [event for event in events if event_is_gap(event)]
    return {
        "event_count": len(events),
        "usable_event_count": len(events) - len(gap_events),
        "gap_event_count": len(gap_events),
        "gap_only": bool(events) and len(gap_events) == len(events),
    }


def find_event_files(package_dir: Path, collector: str | None) -> tuple[list[Path], list[str]]:
    lake = package_dir / "lake"
    if collector:
        event_files = [
            path
            for path in (
                lake / collector / "events.jsonl",
                lake / "data_quality" / "events.jsonl",
            )
            if path.exists()
        ]
        if event_files:
            return event_files, []
        return [], [f"missing event file: {lake / collector / 'events.jsonl'}"]
    if not lake.exists():
        return [], [f"missing lake directory: {lake}"]
    event_files = sorted(path for path in lake.glob("*/events.jsonl") if path.is_file())
    if not event_files:
        return [], [f"no lake/*/events.jsonl files found under {lake}"]
    return event_files, []


def validate_event(event: Any, *, path: Path, line_no: int, expected_collector: str | None) -> list[str]:
    prefix = f"{path}:{line_no}"
    if not isinstance(event, dict):
        return [f"{prefix}: event must be a JSON object"]

    errors: list[str] = []
    missing = EVENT_REQUIRED_KEYS.difference(event)
    if missing:
        errors.append(f"{prefix}: missing required keys: {sorted(missing)}")
        return errors

    if event.get("schema") != "collectorx.event.v1":
        errors.append(f"{prefix}: invalid schema: {event.get('schema')!r}")
    if expected_collector and event.get("collector") != expected_collector:
        errors.append(f"{prefix}: collector {event.get('collector')!r} does not match {expected_collector!r}")

    for key in ("id", "collector", "source", "owner_scope", "kind", "time", "collected_at"):
        if not isinstance(event.get(key), str) or not event.get(key):
            errors.append(f"{prefix}: {key} must be a non-empty string")
    if not isinstance(event.get("data"), dict):
        errors.append(f"{prefix}: data must be an object")
    if not isinstance(event.get("raw_ref"), dict):
        errors.append(f"{prefix}: raw_ref must be an object")

    privacy = event.get("privacy")
    if not isinstance(privacy, dict):
        errors.append(f"{prefix}: privacy must be an object")
    else:
        for key in ("sensitive", "local_only"):
            if not isinstance(privacy.get(key), bool):
                errors.append(f"{prefix}: privacy.{key} must be boolean")
    return errors


def validate_events(path: Path, *, expected_collector: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    events: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{line_no}: invalid JSONL event: {exc}")
                    continue
                errors.extend(validate_event(event, path=path, line_no=line_no, expected_collector=expected_collector))
                if isinstance(event, dict):
                    events.append(event)
    except OSError as exc:
        return [], [f"{path}: cannot read events: {exc}"]
    if not events:
        errors.append(f"{path}: events.jsonl must contain at least one event")
    return events, errors


def validate_manifest(package_dir: Path, collector: str | None) -> tuple[str | None, dict[str, Any] | None, list[str]]:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        return collector, None, [f"missing manifest: {manifest_path}"]

    manifest, errors = load_json(manifest_path)
    if errors:
        return collector, None, errors
    if not isinstance(manifest, dict):
        return collector, None, [f"{manifest_path}: manifest must be a JSON object"]

    manifest_collector = manifest.get("collector")
    expected_collector = collector or (manifest_collector if isinstance(manifest_collector, str) else None)
    if collector and manifest_collector not in (None, collector):
        return expected_collector, manifest, [f"{manifest_path}: collector {manifest_collector!r} does not match {collector!r}"]
    if "event_count" in manifest and not is_non_negative_int(manifest.get("event_count")):
        return expected_collector, manifest, [f"{manifest_path}: event_count must be a non-negative integer when present"]
    return expected_collector, manifest, []


def validate_manifest_semantics(
    manifest: dict[str, Any],
    *,
    collector: str | None,
    stats: dict[str, Any],
    manifest_path: Path,
) -> list[str]:
    errors: list[str] = []
    label = str(manifest_path)
    validate_declared_counts(manifest, label=label, collector=collector, stats=stats, errors=errors)

    readiness = manifest.get("collection_readiness")
    if readiness is None:
        return errors
    if not isinstance(readiness, dict):
        errors.append(f"{label}.collection_readiness must be an object when present")
        return errors

    readiness_label = f"{label}.collection_readiness"
    validate_declared_counts(readiness, label=readiness_label, collector=collector, stats=stats, errors=errors)
    validate_readiness_gates(readiness, label=readiness_label, collector=collector, stats=stats, errors=errors)
    return errors


def validate_declared_counts(
    container: dict[str, Any],
    *,
    label: str,
    collector: str | None,
    stats: dict[str, Any],
    errors: list[str],
) -> None:
    declared_event_count = declared_count(container, label, "event_count", errors)
    if declared_event_count is not None and declared_event_count != stats["event_count"]:
        errors.append(
            f"{label}.event_count {declared_event_count} does not match events.jsonl count {stats['event_count']}"
        )

    declared_usable_count = declared_count(container, label, "usable_event_count", errors)
    if declared_usable_count is not None and declared_usable_count != stats["usable_event_count"]:
        errors.append(
            f"{label}.usable_event_count {declared_usable_count} does not match non-gap event count {stats['usable_event_count']}"
        )

    declared_gap_count = declared_count(container, label, "gap_event_count", errors)
    if declared_gap_count is not None and declared_gap_count != stats["gap_event_count"]:
        errors.append(
            f"{label}.gap_event_count {declared_gap_count} does not match gap event count {stats['gap_event_count']}"
        )

    for key in sorted(DEDICATED_USABLE_COUNT_KEYS):
        declared = declared_count(container, label, key, errors)
        if declared is None:
            continue
        if declared > stats["usable_event_count"]:
            errors.append(
                f"{label}.{key} {declared} cannot exceed usable_event_count {stats['usable_event_count']}"
            )

    primary_key = PRIMARY_USABLE_COUNT_KEY_BY_COLLECTOR.get(str(collector or ""))
    if primary_key and primary_key in container:
        declared = declared_count(container, label, primary_key, errors)
        if declared is not None and declared != stats["usable_event_count"]:
            errors.append(
                f"{label}.{primary_key} {declared} must match non-gap event count {stats['usable_event_count']}"
            )


def validate_readiness_gates(
    readiness: dict[str, Any],
    *,
    label: str,
    collector: str | None,
    stats: dict[str, Any],
    errors: list[str],
) -> None:
    for key, value in readiness.items():
        if key.startswith("can_") and not isinstance(value, bool):
            errors.append(f"{label}.{key} must be boolean")

    gap_count = int(stats["gap_event_count"])
    if "can_enter_data_quality_lake" in readiness:
        expected = gap_count > 0
        observed = readiness.get("can_enter_data_quality_lake")
        if observed is not expected:
            errors.append(f"{label}.can_enter_data_quality_lake must be {expected} when gap_event_count is {gap_count}")

    if stats["gap_only"]:
        for key, value in readiness.items():
            if key in {"can_enter_data_quality_lake", "can_enter_finclaw_lake"}:
                continue
            if key.startswith("can_enter_") and key.endswith("_lake") and value is not False:
                errors.append(f"{label}.{key} must be false for a gap-only package")
        for key in (
            "can_enter_finclaw",
            "can_enter_investor_wiki",
            "can_enter_investor_wiki_directly",
            "can_feed_investor_wiki_directly",
            "can_feed_investor_wiki_evidence",
        ):
            if key in readiness and readiness.get(key) is not False:
                errors.append(f"{label}.{key} must be false for a gap-only package")

    if collector == "social-activity":
        if readiness.get("can_feed_investor_wiki_directly") is not False:
            errors.append(f"{label}.can_feed_investor_wiki_directly must be false for social-activity")
        if stats["gap_only"] and readiness.get("can_feed_social_investment_lens") is not False:
            errors.append(f"{label}.can_feed_social_investment_lens must be false for a gap-only social-activity package")


def validate_event_routing(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for event in events:
        event_id = str(event.get("id") or "<unknown>")
        targets = event_targets(event)
        if event_is_gap(event):
            if targets != [DATA_QUALITY_GAP_TARGET]:
                errors.append(
                    f"gap event {event_id} must route only to {DATA_QUALITY_GAP_TARGET}; got {targets or '<missing>'}"
                )
        elif DATA_QUALITY_GAP_TARGET in targets:
            errors.append(f"non-gap event {event_id} must not route to {DATA_QUALITY_GAP_TARGET}")
    return errors


def validate_evidence_semantics(evidence: dict[str, Any], *, stats: dict[str, Any], evidence_path: Path) -> list[str]:
    errors: list[str] = []
    label = str(evidence_path)
    generated_from = evidence.get("generated_from")
    if isinstance(generated_from, dict):
        declared = declared_count(generated_from, f"{label}.generated_from", "event_count", errors)
        if declared is not None and declared != stats["usable_event_count"]:
            errors.append(
                f"{label}.generated_from.event_count {declared} does not match non-gap event count {stats['usable_event_count']}"
            )
        raw_count = declared_count(generated_from, f"{label}.generated_from", "raw_event_count", errors)
        if raw_count is not None and raw_count != stats["event_count"]:
            errors.append(
                f"{label}.generated_from.raw_event_count {raw_count} does not match events.jsonl count {stats['event_count']}"
            )
        gap_count = declared_count(generated_from, f"{label}.generated_from", "gap_event_count", errors)
        if gap_count is not None and gap_count != stats["gap_event_count"]:
            errors.append(
                f"{label}.generated_from.gap_event_count {gap_count} does not match gap event count {stats['gap_event_count']}"
            )

    coverage_summary = evidence.get("coverage_summary")
    if isinstance(coverage_summary, dict):
        route_counts = coverage_summary.get("route_counts")
        if isinstance(route_counts, dict) and int(route_counts.get(DATA_QUALITY_GAP_TARGET) or 0) > 0:
            errors.append(f"{label}.coverage_summary.route_counts must not include data-quality gap routes as Wiki facts")
        usable_for_wiki_now = coverage_summary.get("usable_for_wiki_now")
        if stats["usable_event_count"] == 0 and isinstance(usable_for_wiki_now, list) and usable_for_wiki_now:
            errors.append(f"{label}.coverage_summary.usable_for_wiki_now must be empty when there are no non-gap events")

    for child_label, child in iter_evidence_children(evidence):
        targets = child.get("route_targets")
        if isinstance(targets, list) and DATA_QUALITY_GAP_TARGET in {str(target) for target in targets}:
            errors.append(f"{label}.{child_label}.route_targets must not include {DATA_QUALITY_GAP_TARGET}")
        evidence_count = child.get("evidence_count")
        if stats["usable_event_count"] == 0 and isinstance(evidence_count, int) and evidence_count > 0:
            errors.append(f"{label}.{child_label}.evidence_count must be 0 when there are no non-gap events")
        support_level = child.get("support_level")
        if stats["usable_event_count"] == 0 and support_level in {"strong", "medium", "weak"}:
            errors.append(f"{label}.{child_label}.support_level must be none when there are no non-gap events")
    return errors


def iter_evidence_children(evidence: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    children: list[tuple[str, dict[str, Any]]] = []
    dimensions = evidence.get("dimensions")
    if not isinstance(dimensions, list):
        return children
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue
        dimension_id = str(dimension.get("dimension_id") or "<unknown>")
        for child in dimension.get("children") or []:
            if isinstance(child, dict):
                child_id = str(child.get("subdimension_id") or "<unknown>")
                children.append((f"{dimension_id}.{child_id}", child))
    return children


def validate_package(
    package_dir: Path,
    *,
    collector: str | None = None,
    require_evidence: bool = False,
    allow_route_only: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not package_dir.exists() or not package_dir.is_dir():
        return {"package_dir": str(package_dir)}, [f"package directory does not exist: {package_dir}"]

    expected_collector, manifest, manifest_errors = validate_manifest(package_dir, collector)
    errors.extend(manifest_errors)

    event_files, event_file_errors = find_event_files(package_dir, collector or expected_collector)
    errors.extend(event_file_errors)

    events: list[dict[str, Any]] = []
    for path in event_files:
        collector_from_path = path.parent.name
        loaded_events, event_errors = validate_events(path, expected_collector=collector or expected_collector or collector_from_path)
        events.extend(loaded_events)
        errors.extend(event_errors)

    stats = event_stats(events)
    errors.extend(validate_event_routing(events))
    if isinstance(manifest, dict):
        errors.extend(
            validate_manifest_semantics(
                manifest,
                collector=collector or expected_collector,
                stats=stats,
                manifest_path=package_dir / "manifest.json",
            )
        )

    evidence_path = package_dir / "investor_wiki_evidence.v1.json"
    evidence_present = evidence_path.exists()
    if require_evidence and not evidence_present:
        errors.append(f"missing required evidence package: {evidence_path}")
    if evidence_present:
        evidence, evidence_load_errors = load_json(evidence_path)
        errors.extend(evidence_load_errors)
        if isinstance(evidence, dict):
            evidence_errors = validate_evidence_contract(evidence, require_dimensions=not allow_route_only)
            errors.extend(f"{evidence_path}: {error}" for error in evidence_errors)
            errors.extend(validate_evidence_semantics(evidence, stats=stats, evidence_path=evidence_path))
        elif not evidence_load_errors:
            errors.append(f"{evidence_path}: evidence must be a JSON object")

    summary = {
        "package_dir": str(package_dir),
        "collector": collector or expected_collector,
        "event_file_count": len(event_files),
        "event_count": stats["event_count"],
        "usable_event_count": stats["usable_event_count"],
        "gap_event_count": stats["gap_event_count"],
        "gap_only": stats["gap_only"],
        "manifest_present": (package_dir / "manifest.json").exists(),
        "evidence_present": evidence_present,
        "valid": not errors,
    }
    return summary, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a CollectorX package directory for FinClaw ingestion.")
    parser.add_argument("package_dir", help="CollectorX package output directory.")
    parser.add_argument("--collector", help="Expected collector id, e.g. eastmoney-portfolio.")
    parser.add_argument("--require-evidence", action="store_true", help="Require investor_wiki_evidence.v1.json.")
    parser.add_argument("--allow-route-only", action="store_true", help="Allow legacy route-only evidence packages.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable validation summary.")
    args = parser.parse_args()

    summary, errors = validate_package(
        Path(args.package_dir),
        collector=args.collector,
        require_evidence=args.require_evidence,
        allow_route_only=args.allow_route_only,
    )
    if args.json:
        print(json.dumps({**summary, "errors": errors}, ensure_ascii=False, indent=2, sort_keys=True))
    elif errors:
        print("CollectorX package validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print("CollectorX package validation passed.")
        print(f"collector: {summary.get('collector') or '<unknown>'}")
        print(f"events: {summary['event_count']} across {summary['event_file_count']} file(s)")
        print(f"evidence: {'present' if summary['evidence_present'] else 'absent'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
