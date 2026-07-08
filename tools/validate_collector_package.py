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

from collectorx.investor_wiki import validate_evidence_file


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


def load_json(path: Path) -> tuple[Any | None, list[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [f"{path}: invalid JSON: {exc}"]
    except OSError as exc:
        return None, [f"{path}: cannot read file: {exc}"]


def find_event_files(package_dir: Path, collector: str | None) -> tuple[list[Path], list[str]]:
    lake = package_dir / "lake"
    if collector:
        event_file = lake / collector / "events.jsonl"
        return ([event_file] if event_file.exists() else []), ([] if event_file.exists() else [f"missing event file: {event_file}"])
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


def validate_events(path: Path, *, expected_collector: str | None) -> tuple[int, list[str]]:
    errors: list[str] = []
    count = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                count += 1
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{line_no}: invalid JSONL event: {exc}")
                    continue
                errors.extend(validate_event(event, path=path, line_no=line_no, expected_collector=expected_collector))
    except OSError as exc:
        return 0, [f"{path}: cannot read events: {exc}"]
    if count == 0:
        errors.append(f"{path}: events.jsonl must contain at least one event")
    return count, errors


def validate_manifest(package_dir: Path, collector: str | None) -> tuple[str | None, list[str]]:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        return collector, [f"missing manifest: {manifest_path}"]

    manifest, errors = load_json(manifest_path)
    if errors:
        return collector, errors
    if not isinstance(manifest, dict):
        return collector, [f"{manifest_path}: manifest must be a JSON object"]

    manifest_collector = manifest.get("collector")
    expected_collector = collector or (manifest_collector if isinstance(manifest_collector, str) else None)
    if collector and manifest_collector not in (None, collector):
        return expected_collector, [f"{manifest_path}: collector {manifest_collector!r} does not match {collector!r}"]
    if "event_count" in manifest and not isinstance(manifest.get("event_count"), int):
        return expected_collector, [f"{manifest_path}: event_count must be an integer when present"]
    return expected_collector, []


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

    expected_collector, manifest_errors = validate_manifest(package_dir, collector)
    errors.extend(manifest_errors)

    event_files, event_file_errors = find_event_files(package_dir, collector or expected_collector)
    errors.extend(event_file_errors)

    event_count = 0
    for path in event_files:
        collector_from_path = path.parent.name
        count, event_errors = validate_events(path, expected_collector=collector or expected_collector or collector_from_path)
        event_count += count
        errors.extend(event_errors)

    evidence_path = package_dir / "investor_wiki_evidence.v1.json"
    evidence_present = evidence_path.exists()
    if require_evidence and not evidence_present:
        errors.append(f"missing required evidence package: {evidence_path}")
    if evidence_present:
        evidence_errors = validate_evidence_file(evidence_path, require_dimensions=not allow_route_only)
        errors.extend(f"{evidence_path}: {error}" for error in evidence_errors)

    summary = {
        "package_dir": str(package_dir),
        "collector": collector or expected_collector,
        "event_file_count": len(event_files),
        "event_count": event_count,
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
