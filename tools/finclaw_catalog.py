#!/usr/bin/env python3
"""Inspect FinClaw investor collector catalog and invocation contracts."""

from __future__ import annotations

import argparse
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


def plan_status(runner: str, placeholders: list[str]) -> tuple[str, str | None]:
    if runner == "soulmirror":
        return "use_soulmirror_runner", "soulmirror_runner_required"
    if placeholders:
        return "fill_placeholders", f"missing_placeholders:{','.join(placeholders)}"
    return "run_command", None


def build_plan(entry: dict[str, Any], *, replacements: dict[str, str]) -> dict[str, Any]:
    command = str(entry["cli"])
    for key, value in replacements.items():
        command = command.replace(f"<{key}>", shlex.quote(value))
    placeholders = sorted(set(re.findall(r"<([^<>]+)>", command)))
    runner = "soulmirror" if command.startswith("SoulMirror") else "command"
    next_action, blocked_reason = plan_status(runner, placeholders)
    contract = entry.get("invocation_contract") or {}
    return {
        "id": entry["id"],
        "runner": runner,
        "command": command,
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
    if args.require_ready and not plan["ready_to_run"]:
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
