#!/usr/bin/env python3
"""Inspect FinClaw investor collector catalog and invocation contracts."""

from __future__ import annotations

import argparse
from collections import Counter
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
