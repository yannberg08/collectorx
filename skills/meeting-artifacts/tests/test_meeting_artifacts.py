#!/usr/bin/env python3
"""Tests for meeting-artifacts collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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


def test_collect_platform_exports_and_sanitizes_raw() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dingtalk = root / "dingtalk-meeting.json"
        wecom = root / "wecom-meeting.csv"
        tencent = root / "腾讯会议纪要.html"
        out = root / "out"
        dingtalk.write_text(
            json.dumps(
                {
                    "meetings": [
                        {
                            "platform": "钉钉",
                            "title": "投委会讨论",
                            "summary": "讨论仓位、估值和风险控制。",
                            "participants": [{"name": "研究员A"}, {"name": "基金经理B"}],
                            "meeting_url": "https://dingtalk.example/meeting",
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
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "meeting-artifacts" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 3
        assert {event["data"]["platform"] for event in events} == {"dingtalk", "wecom", "tencent-meeting"}
        assert any(event["data"].get("meeting_url") == "https://meeting.tencent.com/test" for event in events)
        assert any("研究员C" in event["data"].get("participants", []) for event in events)
        assert any("分析师A" in event["data"].get("participants", []) for event in events)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_counts"]["tencent-meeting"] == 1


if __name__ == "__main__":
    test_collect_minutes_and_transcript_events()
    test_collect_platform_exports_and_sanitizes_raw()
    print("meeting-artifacts tests passed.")
