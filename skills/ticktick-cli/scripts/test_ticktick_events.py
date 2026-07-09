#!/usr/bin/env python3
"""Tests for TickTick CollectorX event conversion."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "ticktick_events.py"


def read_events(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "exports" / "ticktick" / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def test_ticktick_json_to_task_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "tasks.json"
        out = root / "out"
        source.write_text(
            json.dumps(
                [
                    {
                        "id": "task-1",
                        "projectId": "project-1",
                        "projectName": "投资研究",
                        "title": "复盘贵州茅台财报",
                        "content": "看现金流和估值",
                        "startDate": "2026-07-08T09:00:00+08:00",
                        "dueDate": "2026-07-09T10:00:00+08:00",
                        "timeZone": "Asia/Shanghai",
                        "isAllDay": False,
                        "status": 0,
                        "priority": 3,
                        "repeatFlag": "RRULE:FREQ=WEEKLY;BYDAY=TH",
                        "reminders": ["2026-07-09T09:30:00+08:00"],
                        "items": [
                            {"id": "item-1", "title": "读现金流量表", "status": 1, "completedTime": "2026-07-08T10:00:00+08:00"},
                            {"id": "item-2", "title": "更新估值假设", "status": 0},
                        ],
                        "tags": ["投资"],
                        "token": "must-not-leak",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(source), "--out-dir", str(out), "--collected-at", "2026-07-08T01:10:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        event = events[0]
        assert event["schema"] == "collectorx.event.v1"
        assert event["collector"] == "ticktick"
        assert event["kind"] == "task"
        assert event["data"]["source_app"] == "ticktick"
        assert event["data"]["title"] == "复盘贵州茅台财报"
        assert event["data"]["is_completed"] is False
        assert event["data"]["is_overdue"] is False
        assert event["data"]["content_length"] == len("看现金流和估值")
        assert event["data"]["recurrence"] == "RRULE:FREQ=WEEKLY;BYDAY=TH"
        assert event["data"]["recurrence_frequency"] == "weekly"
        assert event["data"]["reminders"] == ["2026-07-09T09:30:00+08:00"]
        assert event["data"]["time_zone"] == "Asia/Shanghai"
        assert event["data"]["is_all_day"] is False
        assert event["data"]["has_time_range"] is True
        assert event["data"]["time_order_valid"] is True
        assert event["data"]["duration_minutes"] == 1500
        assert event["data"]["checklist_total"] == 2
        assert event["data"]["checklist_completed"] == 1
        assert event["data"]["checklist_pending"] == 1
        assert event["data"]["checklist_completion_rate"] == 0.5
        assert event["data"]["checklist_items"][0]["title"] == "读现金流量表"
        assert event["data"]["checklist_items"][0]["is_completed"] is True
        assert "must-not-leak" not in json.dumps(event, ensure_ascii=False)
        assert event["wiki_targets"] == ["internal.productivity.tasks"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["task_event_count"] == 1
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_claim_investment_tasks"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["ticktick"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == ["dida365"]
        assert manifest["field_coverage"]["field_counts"]["recurrence"] == 1
        assert manifest["field_coverage"]["field_counts"]["recurrence_frequency"] == 1
        assert manifest["field_coverage"]["field_counts"]["reminders"] == 1
        assert manifest["field_coverage"]["field_counts"]["checklist_total"] == 1
        assert manifest["field_coverage"]["field_counts"]["checklist_completed"] == 1
        assert manifest["field_coverage"]["field_counts"]["checklist_completion_rate"] == 1
        assert manifest["time_status_summary"]["pending_task_count"] == 1
        assert manifest["time_status_summary"]["events_with_due"] == 1
        assert manifest["time_status_summary"]["overdue_task_count"] == 0
        assert manifest["time_status_summary"]["events_with_time_zone"] == 1
        assert manifest["time_status_summary"]["events_with_duration_minutes"] == 1
        assert manifest["time_status_summary"]["events_with_invalid_time_range"] == 0
        assert manifest["time_status_summary"]["recurrence_frequency_counts"] == {"weekly": 1}
        assert manifest["time_status_summary"]["tasks_with_checklist"] == 1
        assert manifest["time_status_summary"]["checklist_item_total"] == 2
        assert manifest["time_status_summary"]["checklist_item_completed_count"] == 1
        assert manifest["time_status_summary"]["checklist_item_pending_count"] == 1
        assert manifest["time_status_summary"]["average_checklist_completion_rate"] == 0.5
        assert manifest["source_audit"]["input_count"] == 1
        assert manifest["source_audit"]["resolved_input_file_count"] == 1
        assert manifest["source_audit"]["extension_counts"] == {".json": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 1
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert manifest["evidence_policy"]["required_lens"] == "task-calendar-investor"


def test_ticktick_zip_dida_export_and_unsafe_member_skip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "dida365-export.zip"
        out = root / "out"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr(
                "dida365/tasks.json",
                json.dumps(
                    {
                        "tasks": [
                            {
                                "source": "滴答清单",
                                "id": "task-2",
                                "projectName": "交易计划",
                                "title": "检查仓位上限",
                                "dueDate": "2026-07-10T09:00:00+08:00",
                                "completedTime": "2026-07-10T10:00:00+08:00",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"title": "不应读取"}], ensure_ascii=False))
            archive.writestr("..\\windows-traversal.json", json.dumps([{"title": "不应读取"}], ensure_ascii=False))
            archive.writestr("C:\\unsafe.json", json.dumps([{"title": "不应读取"}], ensure_ascii=False))
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(source), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        assert events[0]["data"]["source_app"] == "dida365"
        assert events[0]["data"]["is_completed"] is True
        assert events[0]["raw_ref"]["source_archive"] == str(source)
        assert events[0]["raw_ref"]["archive_member"] == "dida365/tasks.json"
        assert "../unsafe" not in events[0]["raw_ref"]["path"]
        assert "windows-traversal" not in events[0]["raw_ref"]["path"]
        assert "C:/unsafe" not in events[0]["raw_ref"]["path"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["dida365"]
        assert manifest["collection_readiness"]["platform_coverage_status"] == "partial_expected_platforms_observed"
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["extension_counts"] == {".zip": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 1
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert len(manifest["source_audit"]["path_results"]) == 1
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["time_status_summary"]["completed_task_count"] == 1


def test_ticktick_scope_policy_filters_source_project_tag_and_keyword() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "tasks.json"
        out = root / "out"
        source.write_text(
            json.dumps(
                [
                    {
                        "source_app": "ticktick",
                        "id": "task-invest",
                        "projectName": "投资研究",
                        "title": "复盘贵州茅台财报",
                        "content": "检查现金流和估值假设",
                        "tags": ["投资"],
                    },
                    {
                        "source_app": "ticktick",
                        "id": "task-life",
                        "projectName": "生活清单",
                        "title": "周末买菜",
                        "content": "买菜和家务",
                        "tags": ["生活"],
                    },
                    {
                        "source": "滴答清单",
                        "id": "task-dida",
                        "projectName": "投资研究",
                        "title": "Dida 估值提醒",
                        "tags": ["投资"],
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(source),
                "--out-dir",
                str(out),
                "--allow-source-app",
                "ticktick",
                "--allow-project",
                "投资研究",
                "--allow-tag",
                "投资",
                "--deny-keyword",
                "买菜",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "exports" / "ticktick" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["data"]["title"] == "复盘贵州茅台财报"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["source_audit"]
        policy = audit["task_scope_policy"]
        assert manifest["collection_readiness"]["status"] == "events_collected"
        assert audit["candidate_record_count"] == 3
        assert audit["parsed_record_count"] == 3
        assert audit["emitted_event_count"] == 1
        assert policy["enabled"] is True
        assert policy["allow_source_apps"] == ["ticktick"]
        assert policy["allow_projects"] == ["投资研究"]
        assert policy["allow_tags"] == ["投资"]
        assert policy["deny_keywords"] == ["买菜"]
        assert policy["filtered_record_count"] == 2
        assert policy["filter_reason_counts"] == {"keyword_denied": 1, "source_app_not_allowed": 1}
        assert policy["policy_does_not_assert_investment_relevance"] is True
        assert audit["path_results"][0]["scope_policy_filtered_record_count"] == 2
        assert audit["task_scope_policy_filtered_all"] is False


def test_ticktick_scope_policy_filtered_all_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "tasks.json"
        out = root / "out"
        source.write_text(
            json.dumps(
                [{"source_app": "ticktick", "projectName": "投资研究", "title": "复盘任务", "tags": ["投资"]}],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(source),
                "--out-dir",
                str(out),
                "--allow-tag",
                "不存在的标签",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        gap = events[0]
        assert gap["schema"] == "collectorx.event.v1"
        assert gap["collector"] == "ticktick"
        assert gap["kind"] == "profile"
        assert gap["time"]
        assert gap["data"]["subtype"] == "collector_gap"
        assert gap["data"]["action_type"] == "collector_gap"
        assert gap["data"]["gap"] == "task_scope_policy_filtered_all"
        assert gap["data"]["status"] == "scope_policy_filtered_all"
        assert gap["data"]["profile_type"] == "task_collection_gap"
        assert gap["data"]["candidate_record_count"] == 1
        assert gap["data"]["task_event_count"] == 0
        assert gap["data"]["scope_policy_filtered_record_count"] == 1
        assert gap["data"]["scope_policy_filter_reason_counts"] == {"tag_not_allowed": 1}
        assert gap["data"]["policy_is_user_authorization_scope"] is True
        assert gap["data"]["investment_task_fact_claimed"] is False
        assert gap["data"]["complete_task_list_claimed"] is False
        assert gap["raw_ref"] == {
            "preflight": True,
            "reason": "task_scope_policy_filtered_all",
            "scope_policy_enabled": True,
        }
        assert "collection_gap" in gap["privacy"]["contains"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["task_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        audit = manifest["source_audit"]
        assert audit["candidate_record_count"] == 1
        assert audit["emitted_event_count"] == 1
        assert audit["task_scope_policy_filtered_all"] is True
        assert audit["task_scope_policy"]["filtered_record_count"] == 1
        assert audit["task_scope_policy"]["filter_reason_counts"] == {"tag_not_allowed": 1}


def test_ticktick_without_input_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        events = read_events(out)
        assert len(events) == 1
        assert events[0]["kind"] == "profile"
        assert events[0]["time"]
        assert events[0]["data"]["gap"] == "ticktick_authorized_input_missing"
        assert events[0]["data"]["status"] == "needs_ticktick_authorized_input"
        assert events[0]["data"]["profile_type"] == "task_collection_gap"
        assert events[0]["data"]["candidate_record_count"] == 0
        assert events[0]["data"]["task_event_count"] == 0
        assert "collection_gap" in events[0]["privacy"]["contains"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["task_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["source_audit"]["input_count"] == 0
        assert manifest["source_audit"]["resolved_input_file_count"] == 0
        assert manifest["source_audit"]["parsed_record_count"] == 0
        assert manifest["source_audit"]["emitted_event_count"] == 1


if __name__ == "__main__":
    test_ticktick_json_to_task_events()
    test_ticktick_zip_dida_export_and_unsafe_member_skip()
    test_ticktick_scope_policy_filters_source_project_tag_and_keyword()
    test_ticktick_scope_policy_filtered_all_status()
    test_ticktick_without_input_gap()
    print("ticktick event tests passed.")
