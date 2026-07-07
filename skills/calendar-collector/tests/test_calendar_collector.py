#!/usr/bin/env python3
"""Tests for calendar-collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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
        assert event["data"]["start"] == "2026-07-08T09:30:00+08:00"
        assert event["data"]["meeting_url"] == "https://meeting.tencent.com/test"
        assert event["data"]["attendees"][0]["name"] == "研究员"
        assert event["wiki_targets"] == ["internal.calendar.events"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_calendar"] is False


def test_collect_json_and_csv_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "events.json"
        csv_path = root / "events.csv"
        out = root / "out"
        json_path.write_text(
            json.dumps({"events": [{"title": "复盘提醒", "start": "2026-07-08T20:00:00+08:00", "token": "must-not-leak"}]}, ensure_ascii=False),
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


def test_collect_without_input_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        event = json.loads((out / "lake" / "calendar" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["data"]["gap"] == "calendar_authorized_input_missing"


if __name__ == "__main__":
    test_collect_ics_event()
    test_collect_json_and_csv_events()
    test_collect_without_input_gap()
    print("calendar-collector tests passed.")
