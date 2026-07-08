#!/usr/bin/env python3
"""Run or dry-run a FinClaw CollectorX batch manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.finclaw_catalog import (
    build_batch_manifest,
    build_runbook_for_options,
    filtered_entries,
    parse_set_values,
)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid batch manifest JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"Cannot read batch manifest: {path}: {exc}") from exc
    if manifest.get("schema") != "collectorx.finclaw_batch_manifest.v1":
        raise SystemExit(f"Unsupported batch manifest schema: {manifest.get('schema')!r}")
    return manifest


def build_manifest_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.manifest:
        return load_manifest(Path(args.manifest))
    replacements = parse_set_values(args.set_values or [])
    runbook = build_runbook_for_options(
        filtered_entries(args),
        replacements=replacements,
        out_dir_root=args.out_dir_root,
        auto_link_upstream=args.auto_link_upstream,
    )
    return build_batch_manifest(runbook)


def run_argv(argv: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), text=True, capture_output=True, check=False)
    except OSError as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "status": "success" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def validation_result(step: dict[str, Any], *, execute: bool, skip_validation: bool) -> dict[str, Any]:
    validation = step.get("post_run_validation") or {}
    argv = validation.get("argv") or []
    result = {
        "ready": bool(validation.get("ready")),
        "required_evidence": bool(validation.get("require_evidence")),
        "argv": argv,
    }
    if skip_validation:
        return {**result, "status": "skipped"}
    if not validation.get("ready") or not argv:
        return {**result, "status": "not_ready"}
    if not execute:
        return {**result, "status": "planned"}
    run = run_argv(argv)
    return {**result, **run}


def dry_run_step(step: dict[str, Any], *, skip_validation: bool) -> dict[str, Any]:
    return {
        "id": step["id"],
        "stage": step["stage"],
        "status": "dry_run",
        "argv": step["argv"],
        "depends_on": step.get("depends_on", []),
        "output_dir": step.get("output_dir"),
        "lake_events_jsonl": step.get("lake_events_jsonl"),
        "input_events_jsonl": step.get("input_events_jsonl"),
        "post_run_validation": validation_result(step, execute=False, skip_validation=skip_validation),
    }


def execute_step(step: dict[str, Any], *, skip_validation: bool) -> dict[str, Any]:
    run = run_argv(step["argv"])
    result = {
        "id": step["id"],
        "stage": step["stage"],
        "status": run["status"],
        "argv": step["argv"],
        "depends_on": step.get("depends_on", []),
        "output_dir": step.get("output_dir"),
        "lake_events_jsonl": step.get("lake_events_jsonl"),
        "input_events_jsonl": step.get("input_events_jsonl"),
        "exit_code": run["exit_code"],
        "duration_seconds": run["duration_seconds"],
        "stdout": run["stdout"],
        "stderr": run["stderr"],
        "post_run_validation": {"status": "skipped_after_failed_step"},
    }
    if run["status"] == "success":
        validation = validation_result(step, execute=True, skip_validation=skip_validation)
        result["post_run_validation"] = validation
        if validation["status"] not in {"success", "skipped"}:
            result["status"] = f"validation_{validation['status']}"
    return result


def run_batch(
    manifest: dict[str, Any],
    *,
    execute: bool,
    skip_validation: bool,
    continue_on_error: bool,
) -> tuple[dict[str, Any], int]:
    steps: list[dict[str, Any]] = []
    failed = 0
    attempted = 0

    for step in manifest.get("ready_steps", []):
        if execute:
            attempted += 1
            result = execute_step(step, skip_validation=skip_validation)
            if result["status"] != "success":
                failed += 1
                steps.append(result)
                if not continue_on_error:
                    break
            else:
                steps.append(result)
        else:
            steps.append(dry_run_step(step, skip_validation=skip_validation))

    skipped_ready = max(0, len(manifest.get("ready_steps", [])) - len(steps))
    succeeded = sum(
        1
        for step in steps
        if step["status"] == "success" and step["post_run_validation"]["status"] in {"success", "skipped"}
    )
    report = {
        "schema": "collectorx.finclaw_batch_run_report.v1",
        "mode": "execute" if execute else "dry_run",
        "manifest_schema": manifest.get("schema"),
        "summary": {
            "ready_steps": len(manifest.get("ready_steps", [])),
            "blocked_steps": len(manifest.get("blocked_steps", [])),
            "attempted_steps": attempted,
            "succeeded_steps": succeeded,
            "failed_steps": failed,
            "skipped_ready_steps": skipped_ready,
        },
        "steps": steps,
        "blocked_steps": manifest.get("blocked_steps", []),
    }
    return report, 1 if failed else 0


def print_human_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"mode: {report['mode']}")
    print(f"ready_steps: {summary['ready_steps']}")
    print(f"blocked_steps: {summary['blocked_steps']}")
    print(f"attempted_steps: {summary['attempted_steps']}")
    print(f"succeeded_steps: {summary['succeeded_steps']}")
    print(f"failed_steps: {summary['failed_steps']}")
    for step in report["steps"]:
        print(f"- {step['id']}: {step['status']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or dry-run a FinClaw CollectorX batch manifest.")
    parser.add_argument("--manifest", help="Read an existing collectorx.finclaw_batch_manifest.v1 JSON file.")
    parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    parser.add_argument("--readiness")
    parser.add_argument(
        "--out-dir-root",
        help="Replace <out-dir> with <out-dir-root>/<collector-id> when building a manifest.",
    )
    parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        metavar="PLACEHOLDER=VALUE",
        help="Replace an arbitrary command placeholder when building a manifest.",
    )
    parser.add_argument(
        "--no-auto-link-upstream",
        dest="auto_link_upstream",
        action="store_false",
        default=True,
        help="Do not auto-fill <upstream-id-events-jsonl> placeholders when building a manifest.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute ready steps. The default is dry-run only.")
    parser.add_argument("--skip-validation", action="store_true", help="Do not run post-run package validation.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue executing after a failed step.")
    parser.add_argument("--require-all-ready", action="store_true", help="Exit with status 2 when blocked steps remain.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable run report.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    manifest = build_manifest_from_args(args)
    report, exit_code = run_batch(
        manifest,
        execute=args.execute,
        skip_validation=args.skip_validation,
        continue_on_error=args.continue_on_error,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_report(report)
    if args.require_all_ready and report["summary"]["blocked_steps"]:
        return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
