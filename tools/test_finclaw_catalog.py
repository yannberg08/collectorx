#!/usr/bin/env python3
"""Tests for the FinClaw catalog inspection CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
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
        "authorized-ths-watchlist-root=/tmp/ths-root",
        "--json",
    )
    assert plan["ready_to_run"] is True
    assert plan["next_action"] == "run_command"
    assert plan["blocked_reason"] is None
    assert plan["missing_placeholders"] == []
    assert "<out-dir>" not in plan["command"]
    assert "<authorized-ths-watchlist-root>" not in plan["command"]
    assert "skills/ths-watchlist/scripts/ths_watchlist.py" in plan["command"]
    assert plan["argv"][:3] == ["python3", "skills/ths-watchlist/scripts/ths_watchlist.py", "collect"]
    assert plan["argv"][-1] == "/tmp/collectorx-out"
    validation = plan["package_validation"]
    assert validation["ready"] is True
    assert validation["package_dir"] == "/tmp/collectorx-out"
    assert validation["require_evidence"] is True
    assert validation["argv"] == [
        "python3",
        "tools/validate_collector_package.py",
        "/tmp/collectorx-out",
        "--collector",
        "ths-watchlist",
        "--require-evidence",
        "--json",
    ]


def test_plan_argv_preserves_paths_with_spaces_without_shell_quotes() -> None:
    plan = run_json(
        "plan",
        "ths-watchlist",
        "--out-dir",
        "/tmp/collectorx out",
        "--set",
        "authorized-ths-watchlist-root=/tmp/ths root",
        "--json",
    )
    assert plan["ready_to_run"] is True
    assert "'/tmp/ths root'" in plan["command"]
    assert plan["argv"][plan["argv"].index("--container-root") + 1] == "/tmp/ths root"
    assert plan["argv"][plan["argv"].index("--out-dir") + 1] == "/tmp/collectorx out"


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
    assert plan["blocked_reason"] == "missing_placeholders:authorized-ths-watchlist-root"
    assert plan["missing_placeholders"] == ["authorized-ths-watchlist-root"]
    assert plan["package_validation"]["ready"] is True


def test_require_ready_allows_ready_command_plan() -> None:
    proc = run_proc(
        "plan",
        "ths-watchlist",
        "--out-dir",
        "/tmp/collectorx-out",
        "--set",
        "authorized-ths-watchlist-root=/tmp/ths-root",
        "--json",
        "--require-ready",
    )
    assert proc.returncode == 0
    plan = json.loads(proc.stdout)
    assert plan["ready_to_run"] is True


def test_generic_package_validation_does_not_require_evidence() -> None:
    plan = run_json("plan", "email", "--out-dir", "/tmp/email-out", "--json")
    validation = plan["package_validation"]
    assert validation["ready"] is True
    assert validation["require_evidence"] is False
    assert validation["argv"] == [
        "python3",
        "tools/validate_collector_package.py",
        "/tmp/email-out",
        "--collector",
        "email",
        "--json",
    ]


def test_soulmirror_plan_is_not_plain_command() -> None:
    plan = run_json("plan", "ticktick", "--json")
    assert plan["runner"] == "soulmirror"
    assert plan["ready_to_run"] is False
    assert plan["next_action"] == "use_soulmirror_runner"
    assert plan["blocked_reason"] == "soulmirror_runner_required"
    assert plan["failure_state"] == "ticktick_auth_required"
    assert plan["package_validation"]["ready"] is False
    assert plan["package_validation"]["blocked_reason"] == "missing_output_directory"


def test_lens_plan_waits_for_upstream_lake() -> None:
    proc = run_proc("plan", "email-research", "--out-dir", "/tmp/collectorx-out", "--json", "--require-ready")
    assert proc.returncode == 2
    plan = json.loads(proc.stdout)
    assert plan["ready_to_run"] is False
    assert plan["next_action"] == "wait_for_upstream_lake"
    assert plan["blocked_reason"] == "requires_upstream:email"
    assert plan["missing_placeholders"] == ["email-events-jsonl"]
    assert plan["requires_upstream"] == ["email"]


def test_require_ready_rejects_soulmirror_plan() -> None:
    proc = run_proc("plan", "ticktick", "--json", "--require-ready")
    assert proc.returncode == 2
    plan = json.loads(proc.stdout)
    assert plan["runner"] == "soulmirror"
    assert plan["next_action"] == "use_soulmirror_runner"


def test_doctor_reports_batch_readiness_summary() -> None:
    report = run_json("doctor", "--out-dir-root", "/tmp/collectorx-out", "--json")
    assert report["schema"] == "collectorx.finclaw_catalog_doctor.v1"
    assert report["total"] >= 20
    assert report["ready_to_run"] > 0
    assert report["not_ready"] > 0
    assert report["summary"]["by_next_action"]["run_command"] > 0
    assert report["summary"]["by_next_action"]["fill_placeholders"] > 0
    assert report["summary"]["by_next_action"]["use_soulmirror_runner"] > 0
    assert report["summary"]["by_next_action"]["wait_for_upstream_lake"] > 0
    by_id = {item["id"]: item for item in report["items"]}
    assert by_id["eastmoney-portfolio"]["ready_to_run"] is True
    assert by_id["eastmoney-portfolio"]["next_action"] == "run_command"
    assert "/tmp/collectorx-out/eastmoney-portfolio" in by_id["eastmoney-portfolio"]["command"]
    assert by_id["eastmoney-portfolio"]["argv"][-1] == "/tmp/collectorx-out/eastmoney-portfolio"
    eastmoney_validation = by_id["eastmoney-portfolio"]["package_validation"]
    assert eastmoney_validation["ready"] is True
    assert eastmoney_validation["package_dir"] == "/tmp/collectorx-out/eastmoney-portfolio"
    assert eastmoney_validation["require_evidence"] is True
    assert "--require-evidence" in eastmoney_validation["argv"]
    email_validation = by_id["email"]["package_validation"]
    assert email_validation["ready"] is True
    assert email_validation["require_evidence"] is False
    assert "--require-evidence" not in email_validation["argv"]
    assert by_id["ths-watchlist"]["next_action"] == "fill_placeholders"
    assert by_id["ths-watchlist"]["missing_placeholders"] == ["authorized-ths-watchlist-root"]
    assert by_id["wechat-investment-dialogue"]["next_action"] == "wait_for_upstream_lake"
    assert by_id["wechat-investment-dialogue"]["missing_placeholders"] == ["wechat-events-jsonl"]
    wechat_lens_validation = by_id["wechat-investment-dialogue"]["package_validation"]
    assert wechat_lens_validation["ready"] is True
    assert wechat_lens_validation["require_evidence"] is True
    assert "--require-evidence" in wechat_lens_validation["argv"]
    assert by_id["ticktick"]["next_action"] == "use_soulmirror_runner"


def test_doctor_filters_priority() -> None:
    report = run_json("doctor", "--priority", "P0", "--out-dir-root", "/tmp/collectorx-out", "--json")
    assert report["total"] > 0
    assert all(item["priority"] == "P0" for item in report["items"])
    assert report["summary"]["by_priority"] == {"P0": report["total"]}


def test_doctor_require_all_ready_fails_when_any_entry_is_blocked() -> None:
    proc = run_proc("doctor", "--out-dir-root", "/tmp/collectorx-out", "--json", "--require-all-ready")
    assert proc.returncode == 2
    report = json.loads(proc.stdout)
    assert report["not_ready"] > 0


def test_closeout_report_tracks_product_tiers_and_real_validation_gaps() -> None:
    report = run_json("closeout", "--json")
    assert report["schema"] == "collectorx.finclaw_closeout_readiness.v1"
    assert report["total"] == 30
    assert report["summary"]["by_readiness"] == {
        "baseline+audit": 27,
        "deep-beta": 2,
        "production-candidate": 1,
    }
    assert report["summary"]["production_candidates"] == 1
    assert report["summary"]["requires_real_validation_before_production"] == 29
    assert report["summary"]["entries_with_remaining_validation_gap"] == 30
    assert report["summary"]["by_remaining_validation_scope"] == {
        "post_guarded_launch_validation": 1,
        "pre_production_validation": 29,
    }

    by_id = {item["id"]: item for item in report["items"]}
    assert by_id["eastmoney-portfolio"]["launch_tier"] == "guarded-production-candidate"
    assert by_id["eastmoney-portfolio"]["product_claim"] == "may_expose_as_guarded_collector_after_preflight"
    assert by_id["eastmoney-portfolio"]["requires_real_validation_before_production"] is False
    assert by_id["eastmoney-portfolio"]["has_remaining_validation_gap"] is True
    assert by_id["eastmoney-portfolio"]["remaining_validation_scope"] == "post_guarded_launch_validation"
    assert by_id["ths-portfolio"]["launch_tier"] == "invite-only-deep-beta"
    assert by_id["ths-portfolio"]["requires_real_validation_before_production"] is True
    assert by_id["ths-portfolio"]["remaining_validation_scope"] == "pre_production_validation"
    assert by_id["wechat-investment-dialogue"]["launch_tier"] == "downstream-lens-beta"
    assert by_id["ticktick"]["launch_tier"] == "managed-authorization-beta"
    assert all(item["production_gap"].strip() for item in report["items"])
    assert all(item["cannot_claim"].strip() for item in report["items"])


def stage_by_name(runbook: dict[str, object], name: str) -> dict[str, object]:
    stages = runbook["stages"]
    assert isinstance(stages, list)
    by_name = {stage["name"]: stage for stage in stages}
    return by_name[name]


def stage_ids(runbook: dict[str, object], name: str) -> set[str]:
    stage = stage_by_name(runbook, name)
    return {item["id"] for item in stage["items"]}


def test_runbook_groups_p0_entries_by_product_stage() -> None:
    runbook = run_json("runbook", "--priority", "P0", "--out-dir-root", "/tmp/collectorx-out", "--json")
    assert runbook["schema"] == "collectorx.finclaw_runbook.v1"
    assert runbook["summary"]["by_stage"]["ready_collectors"] == 4
    assert runbook["summary"]["by_stage"]["ready_lenses"] == 2
    assert runbook["summary"]["by_stage"]["needs_user_input"] == 5
    assert runbook["summary"]["by_stage"]["needs_upstream_lake"] == 1
    assert "eastmoney-portfolio" in stage_ids(runbook, "ready_collectors")
    assert "email" in stage_ids(runbook, "ready_collectors")
    assert "wechat-investment-dialogue" in stage_ids(runbook, "ready_lenses")
    assert "email-research" in stage_ids(runbook, "ready_lenses")
    assert "ths-watchlist" in stage_ids(runbook, "needs_user_input")
    assert "research-documents" in stage_ids(runbook, "needs_upstream_lake")
    links = {(link["lens_id"], link["upstream_id"], link["placeholder"], link["events_jsonl"]) for link in runbook["auto_upstream_links"]}
    assert (
        "email-research",
        "email",
        "email-events-jsonl",
        "/tmp/collectorx-out/email/lake/email/events.jsonl",
    ) in links
    email_lens = next(item for item in stage_by_name(runbook, "ready_lenses")["items"] if item["id"] == "email-research")
    assert "/tmp/collectorx-out/email/lake/email/events.jsonl" in email_lens["argv"]


def test_runbook_respects_explicit_lens_input_over_auto_link() -> None:
    runbook = run_json(
        "runbook",
        "--priority",
        "P0",
        "--out-dir-root",
        "/tmp/collectorx-out",
        "--set",
        "email-events-jsonl=/tmp/lake/email/events.jsonl",
        "--json",
    )
    assert "email-research" in stage_ids(runbook, "ready_lenses")
    ready_lens = next(item for item in stage_by_name(runbook, "ready_lenses")["items"] if item["id"] == "email-research")
    assert ready_lens["ready_to_run"] is True
    assert ready_lens["package_validation"]["require_evidence"] is True
    assert "/tmp/lake/email/events.jsonl" in ready_lens["argv"]


def test_runbook_can_disable_auto_upstream_linking() -> None:
    runbook = run_json(
        "runbook",
        "--priority",
        "P0",
        "--out-dir-root",
        "/tmp/collectorx-out",
        "--no-auto-link-upstream",
        "--json",
    )
    assert runbook["auto_upstream_links"] == []
    assert "email-research" in stage_ids(runbook, "needs_upstream_lake")
    assert runbook["summary"]["by_stage"]["ready_lenses"] == 0


def test_batch_manifest_renders_executable_p0_steps() -> None:
    manifest = run_json("batch-manifest", "--priority", "P0", "--out-dir-root", "/tmp/collectorx-out", "--json")
    assert manifest["schema"] == "collectorx.finclaw_batch_manifest.v1"
    assert manifest["summary"]["ready_steps"] == 6
    assert manifest["summary"]["blocked_steps"] == 6
    assert manifest["summary"]["by_stage"]["ready_collectors"] == 4
    assert manifest["summary"]["by_stage"]["ready_lenses"] == 2
    assert [step["id"] for step in manifest["ready_steps"]] == [
        "eastmoney-portfolio",
        "ths-portfolio",
        "wechat",
        "email",
        "wechat-investment-dialogue",
        "email-research",
    ]
    email_lens = next(step for step in manifest["ready_steps"] if step["id"] == "email-research")
    assert email_lens["stage"] == "ready_lenses"
    assert email_lens["depends_on"] == ["email"]
    assert email_lens["input_events_jsonl"] == "/tmp/collectorx-out/email/lake/email/events.jsonl"
    assert email_lens["output_dir"] == "/tmp/collectorx-out/email-research"
    assert email_lens["lake_events_jsonl"] == "/tmp/collectorx-out/email-research/lake/email-research/events.jsonl"
    assert email_lens["post_run_validation"]["argv"] == [
        "python3",
        "tools/validate_collector_package.py",
        "/tmp/collectorx-out/email-research",
        "--collector",
        "email-research",
        "--require-evidence",
        "--json",
    ]
    blocked_ids = {step["id"] for step in manifest["blocked_steps"]}
    assert "research-documents" in blocked_ids
    assert "china-wealth-assets" in blocked_ids


def test_batch_manifest_can_disable_auto_upstream_linking() -> None:
    manifest = run_json(
        "batch-manifest",
        "--priority",
        "P0",
        "--out-dir-root",
        "/tmp/collectorx-out",
        "--no-auto-link-upstream",
        "--json",
    )
    assert manifest["auto_upstream_links"] == []
    assert manifest["summary"]["ready_steps"] == 4
    assert manifest["summary"]["blocked_steps"] == 8
    blocked_by_id = {step["id"]: step for step in manifest["blocked_steps"]}
    assert blocked_by_id["email-research"]["next_action"] == "wait_for_upstream_lake"
    assert blocked_by_id["email-research"]["requires_upstream"] == ["email"]


def test_runbook_require_all_ready_fails_when_any_entry_is_blocked() -> None:
    proc = run_proc("runbook", "--priority", "P0", "--out-dir-root", "/tmp/collectorx-out", "--json", "--require-all-ready")
    assert proc.returncode == 2
    runbook = json.loads(proc.stdout)
    assert runbook["not_ready"] > 0


def test_closeout_handoff_matches_catalog_counts_and_ids() -> None:
    catalog = json.loads((ROOT / "collectors" / "finclaw-investor-catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    closeout = (ROOT / "docs" / "investor-collector-closeout.md").read_text(encoding="utf-8")

    assert f"当前仓库已经形成 {len(entries)} 个 FinClaw catalog 条目" in closeout
    readiness_counts = Counter(entry["readiness"] for entry in entries)
    for readiness, count in readiness_counts.items():
        assert f"| `{readiness}` | {count} |" in closeout

    priority_counts = Counter(entry["priority"] for entry in entries)
    for priority, count in priority_counts.items():
        assert f"| {priority} | {count} |" in closeout

    for entry in entries:
        assert f"`{entry['id']}`" in closeout


def test_final_handoff_checklist_matches_closeout_report() -> None:
    report = run_json("closeout", "--json")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    closeout = (ROOT / "docs" / "investor-collector-closeout.md").read_text(encoding="utf-8")
    productization = (ROOT / "docs" / "finclaw-investor-collector-productization.md").read_text(encoding="utf-8")
    production_readiness = (ROOT / "docs" / "production-readiness.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "investor-collector-productization-roadmap.md").read_text(encoding="utf-8")
    handoff = (ROOT / "docs" / "final-handoff-checklist.md").read_text(encoding="utf-8")

    assert "docs/final-handoff-checklist.md" in readme
    assert "docs/final-handoff-checklist.md" in closeout
    assert "docs/final-handoff-checklist.md" in productization
    assert "docs/final-handoff-checklist.md" in production_readiness
    assert "docs/final-handoff-checklist.md" in roadmap
    assert f"CollectorX currently exposes {report['total']} FinClaw investor catalog entries." in handoff

    for priority, count in report["summary"]["by_priority"].items():
        assert f"| {priority} | {count} |" in handoff
    for category, count in report["summary"]["by_category"].items():
        assert f"| {category} | {count} |" in handoff
    for readiness, count in report["summary"]["by_readiness"].items():
        assert f"| `{readiness}` | {count} |" in handoff
    for launch_tier, count in report["summary"]["by_launch_tier"].items():
        assert f"| `{launch_tier}` | {count} |" in handoff
    for scope, count in report["summary"]["by_remaining_validation_scope"].items():
        assert f"| `{scope}` | {count} |" in handoff

    for item in report["items"]:
        expected_row = (
            f"| `{item['id']}` | {item['priority']} | {item['category']} | "
            f"`{item['readiness']}` | `{item['launch_tier']}` | "
            f"`{item['remaining_validation_scope']}` |"
        )
        assert expected_row in handoff

    assert "`eastmoney-portfolio`" in handoff
    assert "`ths-portfolio`, `qq`" in handoff
    assert "production-candidate` as full production done" in handoff
    assert "The next phase is real validation, not more collector expansion." in handoff


def main() -> int:
    test_list_includes_catalog_and_contract_fields()
    test_show_lens_includes_upstream_contract()
    test_plan_replaces_placeholders()
    test_plan_argv_preserves_paths_with_spaces_without_shell_quotes()
    test_plan_reports_missing_placeholders_and_require_ready_fails()
    test_require_ready_allows_ready_command_plan()
    test_generic_package_validation_does_not_require_evidence()
    test_soulmirror_plan_is_not_plain_command()
    test_lens_plan_waits_for_upstream_lake()
    test_require_ready_rejects_soulmirror_plan()
    test_doctor_reports_batch_readiness_summary()
    test_doctor_filters_priority()
    test_doctor_require_all_ready_fails_when_any_entry_is_blocked()
    test_closeout_report_tracks_product_tiers_and_real_validation_gaps()
    test_runbook_groups_p0_entries_by_product_stage()
    test_runbook_respects_explicit_lens_input_over_auto_link()
    test_runbook_can_disable_auto_upstream_linking()
    test_batch_manifest_renders_executable_p0_steps()
    test_batch_manifest_can_disable_auto_upstream_linking()
    test_runbook_require_all_ready_fails_when_any_entry_is_blocked()
    test_closeout_handoff_matches_catalog_counts_and_ids()
    test_final_handoff_checklist_matches_closeout_report()
    print("finclaw catalog tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
