#!/usr/bin/env python3
"""Tests for meeting-artifacts collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "meeting_artifacts.py"


def test_collect_minutes_and_transcript_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        minutes = root / "roadshow.md"
        transcript = root / "meeting.vtt"
        out = root / "out"
        minutes.write_text("# 半导体公司路演纪要\n参会人：研究员A，基金经理B\n讨论财报、估值和风险点。\n", encoding="utf-8")
        transcript.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n今天讨论买入框架。\n", encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(root),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T01:20:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "meeting-artifacts" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 2
        assert {event["data"]["artifact_type"] for event in events} == {"minutes", "transcript"}
        assert all(event["collector"] == "meeting-artifacts" for event in events)
        assert all(event["kind"] == "note" for event in events)
        assert all(event["wiki_targets"] == ["internal.collaboration.meetings"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_meeting_minutes"] is False
        assert manifest["platform_coverage"]["observed_platforms"] == ["local-file"]
        assert manifest["collection_readiness"]["platform_coverage_status"] == "partial_expected_platforms_observed"
        assert manifest["field_coverage"]["field_counts"]["artifact_type"] == 2
        assert manifest["meeting_surface_summary"]["events_with_text"] == 2
        assert manifest["meeting_surface_summary"]["events_with_participants"] == 1
        assert manifest["evidence_policy"]["required_lens"] == "meeting-minutes"


def test_collect_platform_exports_and_sanitizes_raw() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dingtalk = root / "dingtalk-meeting.json"
        wecom = root / "wecom-meeting.csv"
        tencent = root / "腾讯会议纪要.html"
        feishu_zip = root / "feishu-meeting.zip"
        out = root / "out"
        dingtalk.write_text(
            json.dumps(
                {
                    "meetings": [
                        {
                            "platform": "钉钉",
                            "title": "投委会讨论",
                            "summary": "讨论仓位、估值和风险控制。",
                            "start_time": "2026-07-08T09:00:00+08:00",
                            "end_time": "2026-07-08T10:00:00+08:00",
                            "duration": "60m",
                            "participants": [{"name": "研究员A"}, {"name": "基金经理B"}],
                            "meeting_url": "https://dingtalk.example/meeting",
                            "attachments": [{"path": "recording-ref.mp3"}],
                            "token": "must-not-leak",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        wecom.write_text("平台,会议主题,内容,参会人,会议链接\n企业微信,调研纪要,讨论财报和买入框架,研究员A、研究员C,https://work.weixin.qq.com/meeting\n", encoding="utf-8")
        tencent.write_text("<html><head><title>腾讯会议路演</title></head><body>参会人：分析师A，投资经理B<br>讨论估值和现金流 https://meeting.tencent.com/test</body></html>", encoding="utf-8")
        with zipfile.ZipFile(feishu_zip, "w") as archive:
            archive.writestr(
                "feishu/roadshow.md",
                "# 飞书路演纪要\n参会人：研究员D，基金经理E\n讨论行业空间和竞争格局。\n",
            )
            archive.writestr("../unsafe.md", "# 不应读取\n")
            archive.writestr("..\\windows-traversal.md", "# 不应读取\n")
            archive.writestr("C:\\unsafe.md", "# 不应读取\n")
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "meeting-artifacts" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 4
        assert {event["data"]["platform"] for event in events} == {"feishu", "dingtalk", "wecom", "tencent-meeting"}
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("windows-traversal" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("C:/unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        feishu_event = next(event for event in events if event["data"]["platform"] == "feishu")
        assert feishu_event["raw_ref"]["source_archive"] == str(feishu_zip)
        assert feishu_event["raw_ref"]["archive_member"] == "feishu/roadshow.md"
        assert any(event["data"].get("meeting_url") == "https://meeting.tencent.com/test" for event in events)
        assert any("研究员C" in event["data"].get("participants", []) for event in events)
        assert any("分析师A" in event["data"].get("participants", []) for event in events)
        assert any(event["data"].get("attachment_ref_count") == 1 for event in events)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_counts"]["tencent-meeting"] == 1
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["feishu", "dingtalk", "wecom", "tencent-meeting"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == []
        assert manifest["collection_readiness"]["platform_coverage_status"] == "all_expected_platforms_observed"
        assert manifest["platform_coverage"]["real_account_validation"] is False
        assert manifest["field_coverage"]["field_counts"]["platform"] == 4
        assert manifest["meeting_surface_summary"]["events_with_attachments"] == 1
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False


if __name__ == "__main__":
    test_collect_minutes_and_transcript_events()
    test_collect_platform_exports_and_sanitizes_raw()
    print("meeting-artifacts tests passed.")
