#!/usr/bin/env python3
"""Tests for the FinClaw catalog inspection CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_proc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/finclaw_catalog.py", *args],
        cwd=str(ROOT),
        text=True,
        check=False,
        capture_output=True,
    )


def run_json(*args: str) -> object:
    proc = run_proc(*args)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def test_list_includes_catalog_and_contract_fields() -> None:
    entries = run_json("list", "--json")
    assert isinstance(entries, list)
    by_id = {entry["id"]: entry for entry in entries}
    assert "ths-watchlist" in by_id
    assert by_id["eastmoney-portfolio"]["product_surface"] == "guarded-production"
    assert by_id["social-investment-influence"]["authorization_mode"] == "lake-lens"
    assert by_id["qq"]["failure_state"] == "needs_readable_qq_db"


def test_show_lens_includes_upstream_contract() -> None:
    entry = run_json("show", "social-investment-influence", "--json")
    assert entry["category"] == "lens"
    contract = entry["invocation_contract"]
    assert contract["requires_upstream"] == ["social-activity"]
    assert contract["evidence_role"] == "weak-influence"


def test_plan_replaces_placeholders() -> None:
    plan = run_json(
        "plan",
        "ths-watchlist",
        "--out-dir",
        "/tmp/collectorx-out",
        "--set",
        "authorized-ths-watchlist-export=/tmp/watch.csv",
        "--json",
    )
    assert plan["ready_to_run"] is True
    assert plan["next_action"] == "run_command"
    assert plan["blocked_reason"] is None
    assert plan["missing_placeholders"] == []
    assert "<out-dir>" not in plan["command"]
    assert "<authorized-ths-watchlist-export>" not in plan["command"]
    assert "skills/ths-watchlist/scripts/ths_watchlist.py" in plan["command"]


def test_plan_reports_missing_placeholders_and_require_ready_fails() -> None:
    proc = run_proc(
        "plan",
        "ths-watchlist",
        "--out-dir",
        "/tmp/collectorx-out",
        "--json",
        "--require-ready",
    )
    assert proc.returncode == 2
    plan = json.loads(proc.stdout)
    assert plan["ready_to_run"] is False
    assert plan["next_action"] == "fill_placeholders"
    assert plan["blocked_reason"] == "missing_placeholders:authorized-ths-watchlist-export"
    assert plan["missing_placeholders"] == ["authorized-ths-watchlist-export"]


def test_require_ready_allows_ready_command_plan() -> None:
    proc = run_proc(
        "plan",
        "ths-watchlist",
        "--out-dir",
        "/tmp/collectorx-out",
        "--set",
        "authorized-ths-watchlist-export=/tmp/watch.csv",
        "--json",
        "--require-ready",
    )
    assert proc.returncode == 0
    plan = json.loads(proc.stdout)
    assert plan["ready_to_run"] is True


def test_soulmirror_plan_is_not_plain_command() -> None:
    plan = run_json("plan", "ticktick", "--json")
    assert plan["runner"] == "soulmirror"
    assert plan["ready_to_run"] is False
    assert plan["next_action"] == "use_soulmirror_runner"
    assert plan["blocked_reason"] == "soulmirror_runner_required"
    assert plan["failure_state"] == "ticktick_auth_required"


def test_require_ready_rejects_soulmirror_plan() -> None:
    proc = run_proc("plan", "ticktick", "--json", "--require-ready")
    assert proc.returncode == 2
    plan = json.loads(proc.stdout)
    assert plan["runner"] == "soulmirror"
    assert plan["next_action"] == "use_soulmirror_runner"


def main() -> int:
    test_list_includes_catalog_and_contract_fields()
    test_show_lens_includes_upstream_contract()
    test_plan_replaces_placeholders()
    test_plan_reports_missing_placeholders_and_require_ready_fails()
    test_require_ready_allows_ready_command_plan()
    test_soulmirror_plan_is_not_plain_command()
    test_require_ready_rejects_soulmirror_plan()
    print("finclaw catalog tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
