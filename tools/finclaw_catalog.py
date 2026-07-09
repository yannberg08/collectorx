#!/usr/bin/env python3
"""Inspect FinClaw investor collector catalog and invocation contracts."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "collectors" / "finclaw-investor-catalog.json"
CONTRACTS_PATH = ROOT / "collectors" / "finclaw-invocation-contracts.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_catalog() -> dict[str, Any]:
    return load_json(CATALOG_PATH)


def load_contracts() -> dict[str, Any]:
    return load_json(CONTRACTS_PATH)


def merged_entries() -> list[dict[str, Any]]:
    catalog = load_catalog()
    contracts = {item["id"]: item for item in load_contracts().get("contracts", [])}
    merged: list[dict[str, Any]] = []
    for entry in catalog.get("entries", []):
        contract = contracts.get(entry["id"], {})
        merged.append({**entry, "invocation_contract": contract})
    return merged


def find_entry(collector_id: str) -> dict[str, Any]:
    for entry in merged_entries():
        if entry["id"] == collector_id:
            return entry
    raise SystemExit(f"Unknown FinClaw collector id: {collector_id}")


def summarize(entry: dict[str, Any]) -> dict[str, Any]:
    contract = entry.get("invocation_contract") or {}
    return {
        "id": entry["id"],
        "priority": entry["priority"],
        "category": entry["category"],
        "skill": entry["skill"],
        "readiness": entry["readiness"],
        "gate": entry["gate"],
        "product_surface": contract.get("product_surface"),
        "authorization_mode": contract.get("authorization_mode"),
        "evidence_role": contract.get("evidence_role"),
        "failure_state": contract.get("failure_state"),
        "requires_upstream": contract.get("requires_upstream", []),
    }


def print_human_list(entries: list[dict[str, Any]]) -> None:
    headers = ("id", "P", "category", "readiness", "auth", "surface", "failure")
    rows = [
        (
            entry["id"],
            entry["priority"],
            entry["category"],
            entry["readiness"],
            (entry.get("invocation_contract") or {}).get("authorization_mode", ""),
            (entry.get("invocation_contract") or {}).get("product_surface", ""),
            (entry.get("invocation_contract") or {}).get("failure_state", ""),
        )
        for entry in entries
    ]
    widths = [
        max(len(str(value)) for value in column)
        for column in zip(headers, *rows, strict=False)
    ]
    print("  ".join(str(value).ljust(width) for value, width in zip(headers, widths, strict=False)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths, strict=False)))


def parse_set_values(values: list[str]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--set must use placeholder=value format: {value}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--set placeholder cannot be empty: {value}")
        replacements[key] = raw
    return replacements


def plan_status(runner: str, placeholders: list[str], contract: dict[str, Any]) -> tuple[str, str | None]:
    if runner == "soulmirror":
        return "use_soulmirror_runner", "soulmirror_runner_required"
    upstream = contract.get("requires_upstream") or []
    if placeholders and contract.get("authorization_mode") == "lake-lens" and upstream:
        return "wait_for_upstream_lake", f"requires_upstream:{','.join(upstream)}"
    if placeholders:
        return "fill_placeholders", f"missing_placeholders:{','.join(placeholders)}"
    return "run_command", None


def value_after(argv: list[str], flags: set[str]) -> str | None:
    for index, token in enumerate(argv):
        if token in flags and index + 1 < len(argv):
            return argv[index + 1]
    return None


def build_package_validation(entry: dict[str, Any], argv: list[str], placeholders: list[str]) -> dict[str, Any]:
    package_dir = value_after(argv, {"--out-dir", "--output"})
    package_dir_ready = bool(package_dir) and "out-dir" not in placeholders and not re.search(r"<[^<>]+>", package_dir or "")
    require_evidence = entry["category"] in {"vertical", "lens"}
    validation_argv = [
        "python3",
        "tools/validate_collector_package.py",
        package_dir or "<out-dir>",
        "--collector",
        entry["id"],
    ]
    if require_evidence:
        validation_argv.append("--require-evidence")
    validation_argv.append("--json")
    return {
        "package_dir": package_dir,
        "ready": package_dir_ready,
        "require_evidence": require_evidence,
        "argv": validation_argv if package_dir_ready else [],
        "command": shlex.join(validation_argv) if package_dir_ready else None,
        "blocked_reason": None if package_dir_ready else "missing_output_directory",
    }


def build_plan(entry: dict[str, Any], *, replacements: dict[str, str]) -> dict[str, Any]:
    command = str(entry["cli"])
    for key, value in replacements.items():
        command = command.replace(f"<{key}>", shlex.quote(value))
    placeholders = sorted(set(re.findall(r"<([^<>]+)>", command)))
    argv = shlex.split(command)
    runner = "soulmirror" if command.startswith("SoulMirror") else "command"
    contract = entry.get("invocation_contract") or {}
    next_action, blocked_reason = plan_status(runner, placeholders, contract)
    package_validation = build_package_validation(entry, argv, placeholders)
    return {
        "id": entry["id"],
        "runner": runner,
        "command": command,
        "argv": argv,
        "ready_to_run": runner == "command" and not placeholders,
        "next_action": next_action,
        "blocked_reason": blocked_reason,
        "missing_placeholders": placeholders,
        "authorization_mode": contract.get("authorization_mode"),
        "product_surface": contract.get("product_surface"),
        "evidence_role": contract.get("evidence_role"),
        "user_step": contract.get("user_step"),
        "preflight": contract.get("preflight"),
        "failure_state": contract.get("failure_state"),
        "requires_upstream": contract.get("requires_upstream", []),
        "package_validation": package_validation,
    }


def cmd_list(args: argparse.Namespace) -> int:
    entries = merged_entries()
    if args.priority:
        entries = [entry for entry in entries if entry["priority"] == args.priority]
    if args.category:
        entries = [entry for entry in entries if entry["category"] == args.category]
    if args.readiness:
        entries = [entry for entry in entries if entry["readiness"] == args.readiness]
    if args.json:
        print(json.dumps([summarize(entry) for entry in entries], ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_list(entries)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    entry = find_entry(args.collector_id)
    if args.json:
        print(json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        contract = entry.get("invocation_contract") or {}
        print(f"id: {entry['id']}")
        print(f"priority/category: {entry['priority']} / {entry['category']}")
        print(f"readiness/gate: {entry['readiness']} / {entry['gate']}")
        print(f"skill: {entry['skill']}")
        print(f"authorization: {contract.get('authorization_mode')}")
        print(f"product surface: {contract.get('product_surface')}")
        print(f"evidence role: {contract.get('evidence_role')}")
        upstream = contract.get("requires_upstream") or []
        if upstream:
            print(f"requires upstream: {', '.join(upstream)}")
        print(f"user step: {contract.get('user_step')}")
        print(f"preflight: {contract.get('preflight')}")
        print(f"failure state: {contract.get('failure_state')}")
        print(f"cli: {entry['cli']}")
        print(f"collects: {entry['collects']}")
        print(f"must not collect: {entry['must_not_collect']}")
        print(f"production gap: {entry['production_gap']}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    entry = find_entry(args.collector_id)
    replacements = parse_set_values(args.set_values or [])
    if args.out_dir:
        replacements["out-dir"] = args.out_dir
    plan = build_plan(entry, replacements=replacements)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"id: {plan['id']}")
        print(f"runner: {plan['runner']}")
        print(f"ready_to_run: {str(plan['ready_to_run']).lower()}")
        print(f"next action: {plan['next_action']}")
        if plan["blocked_reason"]:
            print(f"blocked reason: {plan['blocked_reason']}")
        if plan["missing_placeholders"]:
            print(f"missing placeholders: {', '.join(plan['missing_placeholders'])}")
        print(f"user step: {plan['user_step']}")
        print(f"preflight: {plan['preflight']}")
        print(f"failure state: {plan['failure_state']}")
        print(f"command: {plan['command']}")
        package_validation = plan["package_validation"]
        print(f"package validation ready: {str(package_validation['ready']).lower()}")
        if package_validation["ready"]:
            print(f"package validation command: {package_validation['command']}")
    if args.require_ready and not plan["ready_to_run"]:
        return 2
    return 0


def filtered_entries(args: argparse.Namespace) -> list[dict[str, Any]]:
    entries = merged_entries()
    if args.priority:
        entries = [entry for entry in entries if entry["priority"] == args.priority]
    if args.category:
        entries = [entry for entry in entries if entry["category"] == args.category]
    if args.readiness:
        entries = [entry for entry in entries if entry["readiness"] == args.readiness]
    return entries


def doctor_item(entry: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "priority": entry["priority"],
        "category": entry["category"],
        "skill": entry["skill"],
        "readiness": entry["readiness"],
        "gate": entry["gate"],
        "product_surface": plan["product_surface"],
        "authorization_mode": plan["authorization_mode"],
        "evidence_role": plan["evidence_role"],
        "runner": plan["runner"],
        "ready_to_run": plan["ready_to_run"],
        "next_action": plan["next_action"],
        "blocked_reason": plan["blocked_reason"],
        "missing_placeholders": plan["missing_placeholders"],
        "requires_upstream": plan["requires_upstream"],
        "failure_state": plan["failure_state"],
        "user_step": plan["user_step"],
        "preflight": plan["preflight"],
        "command": plan["command"],
        "argv": plan["argv"],
        "package_validation": plan["package_validation"],
    }


def build_doctor_report(
    entries: list[dict[str, Any]], *, replacements: dict[str, str], out_dir_root: str | None
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for entry in entries:
        entry_replacements = dict(replacements)
        if out_dir_root:
            entry_replacements["out-dir"] = str(Path(out_dir_root) / entry["id"])
        plan = build_plan(entry, replacements=entry_replacements)
        items.append(doctor_item(entry, plan))

    by_next_action = Counter(item["next_action"] for item in items)
    by_runner = Counter(item["runner"] for item in items)
    by_priority = Counter(item["priority"] for item in items)
    by_category = Counter(item["category"] for item in items)
    ready_count = sum(1 for item in items if item["ready_to_run"])
    return {
        "schema": "collectorx.finclaw_catalog_doctor.v1",
        "total": len(items),
        "ready_to_run": ready_count,
        "not_ready": len(items) - ready_count,
        "summary": {
            "by_next_action": dict(sorted(by_next_action.items())),
            "by_runner": dict(sorted(by_runner.items())),
            "by_priority": dict(sorted(by_priority.items())),
            "by_category": dict(sorted(by_category.items())),
        },
        "items": items,
    }


def print_human_doctor(report: dict[str, Any]) -> None:
    print(f"total: {report['total']}")
    print(f"ready_to_run: {report['ready_to_run']}")
    print(f"not_ready: {report['not_ready']}")
    items = report["items"]
    if not items:
        print("No entries matched.")
        return

    headers = ("id", "P", "category", "ready", "next_action", "missing/upstream", "failure")
    rows = []
    for item in items:
        detail_values = item["missing_placeholders"] or item["requires_upstream"]
        rows.append(
            (
                item["id"],
                item["priority"],
                item["category"],
                str(item["ready_to_run"]).lower(),
                item["next_action"],
                ",".join(detail_values),
                item["failure_state"] or "",
            )
        )
    widths = [
        max(len(str(value)) for value in column)
        for column in zip(headers, *rows, strict=False)
    ]
    print("  ".join(str(value).ljust(width) for value, width in zip(headers, widths, strict=False)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths, strict=False)))


def cmd_doctor(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    replacements = parse_set_values(args.set_values or [])
    report = build_doctor_report(entries, replacements=replacements, out_dir_root=args.out_dir_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_doctor(report)
    if args.require_all_ready and report["not_ready"]:
        return 2
    return 0


RUNBOOK_STAGE_DEFINITIONS = [
    (
        "ready_collectors",
        "Run ordinary source collectors that do not require upstream Lake inputs.",
    ),
    (
        "ready_lenses",
        "Run investor lenses whose upstream Lake inputs have been supplied.",
    ),
    (
        "needs_upstream_lake",
        "Run or select upstream collectors before these lenses can execute.",
    ),
    (
        "needs_user_input",
        "Ask the user for authorized files, folders, accounts, or placeholders.",
    ),
    (
        "soulmirror_runner",
        "Hand these collectors to the SoulMirror-managed runner.",
    ),
]


def runbook_stage_name(item: dict[str, Any]) -> str:
    if item["next_action"] == "run_command" and item["requires_upstream"]:
        return "ready_lenses"
    if item["next_action"] == "run_command":
        return "ready_collectors"
    if item["next_action"] == "wait_for_upstream_lake":
        return "needs_upstream_lake"
    if item["next_action"] == "fill_placeholders":
        return "needs_user_input"
    if item["next_action"] == "use_soulmirror_runner":
        return "soulmirror_runner"
    return "needs_user_input"


def build_runbook(report: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in RUNBOOK_STAGE_DEFINITIONS}
    for item in report["items"]:
        grouped[runbook_stage_name(item)].append(item)

    stages = [
        {
            "name": name,
            "description": description,
            "count": len(grouped[name]),
            "items": grouped[name],
        }
        for name, description in RUNBOOK_STAGE_DEFINITIONS
    ]
    return {
        "schema": "collectorx.finclaw_runbook.v1",
        "doctor_schema": report["schema"],
        "auto_upstream_links": report.get("auto_upstream_links", []),
        "total": report["total"],
        "ready_to_run": report["ready_to_run"],
        "not_ready": report["not_ready"],
        "summary": {
            **report["summary"],
            "by_stage": {stage["name"]: stage["count"] for stage in stages},
        },
        "stages": stages,
    }


def build_runbook_for_options(
    entries: list[dict[str, Any]],
    *,
    replacements: dict[str, str],
    out_dir_root: str | None,
    auto_link_upstream: bool,
) -> dict[str, Any]:
    report = build_doctor_report(entries, replacements=replacements, out_dir_root=out_dir_root)
    if auto_link_upstream:
        auto_replacements, links = auto_upstream_replacements(report)
        if auto_replacements:
            merged_replacements = {**auto_replacements, **replacements}
            report = build_doctor_report(entries, replacements=merged_replacements, out_dir_root=out_dir_root)
        report["auto_upstream_links"] = links
    else:
        report["auto_upstream_links"] = []
    return build_runbook(report)


def build_upstream_lake_path(upstream_item: dict[str, Any]) -> str | None:
    package_validation = upstream_item.get("package_validation") or {}
    package_dir = package_validation.get("package_dir")
    if not package_validation.get("ready") or not package_dir:
        return None
    return str(Path(package_dir) / "lake" / upstream_item["id"] / "events.jsonl")


def auto_upstream_replacements(report: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    by_id = {item["id"]: item for item in report["items"]}
    replacements: dict[str, str] = {}
    links: list[dict[str, str]] = []
    for item in report["items"]:
        if item["next_action"] != "wait_for_upstream_lake":
            continue
        missing = set(item.get("missing_placeholders") or [])
        for upstream_id in item.get("requires_upstream") or []:
            upstream = by_id.get(upstream_id)
            if not upstream or not upstream.get("ready_to_run"):
                continue
            placeholder = f"{upstream_id}-events-jsonl"
            if placeholder not in missing:
                continue
            events_jsonl = build_upstream_lake_path(upstream)
            if not events_jsonl:
                continue
            replacements[placeholder] = events_jsonl
            links.append(
                {
                    "lens_id": item["id"],
                    "upstream_id": upstream_id,
                    "placeholder": placeholder,
                    "events_jsonl": events_jsonl,
                }
            )
    return replacements, links


def execution_step(item: dict[str, Any], *, stage_name: str, step_number: int) -> dict[str, Any]:
    package_validation = item["package_validation"]
    input_events_jsonl = value_after(item["argv"], {"--input"})
    step = {
        "step": step_number,
        "id": item["id"],
        "stage": stage_name,
        "priority": item["priority"],
        "category": item["category"],
        "runner": item["runner"],
        "argv": item["argv"],
        "display_command": item["command"],
        "depends_on": item["requires_upstream"],
        "output_dir": package_validation.get("package_dir"),
        "lake_events_jsonl": build_upstream_lake_path(item),
        "post_run_validation": {
            "ready": package_validation["ready"],
            "argv": package_validation["argv"],
            "command": package_validation["command"],
            "require_evidence": package_validation["require_evidence"],
        },
        "preflight": item["preflight"],
        "failure_state": item["failure_state"],
        "evidence_role": item["evidence_role"],
        "product_surface": item["product_surface"],
    }
    if input_events_jsonl and Path(input_events_jsonl).name == "events.jsonl":
        step["input_events_jsonl"] = input_events_jsonl
    return step


def blocked_step(item: dict[str, Any], *, stage_name: str) -> dict[str, Any]:
    return {
        "id": item["id"],
        "stage": stage_name,
        "priority": item["priority"],
        "category": item["category"],
        "next_action": item["next_action"],
        "blocked_reason": item["blocked_reason"],
        "missing_placeholders": item["missing_placeholders"],
        "requires_upstream": item["requires_upstream"],
        "user_step": item["user_step"],
        "preflight": item["preflight"],
        "failure_state": item["failure_state"],
        "evidence_role": item["evidence_role"],
        "product_surface": item["product_surface"],
    }


def build_batch_manifest(runbook: dict[str, Any]) -> dict[str, Any]:
    ready_steps: list[dict[str, Any]] = []
    blocked_steps: list[dict[str, Any]] = []
    for stage in runbook["stages"]:
        stage_name = stage["name"]
        for item in stage["items"]:
            if stage_name in {"ready_collectors", "ready_lenses"}:
                ready_steps.append(execution_step(item, stage_name=stage_name, step_number=len(ready_steps) + 1))
            else:
                blocked_steps.append(blocked_step(item, stage_name=stage_name))

    return {
        "schema": "collectorx.finclaw_batch_manifest.v1",
        "runbook_schema": runbook["schema"],
        "summary": {
            "total": runbook["total"],
            "ready_steps": len(ready_steps),
            "blocked_steps": len(blocked_steps),
            "by_stage": runbook["summary"]["by_stage"],
        },
        "auto_upstream_links": runbook.get("auto_upstream_links", []),
        "ready_steps": ready_steps,
        "blocked_steps": blocked_steps,
    }


def closeout_launch_tier(entry: dict[str, Any], product_surface: str | None) -> str:
    readiness = entry["readiness"]
    if readiness == "production-candidate":
        return "guarded-production-candidate"
    if readiness == "deep-beta":
        return "invite-only-deep-beta"
    if product_surface == "lens-beta":
        return "downstream-lens-beta"
    if product_surface == "managed-oauth-beta":
        return "managed-authorization-beta"
    return "authorized-import-or-local-beta"


def closeout_product_claim(entry: dict[str, Any]) -> str:
    readiness = entry["readiness"]
    if readiness == "production-candidate":
        return "may_expose_as_guarded_collector_after_preflight"
    if readiness == "deep-beta":
        return "may_expose_to_invited_beta_users_with_caveats"
    return "must_not_claim_production_without_real_validation"


def closeout_remaining_validation_scope(entry: dict[str, Any]) -> str:
    if not str(entry.get("production_gap", "")).strip():
        return "none_recorded"
    if entry["readiness"] == "production-candidate":
        return "post_guarded_launch_validation"
    return "pre_production_validation"


def closeout_item(entry: dict[str, Any]) -> dict[str, Any]:
    contract = entry.get("invocation_contract") or {}
    product_surface = contract.get("product_surface")
    production_gap = str(entry["production_gap"])
    return {
        "id": entry["id"],
        "priority": entry["priority"],
        "category": entry["category"],
        "skill": entry["skill"],
        "readiness": entry["readiness"],
        "gate": entry["gate"],
        "product_surface": product_surface,
        "authorization_mode": contract.get("authorization_mode"),
        "evidence_role": contract.get("evidence_role"),
        "launch_tier": closeout_launch_tier(entry, product_surface),
        "product_claim": closeout_product_claim(entry),
        "requires_real_validation_before_production": entry["readiness"] != "production-candidate",
        "has_remaining_validation_gap": bool(production_gap.strip()),
        "remaining_validation_scope": closeout_remaining_validation_scope(entry),
        "production_gap": production_gap,
        "cannot_claim": entry["must_not_collect"],
        "failure_state": contract.get("failure_state"),
    }


def build_closeout_report(entries: list[dict[str, Any]]) -> dict[str, Any]:
    items = [closeout_item(entry) for entry in entries]
    return {
        "schema": "collectorx.finclaw_closeout_readiness.v1",
        "total": len(items),
        "summary": {
            "by_priority": dict(sorted(Counter(item["priority"] for item in items).items())),
            "by_category": dict(sorted(Counter(item["category"] for item in items).items())),
            "by_readiness": dict(sorted(Counter(item["readiness"] for item in items).items())),
            "by_product_surface": dict(sorted(Counter(item["product_surface"] for item in items).items())),
            "by_launch_tier": dict(sorted(Counter(item["launch_tier"] for item in items).items())),
            "production_candidates": sum(1 for item in items if item["readiness"] == "production-candidate"),
            "requires_real_validation_before_production": sum(
                1 for item in items if item["requires_real_validation_before_production"]
            ),
            "entries_with_remaining_validation_gap": sum(1 for item in items if item["has_remaining_validation_gap"]),
            "by_remaining_validation_scope": dict(
                sorted(Counter(item["remaining_validation_scope"] for item in items).items())
            ),
        },
        "items": items,
    }


def print_human_closeout(report: dict[str, Any]) -> None:
    print(f"total: {report['total']}")
    print(f"production_candidates: {report['summary']['production_candidates']}")
    print(
        "requires_real_validation_before_production: "
        f"{report['summary']['requires_real_validation_before_production']}"
    )
    print(f"entries_with_remaining_validation_gap: {report['summary']['entries_with_remaining_validation_gap']}")
    items = report["items"]
    if not items:
        print("No entries matched.")
        return
    headers = ("id", "P", "readiness", "surface", "launch_tier", "claim")
    rows = [
        (
            item["id"],
            item["priority"],
            item["readiness"],
            item["product_surface"],
            item["launch_tier"],
            item["product_claim"],
        )
        for item in items
    ]
    widths = [
        max(len(str(value)) for value in column)
        for column in zip(headers, *rows, strict=False)
    ]
    print("  ".join(str(value).ljust(width) for value, width in zip(headers, widths, strict=False)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths, strict=False)))


def cmd_closeout(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    report = build_closeout_report(entries)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_closeout(report)
    return 0


def validation_backlog_item(entry: dict[str, Any], *, order: int) -> dict[str, Any]:
    contract = entry.get("invocation_contract") or {}
    closeout = closeout_item(entry)
    return {
        "order": order,
        "id": entry["id"],
        "priority": entry["priority"],
        "category": entry["category"],
        "skill": entry["skill"],
        "readiness": entry["readiness"],
        "gate": entry["gate"],
        "launch_tier": closeout["launch_tier"],
        "remaining_validation_scope": closeout["remaining_validation_scope"],
        "requires_real_validation_before_production": closeout["requires_real_validation_before_production"],
        "product_surface": contract.get("product_surface"),
        "authorization_mode": contract.get("authorization_mode"),
        "evidence_role": contract.get("evidence_role"),
        "failure_state": contract.get("failure_state"),
        "requires_upstream": contract.get("requires_upstream", []),
        "production_gap": closeout["production_gap"],
    }


def build_validation_backlog(entries: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        validation_backlog_item(entry, order=order)
        for order, entry in enumerate(entries, start=1)
        if str(entry.get("production_gap", "")).strip()
    ]
    return {
        "schema": "collectorx.finclaw_real_validation_backlog.v1",
        "closeout_schema": "collectorx.finclaw_closeout_readiness.v1",
        "total": len(items),
        "summary": {
            "by_priority": dict(sorted(Counter(item["priority"] for item in items).items())),
            "by_category": dict(sorted(Counter(item["category"] for item in items).items())),
            "by_readiness": dict(sorted(Counter(item["readiness"] for item in items).items())),
            "by_remaining_validation_scope": dict(
                sorted(Counter(item["remaining_validation_scope"] for item in items).items())
            ),
            "requires_real_validation_before_production": sum(
                1 for item in items if item["requires_real_validation_before_production"]
            ),
        },
        "items": items,
    }


def print_human_validation_backlog(report: dict[str, Any]) -> None:
    print(f"total: {report['total']}")
    items = report["items"]
    if not items:
        print("No validation backlog entries matched.")
        return
    headers = ("order", "id", "P", "readiness", "scope", "production_gap")
    rows = [
        (
            item["order"],
            item["id"],
            item["priority"],
            item["readiness"],
            item["remaining_validation_scope"],
            item["production_gap"],
        )
        for item in items
    ]
    widths = [
        max(len(str(value)) for value in column)
        for column in zip(headers, *rows, strict=False)
    ]
    print("  ".join(str(value).ljust(width) for value, width in zip(headers, widths, strict=False)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths, strict=False)))


def cmd_validation_backlog(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    report = build_validation_backlog(entries)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_validation_backlog(report)
    return 0


VALIDATION_EVIDENCE_SCHEMA = "collectorx.finclaw_real_validation_evidence.v1"
REAL_VALIDATION_TYPES = {
    "real_user_authorization",
    "real_account",
    "real_device",
    "real_export",
    "real_readonly_screen",
    "real_api_response",
    "wiki_backtest",
    "package_validation",
}
GAP_CLOSING_DECISIONS = {
    "gap_closed",
    "post_guarded_gap_closed",
    "ready_for_readiness_review",
}


def template_decision_for_item(item: dict[str, Any]) -> str:
    if item["remaining_validation_scope"] == "post_guarded_launch_validation":
        return "post_guarded_gap_closed"
    return "ready_for_readiness_review"


def validation_template_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": f"{item['id']}-real-validation-001",
        "collector_id": item["id"],
        "priority": item["priority"],
        "category": item["category"],
        "current_readiness": item["readiness"],
        "launch_tier": item["launch_tier"],
        "remaining_validation_scope": item["remaining_validation_scope"],
        "production_gap": item["production_gap"],
        "result": "<pass|fail|partial>",
        "decision": template_decision_for_item(item),
        "covers_production_gap": False,
        "evidence_types": [],
        "required_evidence_type_options": sorted(REAL_VALIDATION_TYPES),
        "artifacts": [],
        "validated_at": "<YYYY-MM-DDTHH:MM:SS+08:00>",
        "validated_by": "<qa-owner>",
        "notes": "",
    }


def build_validation_template(entries: list[dict[str, Any]]) -> dict[str, Any]:
    backlog = build_validation_backlog(entries)
    return {
        "schema": VALIDATION_EVIDENCE_SCHEMA,
        "template_schema": "collectorx.finclaw_real_validation_evidence_template.v1",
        "validation_backlog_schema": backlog["schema"],
        "template_only": True,
        "instructions": [
            "Fill one record after real user authorization and real validation artifacts exist.",
            "Set result=pass only after package, scope, read-only, and Wiki evidence checks pass.",
            "Set covers_production_gap=true only when the artifacts address the recorded production_gap.",
            "Leave unknown or incomplete records as non-pass; validation-evidence will keep them blocked.",
        ],
        "total": backlog["total"],
        "summary": backlog["summary"],
        "records": [validation_template_record(item) for item in backlog["items"]],
    }


def print_human_validation_template(template: dict[str, Any]) -> None:
    print(f"schema: {template['schema']}")
    print(f"template_schema: {template['template_schema']}")
    print(f"total_records: {template['total']}")
    print("Use --json to write the fillable ledger template.")


def cmd_validation_template(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    template = build_validation_template(entries)
    if args.json:
        print(json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_validation_template(template)
    return 0


def load_validation_evidence(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"validation evidence file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"validation evidence file is not valid JSON: {path}: {exc}") from exc

    issues: list[str] = []
    if isinstance(payload, list):
        records = payload
        issues.append("missing_top_level_schema")
    elif isinstance(payload, dict):
        if payload.get("schema") != VALIDATION_EVIDENCE_SCHEMA:
            issues.append("invalid_or_missing_schema")
        records = payload.get("records", [])
    else:
        raise SystemExit("validation evidence must be a JSON object or list")

    if not isinstance(records, list):
        raise SystemExit("validation evidence records must be a list")
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        if isinstance(record, dict):
            normalized.append(record)
        else:
            issues.append(f"record_{index}_is_not_object")
    return normalized, issues


def validation_record_collector_id(record: dict[str, Any]) -> str:
    return str(record.get("collector_id") or record.get("id") or "").strip()


def validation_record_artifacts(record: dict[str, Any]) -> list[Any]:
    artifacts = record.get("artifacts")
    if artifacts is None:
        artifacts = record.get("artifact_refs")
    return artifacts if isinstance(artifacts, list) else []


def validation_record_types(record: dict[str, Any]) -> set[str]:
    raw_types = record.get("evidence_types")
    if raw_types is None:
        raw_types = record.get("evidence_type")
    if isinstance(raw_types, str):
        return {raw_types}
    if isinstance(raw_types, list):
        return {str(value) for value in raw_types if str(value).strip()}
    return set()


def validation_record_timestamp(record: dict[str, Any]) -> str:
    return str(record.get("validated_at") or record.get("checked_at") or "").strip()


def validation_record_reviewer(record: dict[str, Any]) -> str:
    return str(record.get("validated_by") or record.get("reviewer") or "").strip()


def artifact_path_value(artifact: Any) -> str:
    if isinstance(artifact, str):
        return artifact.strip()
    if isinstance(artifact, dict):
        return str(artifact.get("path") or artifact.get("local_path") or "").strip()
    return ""


def artifact_sha256_value(artifact: Any) -> str:
    if isinstance(artifact, dict):
        return str(artifact.get("sha256") or "").strip().lower()
    return ""


def resolve_artifact_path(raw_path: str, artifact_root: Path | None) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (artifact_root or Path.cwd()) / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_integrity_issues(artifacts: list[Any], *, artifact_root: Path | None) -> list[str]:
    issues: list[str] = []
    for artifact in artifacts:
        raw_path = artifact_path_value(artifact)
        if not raw_path:
            issues.append("artifact_missing_path")
            continue
        if "<" in raw_path or ">" in raw_path:
            issues.append("artifact_path_placeholder")
            continue
        path = resolve_artifact_path(raw_path, artifact_root)
        if not path.is_file():
            issues.append("artifact_path_not_found")
            continue
        expected_sha256 = artifact_sha256_value(artifact)
        if not expected_sha256:
            issues.append("artifact_missing_sha256")
            continue
        if "<" in expected_sha256 or ">" in expected_sha256:
            issues.append("artifact_sha256_placeholder")
            continue
        if sha256_file(path) != expected_sha256:
            issues.append("artifact_sha256_mismatch")
    return issues


def validation_record_issues(
    record: dict[str, Any],
    item: dict[str, Any],
    *,
    verify_artifacts: bool = False,
    artifact_root: Path | None = None,
) -> list[str]:
    issues: list[str] = []
    collector_id = validation_record_collector_id(record)
    if collector_id != item["id"]:
        issues.append("collector_id_mismatch")
    if record.get("result") != "pass":
        issues.append("result_not_pass")
    if record.get("decision") not in GAP_CLOSING_DECISIONS:
        issues.append("decision_not_gap_closing")
    if record.get("covers_production_gap") is not True:
        issues.append("does_not_cover_production_gap")
    evidence_types = validation_record_types(record)
    if not evidence_types:
        issues.append("missing_evidence_types")
    elif not evidence_types.intersection(REAL_VALIDATION_TYPES):
        issues.append("missing_real_validation_type")
    if not validation_record_artifacts(record):
        issues.append("missing_artifacts")
    elif verify_artifacts:
        issues.extend(artifact_integrity_issues(validation_record_artifacts(record), artifact_root=artifact_root))
    if not validation_record_timestamp(record):
        issues.append("missing_validated_at")
    if not validation_record_reviewer(record):
        issues.append("missing_validated_by")
    return issues


def accepted_validation_record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record.get("record_id") or record.get("id"),
        "decision": record.get("decision"),
        "result": record.get("result"),
        "validated_at": validation_record_timestamp(record),
        "validated_by": validation_record_reviewer(record),
        "evidence_types": sorted(validation_record_types(record)),
        "artifact_count": len(validation_record_artifacts(record)),
    }


def validation_evidence_item(
    item: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    verify_artifacts: bool = False,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    candidate_records = [record for record in records if validation_record_collector_id(record) == item["id"]]
    if not candidate_records:
        status = "missing_evidence"
        accepted_record = None
        issues = ["missing_validation_evidence"]
    else:
        evaluations = [
            (
                record,
                validation_record_issues(
                    record,
                    item,
                    verify_artifacts=verify_artifacts,
                    artifact_root=artifact_root,
                ),
            )
            for record in candidate_records
        ]
        accepted = [record for record, record_issues in evaluations if not record_issues]
        if accepted:
            status = "ready_for_readiness_review"
            accepted_record = accepted[-1]
            issues = []
        else:
            status = "insufficient_evidence"
            accepted_record = None
            issue_set = {issue for _, record_issues in evaluations for issue in record_issues}
            issues = sorted(issue_set)

    return {
        **item,
        "evidence_status": status,
        "readiness_review_allowed": status == "ready_for_readiness_review",
        "evidence_record_count": len(candidate_records),
        "accepted_evidence": accepted_validation_record_summary(accepted_record) if accepted_record else None,
        "issues": issues,
    }


def build_validation_evidence_report(
    entries: list[dict[str, Any]],
    *,
    evidence_path: Path,
    verify_artifacts: bool = False,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    records, ledger_issues = load_validation_evidence(evidence_path)
    backlog = build_validation_backlog(entries)
    backlog_by_id = {item["id"]: item for item in backlog["items"]}
    effective_artifact_root = artifact_root or evidence_path.parent
    items = [
        validation_evidence_item(
            item,
            records,
            verify_artifacts=verify_artifacts,
            artifact_root=effective_artifact_root,
        )
        for item in backlog["items"]
    ]
    matched_ids = {item["id"] for item in items}
    unmatched_records = [
        {
            "record_index": index,
            "collector_id": validation_record_collector_id(record),
            "issue": "not_in_selected_validation_backlog",
        }
        for index, record in enumerate(records, start=1)
        if validation_record_collector_id(record) not in matched_ids
    ]
    by_status = Counter(item["evidence_status"] for item in items)
    not_review_ready = [item for item in items if not item["readiness_review_allowed"]]
    return {
        "schema": "collectorx.finclaw_real_validation_evidence_audit.v1",
        "evidence_schema": VALIDATION_EVIDENCE_SCHEMA,
        "validation_backlog_schema": backlog["schema"],
        "evidence_path": str(evidence_path),
        "artifact_verification": {
            "enabled": verify_artifacts,
            "artifact_root": str(effective_artifact_root) if verify_artifacts else None,
        },
        "ledger_issues": ledger_issues,
        "total": len(items),
        "summary": {
            "by_evidence_status": dict(sorted(by_status.items())),
            "ready_for_readiness_review": by_status.get("ready_for_readiness_review", 0),
            "missing_evidence": by_status.get("missing_evidence", 0),
            "insufficient_evidence": by_status.get("insufficient_evidence", 0),
            "not_ready_for_readiness_review": len(not_review_ready),
            "blocked_before_production": sum(
                1
                for item in not_review_ready
                if item["remaining_validation_scope"] == "pre_production_validation"
            ),
            "guarded_post_launch_remaining": sum(
                1
                for item in not_review_ready
                if item["remaining_validation_scope"] == "post_guarded_launch_validation"
            ),
            "unmatched_evidence_records": len(unmatched_records),
        },
        "unmatched_records": unmatched_records,
        "items": items,
        "catalog_backlog_ids": sorted(backlog_by_id),
    }


def print_human_validation_evidence(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"total: {report['total']}")
    print(f"ready_for_readiness_review: {summary['ready_for_readiness_review']}")
    print(f"not_ready_for_readiness_review: {summary['not_ready_for_readiness_review']}")
    if report["ledger_issues"]:
        print(f"ledger issues: {', '.join(report['ledger_issues'])}")
    if report["unmatched_records"]:
        print(f"unmatched evidence records: {len(report['unmatched_records'])}")
    items = report["items"]
    if not items:
        print("No validation backlog entries matched.")
        return
    headers = ("id", "P", "scope", "evidence_status", "records", "issues")
    rows = [
        (
            item["id"],
            item["priority"],
            item["remaining_validation_scope"],
            item["evidence_status"],
            item["evidence_record_count"],
            ",".join(item["issues"]),
        )
        for item in items
    ]
    widths = [
        max(len(str(value)) for value in column)
        for column in zip(headers, *rows, strict=False)
    ]
    print("  ".join(str(value).ljust(width) for value, width in zip(headers, widths, strict=False)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths, strict=False)))


def cmd_validation_evidence(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    report = build_validation_evidence_report(
        entries,
        evidence_path=Path(args.evidence),
        verify_artifacts=args.verify_artifacts,
        artifact_root=artifact_root,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_validation_evidence(report)
    if args.require_all_review_ready and report["summary"]["not_ready_for_readiness_review"]:
        return 2
    return 0


def readiness_review_type(item: dict[str, Any]) -> str:
    if item["remaining_validation_scope"] == "post_guarded_launch_validation":
        return "post_guarded_validation_review"
    if item["readiness"] == "deep-beta":
        return "production_candidate_review"
    if item["product_surface"] == "lens-beta":
        return "lens_beta_review"
    if item["product_surface"] == "managed-oauth-beta":
        return "managed_authorization_review"
    return "beta_readiness_review"


def readiness_review_next_action(item: dict[str, Any]) -> str:
    if not item["readiness_review_allowed"]:
        return "keep_current_readiness_and_collect_more_evidence"
    if item["remaining_validation_scope"] == "post_guarded_launch_validation":
        return "human_review_can_consider_clearing_post_guarded_gap"
    return "human_review_can_consider_readiness_promotion"


def readiness_review_checks(item: dict[str, Any]) -> list[str]:
    checks = [
        "inspect_artifacts_against_production_gap",
        "rerun_package_validation_on_referenced_package",
        "verify_no_gap_events_enter_investor_wiki",
        "confirm_user_authorization_and_read_only_boundary",
        "confirm_scope_policy_and_failure_state_are_still_true",
    ]
    if item["category"] in {"vertical", "lens"}:
        checks.append("rerun_investor_wiki_evidence_validation")
    if item["remaining_validation_scope"] == "pre_production_validation":
        checks.append("confirm_real_account_or_real_export_coverage_before_promotion")
    if item["remaining_validation_scope"] == "post_guarded_launch_validation":
        checks.append("confirm_guarded_launch_telemetry_and_post_launch_sample_coverage")
    return checks


def readiness_review_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "priority": item["priority"],
        "category": item["category"],
        "skill": item["skill"],
        "current_readiness": item["readiness"],
        "current_launch_tier": item["launch_tier"],
        "remaining_validation_scope": item["remaining_validation_scope"],
        "production_gap": item["production_gap"],
        "evidence_status": item["evidence_status"],
        "evidence_record_count": item["evidence_record_count"],
        "accepted_evidence": item["accepted_evidence"],
        "issues": item["issues"],
        "readiness_review_allowed": item["readiness_review_allowed"],
        "review_type": readiness_review_type(item),
        "next_action": readiness_review_next_action(item),
        "required_human_checks": readiness_review_checks(item),
        "catalog_update_allowed_by_tool": False,
        "catalog_update_policy": "manual_catalog_change_after_human_review_and_full_validation_only",
    }


def build_readiness_review_packet(
    entries: list[dict[str, Any]],
    *,
    evidence_path: Path,
    verify_artifacts: bool = False,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    evidence_report = build_validation_evidence_report(
        entries,
        evidence_path=evidence_path,
        verify_artifacts=verify_artifacts,
        artifact_root=artifact_root,
    )
    items = [readiness_review_item(item) for item in evidence_report["items"]]
    eligible = [item for item in items if item["readiness_review_allowed"]]
    blocked = [item for item in items if not item["readiness_review_allowed"]]
    return {
        "schema": "collectorx.finclaw_readiness_review_packet.v1",
        "validation_evidence_audit_schema": evidence_report["schema"],
        "evidence_path": evidence_report["evidence_path"],
        "artifact_verification": evidence_report["artifact_verification"],
        "total": len(items),
        "summary": {
            "eligible_for_human_review": len(eligible),
            "blocked_from_human_review": len(blocked),
            "by_review_type": dict(sorted(Counter(item["review_type"] for item in items).items())),
            "by_next_action": dict(sorted(Counter(item["next_action"] for item in items).items())),
            "by_evidence_status": evidence_report["summary"]["by_evidence_status"],
            "ledger_issues": len(evidence_report["ledger_issues"]),
            "unmatched_evidence_records": evidence_report["summary"]["unmatched_evidence_records"],
        },
        "ledger_issues": evidence_report["ledger_issues"],
        "unmatched_records": evidence_report["unmatched_records"],
        "eligible_reviews": eligible,
        "blocked_reviews": blocked,
    }


def print_human_readiness_review(packet: dict[str, Any]) -> None:
    summary = packet["summary"]
    print(f"total: {packet['total']}")
    print(f"eligible_for_human_review: {summary['eligible_for_human_review']}")
    print(f"blocked_from_human_review: {summary['blocked_from_human_review']}")
    if packet["ledger_issues"]:
        print(f"ledger issues: {', '.join(packet['ledger_issues'])}")
    if packet["unmatched_records"]:
        print(f"unmatched evidence records: {len(packet['unmatched_records'])}")
    print("eligible:")
    for item in packet["eligible_reviews"]:
        print(f"  - {item['id']} ({item['review_type']}): {item['next_action']}")
    print("blocked:")
    for item in packet["blocked_reviews"]:
        print(f"  - {item['id']} ({item['evidence_status']}): {','.join(item['issues'])}")


def cmd_readiness_review(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    packet = build_readiness_review_packet(
        entries,
        evidence_path=Path(args.evidence),
        verify_artifacts=args.verify_artifacts,
        artifact_root=artifact_root,
    )
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_readiness_review(packet)
    if args.require_any_eligible and not packet["summary"]["eligible_for_human_review"]:
        return 2
    return 0


def print_human_runbook(runbook: dict[str, Any]) -> None:
    print(f"total: {runbook['total']}")
    for stage in runbook["stages"]:
        print(f"{stage['name']}: {stage['count']}")
        for item in stage["items"]:
            print(f"  - {item['id']} ({item['priority']}/{item['category']}): {item['next_action']}")


def cmd_runbook(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    replacements = parse_set_values(args.set_values or [])
    runbook = build_runbook_for_options(
        entries,
        replacements=replacements,
        out_dir_root=args.out_dir_root,
        auto_link_upstream=args.auto_link_upstream,
    )
    if args.json:
        print(json.dumps(runbook, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_runbook(runbook)
    if args.require_all_ready and runbook["not_ready"]:
        return 2
    return 0


def print_human_batch_manifest(manifest: dict[str, Any]) -> None:
    print(f"total: {manifest['summary']['total']}")
    print(f"ready_steps: {manifest['summary']['ready_steps']}")
    print(f"blocked_steps: {manifest['summary']['blocked_steps']}")
    for step in manifest["ready_steps"]:
        print(f"  {step['step']}. {step['id']} ({step['stage']}): {shlex.join(step['argv'])}")
    if manifest["blocked_steps"]:
        print("blocked:")
        for step in manifest["blocked_steps"]:
            print(f"  - {step['id']} ({step['stage']}): {step['next_action']}")


def cmd_batch_manifest(args: argparse.Namespace) -> int:
    entries = filtered_entries(args)
    replacements = parse_set_values(args.set_values or [])
    runbook = build_runbook_for_options(
        entries,
        replacements=replacements,
        out_dir_root=args.out_dir_root,
        auto_link_upstream=args.auto_link_upstream,
    )
    manifest = build_batch_manifest(runbook)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_batch_manifest(manifest)
    if args.require_all_ready and manifest["summary"]["blocked_steps"]:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect FinClaw investor collector catalog.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List FinClaw investor collectors.")
    list_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    list_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    list_parser.add_argument("--readiness")
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show one catalog entry with invocation contract.")
    show_parser.add_argument("collector_id")
    show_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    show_parser.set_defaults(func=cmd_show)

    plan_parser = subparsers.add_parser("plan", help="Render a collector invocation plan.")
    plan_parser.add_argument("collector_id")
    plan_parser.add_argument("--out-dir", help="Replace the <out-dir> command placeholder.")
    plan_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        metavar="PLACEHOLDER=VALUE",
        help="Replace an arbitrary command placeholder, e.g. --set authorized-email-export=/tmp/mail.",
    )
    plan_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    plan_parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit with status 2 unless the rendered plan is ready for ordinary command execution.",
    )
    plan_parser.set_defaults(func=cmd_plan)

    doctor_parser = subparsers.add_parser("doctor", help="Summarize FinClaw collector readiness.")
    doctor_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    doctor_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    doctor_parser.add_argument("--readiness")
    doctor_parser.add_argument(
        "--out-dir-root",
        help="Replace <out-dir> with <out-dir-root>/<collector-id> for each catalog entry.",
    )
    doctor_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        metavar="PLACEHOLDER=VALUE",
        help="Replace an arbitrary command placeholder across all plans.",
    )
    doctor_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    doctor_parser.add_argument(
        "--require-all-ready",
        action="store_true",
        help="Exit with status 2 unless every selected entry is ready for ordinary command execution.",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    closeout_parser = subparsers.add_parser(
        "closeout",
        help="Summarize product closeout tiers and remaining real-validation gaps.",
    )
    closeout_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    closeout_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    closeout_parser.add_argument("--readiness")
    closeout_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    closeout_parser.set_defaults(func=cmd_closeout)

    validation_backlog_parser = subparsers.add_parser(
        "validation-backlog",
        help="List remaining real-user/device/export validation work.",
    )
    validation_backlog_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    validation_backlog_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    validation_backlog_parser.add_argument("--readiness")
    validation_backlog_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    validation_backlog_parser.set_defaults(func=cmd_validation_backlog)

    validation_template_parser = subparsers.add_parser(
        "validation-template",
        help="Generate a fillable real-validation evidence ledger template from the backlog.",
    )
    validation_template_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    validation_template_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    validation_template_parser.add_argument("--readiness")
    validation_template_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    validation_template_parser.set_defaults(func=cmd_validation_template)

    validation_evidence_parser = subparsers.add_parser(
        "validation-evidence",
        help="Audit a real-validation evidence ledger against the remaining backlog.",
    )
    validation_evidence_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    validation_evidence_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    validation_evidence_parser.add_argument("--readiness")
    validation_evidence_parser.add_argument("--evidence", required=True, help="Path to validation evidence JSON.")
    validation_evidence_parser.add_argument(
        "--verify-artifacts",
        action="store_true",
        help="Verify artifact local paths and sha256 values before accepting evidence.",
    )
    validation_evidence_parser.add_argument(
        "--artifact-root",
        help="Resolve relative artifact paths under this directory. Defaults to the evidence file directory.",
    )
    validation_evidence_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    validation_evidence_parser.add_argument(
        "--require-all-review-ready",
        action="store_true",
        help="Exit with status 2 unless every selected backlog item has enough evidence for readiness review.",
    )
    validation_evidence_parser.set_defaults(func=cmd_validation_evidence)

    readiness_review_parser = subparsers.add_parser(
        "readiness-review",
        help="Build a human readiness-review packet from audited real-validation evidence.",
    )
    readiness_review_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    readiness_review_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    readiness_review_parser.add_argument("--readiness")
    readiness_review_parser.add_argument("--evidence", required=True, help="Path to validation evidence JSON.")
    readiness_review_parser.add_argument(
        "--verify-artifacts",
        action="store_true",
        help="Verify artifact local paths and sha256 values before allowing human review.",
    )
    readiness_review_parser.add_argument(
        "--artifact-root",
        help="Resolve relative artifact paths under this directory. Defaults to the evidence file directory.",
    )
    readiness_review_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    readiness_review_parser.add_argument(
        "--require-any-eligible",
        action="store_true",
        help="Exit with status 2 unless at least one selected backlog item is ready for human review.",
    )
    readiness_review_parser.set_defaults(func=cmd_readiness_review)

    runbook_parser = subparsers.add_parser("runbook", help="Build a staged FinClaw collector runbook.")
    runbook_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    runbook_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    runbook_parser.add_argument("--readiness")
    runbook_parser.add_argument(
        "--out-dir-root",
        help="Replace <out-dir> with <out-dir-root>/<collector-id> for each catalog entry.",
    )
    runbook_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        metavar="PLACEHOLDER=VALUE",
        help="Replace an arbitrary command placeholder across all plans.",
    )
    runbook_parser.add_argument(
        "--no-auto-link-upstream",
        dest="auto_link_upstream",
        action="store_false",
        default=True,
        help="Do not auto-fill <upstream-id-events-jsonl> placeholders from ready upstream package paths.",
    )
    runbook_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    runbook_parser.add_argument(
        "--require-all-ready",
        action="store_true",
        help="Exit with status 2 unless every selected entry is ready for ordinary command execution.",
    )
    runbook_parser.set_defaults(func=cmd_runbook)

    batch_manifest_parser = subparsers.add_parser(
        "batch-manifest",
        help="Build a compact execution manifest for FinClaw product runners.",
    )
    batch_manifest_parser.add_argument("--priority", choices=["P0", "P1", "P2", "supporting"])
    batch_manifest_parser.add_argument("--category", choices=["generic", "vertical", "lens"])
    batch_manifest_parser.add_argument("--readiness")
    batch_manifest_parser.add_argument(
        "--out-dir-root",
        help="Replace <out-dir> with <out-dir-root>/<collector-id> for each catalog entry.",
    )
    batch_manifest_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        metavar="PLACEHOLDER=VALUE",
        help="Replace an arbitrary command placeholder across all plans.",
    )
    batch_manifest_parser.add_argument(
        "--no-auto-link-upstream",
        dest="auto_link_upstream",
        action="store_false",
        default=True,
        help="Do not auto-fill <upstream-id-events-jsonl> placeholders from ready upstream package paths.",
    )
    batch_manifest_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    batch_manifest_parser.add_argument(
        "--require-all-ready",
        action="store_true",
        help="Exit with status 2 unless every selected entry is ready for ordinary command execution.",
    )
    batch_manifest_parser.set_defaults(func=cmd_batch_manifest)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
