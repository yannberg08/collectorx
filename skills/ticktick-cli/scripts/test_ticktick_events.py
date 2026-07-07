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
                        "status": 0,
                        "priority": 3,
                        "repeatFlag": "weekly",
                        "reminders": ["2026-07-09T09:30:00+08:00"],
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
        events = [json.loads(line) for line in (out / "lake" / "ticktick" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
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
        assert event["data"]["recurrence"] == "weekly"
        assert event["data"]["reminders"] == ["2026-07-09T09:30:00+08:00"]
        assert "must-not-leak" not in json.dumps(event, ensure_ascii=False)
        assert event["wiki_targets"] == ["internal.productivity.tasks"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_tasks"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["ticktick"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == ["dida365"]
        assert manifest["field_coverage"]["field_counts"]["recurrence"] == 1
        assert manifest["field_coverage"]["field_counts"]["reminders"] == 1
        assert manifest["time_status_summary"]["pending_task_count"] == 1
        assert manifest["time_status_summary"]["events_with_due"] == 1
        assert manifest["time_status_summary"]["overdue_task_count"] == 0
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
        events = [json.loads(line) for line in (out / "lake" / "ticktick" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
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
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["time_status_summary"]["completed_task_count"] == 1


if __name__ == "__main__":
    test_ticktick_json_to_task_events()
    test_ticktick_zip_dida_export_and_unsafe_member_skip()
    print("ticktick event tests passed.")
