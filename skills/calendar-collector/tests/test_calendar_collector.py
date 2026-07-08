#!/usr/bin/env python3
"""Tests for calendar-collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "calendar_query.py"


def test_collect_ics_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ics = root / "calendar.ics"
        out = root / "out"
        ics.write_text(
            "\n".join(
                [
                    "BEGIN:VCALENDAR",
                    "BEGIN:VEVENT",
                    "UID:event-1",
                    "SUMMARY:财报电话会",
                    "DTSTART;TZID=Asia/Shanghai:20260708T093000",
                    "DTEND;TZID=Asia/Shanghai:20260708T103000",
                    "DESCRIPTION:跟踪贵州茅台二季度财报",
                    "LOCATION:腾讯会议",
                    "URL:https://meeting.tencent.com/test",
                    "ATTENDEE;CN=研究员;ROLE=REQ-PARTICIPANT:mailto:analyst@example.com",
                    "RRULE:FREQ=WEEKLY;COUNT=2",
                    "BEGIN:VALARM",
                    "TRIGGER:-PT30M",
                    "END:VALARM",
                    "END:VEVENT",
                    "END:VCALENDAR",
                ]
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(ics), "--out-dir", str(out), "--collected-at", "2026-07-08T09:00:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        event = json.loads((out / "lake" / "calendar" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["schema"] == "collectorx.event.v1"
        assert event["collector"] == "calendar"
        assert event["kind"] == "calendar"
        assert event["data"]["title"] == "财报电话会"
        assert event["data"]["source_platform"] == "ics_export"
        assert event["data"]["start"] == "2026-07-08T09:30:00+08:00"
        assert event["data"]["end"] == "2026-07-08T10:30:00+08:00"
        assert event["data"]["has_time_range"] is True
        assert event["data"]["time_order_valid"] is True
        assert event["data"]["duration_minutes"] == 60
        assert event["data"]["is_multi_day"] is False
        assert event["data"]["meeting_url"] == "https://meeting.tencent.com/test"
        assert event["data"]["attendees"][0]["name"] == "研究员"
        assert event["data"]["has_description"] is True
        assert event["data"]["description_length"] == len("跟踪贵州茅台二季度财报")
        assert event["wiki_targets"] == ["internal.calendar.events"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_calendar"] is False
        assert manifest["platform_coverage"]["observed_platforms"] == ["ics_export"]
        assert manifest["collection_readiness"]["platform_coverage_status"] == "partial_expected_platforms_observed"
        assert manifest["field_coverage"]["field_counts"]["meeting_url"] == 1
        assert manifest["field_coverage"]["field_counts"]["attendees"] == 1
        assert manifest["time_surface_summary"]["events_with_recurrence"] == 1
        assert manifest["time_surface_summary"]["events_with_reminders"] == 1
        assert manifest["time_surface_summary"]["events_with_time_range"] == 1
        assert manifest["time_surface_summary"]["events_with_duration_minutes"] == 1
        assert manifest["time_surface_summary"]["average_duration_minutes"] == 60
        assert manifest["time_surface_summary"]["time_conflict_summary"]["conflict_pair_count"] == 0
        assert manifest["source_audit"]["input_count"] == 1
        assert manifest["source_audit"]["resolved_input_file_count"] == 1
        assert manifest["source_audit"]["extension_counts"] == {".ics": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 1
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert manifest["evidence_policy"]["required_lens"] == "task-calendar-investor"


def test_collect_json_and_csv_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "events.json"
        csv_path = root / "outlook-events.csv"
        out = root / "out"
        json_path.write_text(
            json.dumps({"events": [{"source_platform": "Google Calendar", "title": "复盘提醒", "start": "2026-07-08T20:00:00+08:00", "token": "must-not-leak"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        csv_path.write_text("标题,开始时间,结束时间,地点\n行业会议,2026-07-09T10:00:00+08:00,2026-07-09T11:00:00+08:00,线上\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "calendar" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 2
        assert {event["data"]["title"] for event in events} == {"复盘提醒", "行业会议"}
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        assert all(target == "internal.calendar.events" for event in events for target in event["wiki_targets"])
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_coverage"]["source_platform_counts"] == {
            "google_calendar": 1,
            "outlook_calendar": 1,
        }


def test_collect_all_expected_calendar_platforms_and_zip_safety() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        exports.mkdir()
        (exports / "apple-calendar.ics").write_text(
            "\n".join(
                [
                    "BEGIN:VCALENDAR",
                    "BEGIN:VEVENT",
                    "UID:apple-1",
                    "SUMMARY:苹果日历复盘",
                    "DTSTART:20260708T090000",
                    "END:VEVENT",
                    "END:VCALENDAR",
                ]
            ),
            encoding="utf-8",
        )
        (exports / "google.json").write_text(
            json.dumps({"events": [{"platform": "google", "title": "Google 财报提醒", "start": "2026-07-08T10:00:00+08:00"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (exports / "outlook.csv").write_text("title,start\nOutlook 投委会,2026-07-08T11:00:00+08:00\n", encoding="utf-8")
        (exports / "feishu.json").write_text(
            json.dumps({"events": [{"来源": "飞书", "title": "飞书路演", "start": "2026-07-08T12:00:00+08:00"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (exports / "dingtalk.json").write_text(
            json.dumps({"events": [{"platform": "钉钉", "title": "钉钉调研", "start": "2026-07-08T13:00:00+08:00"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (exports / "wecom.json").write_text(
            json.dumps({"events": [{"platform": "企业微信", "title": "企业微信复盘", "start": "2026-07-08T14:00:00+08:00"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        zip_path = exports / "tencent-meeting-calendar.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "tencent-meeting.ics",
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "UID:tencent-1",
                        "SUMMARY:腾讯会议纪要跟进",
                        "DTSTART:20260708T150000",
                        "END:VEVENT",
                        "END:VCALENDAR",
                    ]
                ),
            )
            archive.writestr("../unsafe.ics", "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:不应读取\nEND:VEVENT\nEND:VCALENDAR\n")
            archive.writestr("..\\windows-traversal.ics", "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:不应读取\nEND:VEVENT\nEND:VCALENDAR\n")
            archive.writestr("C:\\unsafe.ics", "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:不应读取\nEND:VEVENT\nEND:VCALENDAR\n")

        out = root / "out"
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(exports), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "calendar" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 7
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("windows-traversal" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("C:/unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        tencent_event = next(event for event in events if event["data"]["source_platform"] == "tencent_meeting_calendar")
        assert tencent_event["raw_ref"]["source_archive"] == str(zip_path)
        assert tencent_event["raw_ref"]["archive_member"] == "tencent-meeting.ics"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_coverage"]["observed_expected_platforms"] == [
            "apple_calendar",
            "google_calendar",
            "outlook_calendar",
            "feishu_calendar",
            "dingtalk_calendar",
            "wecom_calendar",
            "tencent_meeting_calendar",
        ]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == []
        assert manifest["collection_readiness"]["platform_coverage_status"] == "all_expected_platforms_observed"
        assert manifest["platform_coverage"]["real_account_validation"] is False
        assert manifest["field_coverage"]["field_counts"]["source_platform"] == 7
        assert manifest["time_surface_summary"]["events_with_start"] == 7
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["extension_counts"] == {".csv": 1, ".ics": 1, ".json": 4, ".zip": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 7
        assert manifest["source_audit"]["emitted_event_count"] == 7
        assert len(manifest["source_audit"]["path_results"]) == 7
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False


def test_collect_calendar_time_quality_and_conflict_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "investment-calendar.csv"
        out = root / "out"
        csv_path.write_text(
            "\n".join(
                [
                    "title,calendar_name,start,end,reminders,meeting_url",
                    "上午调研,投资日历,2026-07-08T09:00:00+08:00,2026-07-08T10:00:00+08:00,提前30分钟,https://meeting.example/a",
                    "并行投委会,投资日历,2026-07-08T09:30:00+08:00,2026-07-08T10:30:00+08:00,,",
                    "无效结束,投资日历,2026-07-08T11:00:00+08:00,2026-07-08T10:00:00+08:00,,",
                    "跨夜复盘,投资日历,2026-07-08T23:00:00+08:00,2026-07-09T00:30:00+08:00,,",
                ]
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(csv_path), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "calendar" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        by_title = {event["data"]["title"]: event for event in events}
        assert by_title["上午调研"]["data"]["duration_minutes"] == 60
        assert by_title["并行投委会"]["data"]["duration_minutes"] == 60
        assert by_title["无效结束"]["data"]["time_order_valid"] is False
        assert "duration_minutes" not in by_title["无效结束"]["data"]
        assert by_title["跨夜复盘"]["data"]["duration_minutes"] == 90
        assert by_title["跨夜复盘"]["data"]["is_multi_day"] is True
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        time_surface = manifest["time_surface_summary"]
        assert time_surface["events_with_time_range"] == 4
        assert time_surface["events_with_duration_minutes"] == 3
        assert time_surface["events_with_invalid_time_range"] == 1
        assert time_surface["multi_day_event_count"] == 1
        assert time_surface["min_duration_minutes"] == 60
        assert time_surface["max_duration_minutes"] == 90
        assert time_surface["average_duration_minutes"] == 70
        conflict = time_surface["time_conflict_summary"]
        assert conflict["checked_timed_event_count"] == 3
        assert conflict["conflict_pair_count"] == 1
        assert conflict["events_with_conflicts"] == 2
        assert len(conflict["sample_conflict_pairs"]) == 1


def test_collect_without_input_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        event = json.loads((out / "lake" / "calendar" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["data"]["gap"] == "calendar_authorized_input_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["source_audit"]["input_count"] == 0
        assert manifest["source_audit"]["resolved_input_file_count"] == 0
        assert manifest["source_audit"]["parsed_record_count"] == 0
        assert manifest["source_audit"]["emitted_event_count"] == 1


if __name__ == "__main__":
    test_collect_ics_event()
    test_collect_json_and_csv_events()
    test_collect_all_expected_calendar_platforms_and_zip_safety()
    test_collect_calendar_time_quality_and_conflict_summary()
    test_collect_without_input_gap()
    print("calendar-collector tests passed.")
