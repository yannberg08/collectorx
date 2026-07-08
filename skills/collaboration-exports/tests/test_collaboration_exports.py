#!/usr/bin/env python3
"""Tests for collaboration-exports collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collaboration_exports.py"


def read_events(out: Path, collector: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (out / "lake" / collector / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_collect_dingtalk_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "dingtalk-export.json"
        html = root / "dingtalk-minutes.html"
        zip_path = root / "dingtalk-package.zip"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "platform": "钉钉",
                    "messages": [
                        {
                            "chat": "投研讨论群",
                            "sender": "研究员A",
                            "time": "2026-07-08T09:00:00+08:00",
                            "content": "讨论半导体订单和估值。",
                            "auth": {"token": "must-not-leak"},
                        }
                    ],
                    "files": [{"file_name": "调研纪要.pdf", "sender": "研究员B", "link": "https://dingtalk.example/file"}],
                    "contacts": [{"name": "基金经理C", "department": "投资部"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        html.write_text(
            "<html><head><title>钉钉会议纪要</title></head><body>参会人：研究员A，基金经理C https://dingtalk.example/meeting</body></html>",
            encoding="utf-8",
        )
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("dingtalk/roadshow.md", "# 钉钉路演纪要\n参会人：研究员D，基金经理E\n讨论估值。\n")
            archive.writestr("../unsafe.md", "# 不应读取\n")
            archive.writestr("..\\windows-traversal.md", "# 不应读取\n")
            archive.writestr("C:\\unsafe.md", "# 不应读取\n")
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--platform",
                "dingtalk",
                "--input",
                str(root),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out, "dingtalk")
        assert len(events) == 5
        assert {event["collector"] for event in events} == {"dingtalk"}
        assert {event["data"]["record_kind"] for event in events} == {"contact", "file", "meeting", "message"}
        assert {event["kind"] for event in events} == {"calendar", "file", "message", "profile"}
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("windows-traversal" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("C:/unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        zip_event = next(event for event in events if event["raw_ref"].get("archive_member") == "dingtalk/roadshow.md")
        assert zip_event["raw_ref"]["source_archive"] == str(zip_path)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        message = next(event for event in events if event["data"]["record_kind"] == "message")
        assert message["wiki_targets"] == ["internal.collaboration.messages"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collector"] == "dingtalk"
        assert manifest["collection_readiness"]["can_claim_investment_collaboration"] is False
        assert manifest["field_coverage"]["field_counts"]["platform"] == 5
        assert manifest["collaboration_surface_summary"]["meeting_event_count"] == 2
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["extension_counts"] == {".html": 1, ".json": 1, ".zip": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 5
        assert manifest["source_audit"]["emitted_event_count"] == 5
        assert len(manifest["source_audit"]["path_results"]) == 3
        assert manifest["source_audit"]["archive_count"] == 1


def test_collect_wecom_csv_and_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "wecom-messages.csv"
        out = root / "out"
        gap_out = root / "gap"
        csv_path.write_text(
            "平台,类型,会话,发送人,内容,时间,会议链接\n"
            "企业微信,message,调研群,投资经理A,明天讨论现金流模型,2026-07-08T10:00:00+08:00,\n"
            "企业微信,meeting,投委会,秘书,会议纪要已生成,2026-07-08T11:00:00+08:00,https://work.weixin.qq.com/meeting\n",
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--platform", "wecom", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out, "wecom")
        assert len(events) == 2
        assert {event["collector"] for event in events} == {"wecom"}
        assert {event["data"]["record_kind"] for event in events} == {"meeting", "message"}
        assert any(event["data"].get("meeting_url") == "https://work.weixin.qq.com/meeting" for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["field_coverage"]["field_counts"]["record_kind"] == 2
        assert manifest["collaboration_surface_summary"]["meeting_event_count"] == 1
        assert manifest["source_audit"]["input_count"] == 1
        assert manifest["source_audit"]["resolved_input_file_count"] == 1
        assert manifest["source_audit"]["extension_counts"] == {".csv": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 2
        assert manifest["source_audit"]["emitted_event_count"] == 2

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--platform", "wecom", "--out-dir", str(gap_out)],
            check=True,
            text=True,
            capture_output=True,
        )
        gap_events = read_events(gap_out, "wecom")
        assert len(gap_events) == 1
        assert gap_events[0]["data"]["record_kind"] == "collector_gap"
        gap_manifest = json.loads((gap_out / "manifest.json").read_text(encoding="utf-8"))
        assert gap_manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert gap_manifest["source_audit"]["input_count"] == 0
        assert gap_manifest["source_audit"]["resolved_input_file_count"] == 0
        assert gap_manifest["source_audit"]["parsed_record_count"] == 0
        assert gap_manifest["source_audit"]["emitted_event_count"] == 1


def test_collect_collaboration_scope_policy_filters_platform_chat_sender_and_keyword() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "dingtalk-export.json"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "messages": [
                        {
                            "platform": "钉钉",
                            "chat": "投研讨论群",
                            "sender": "研究员A",
                            "time": "2026-07-08T09:00:00+08:00",
                            "content": "讨论半导体订单和估值。",
                        },
                        {
                            "platform": "钉钉",
                            "chat": "投研讨论群",
                            "sender": "研究员A",
                            "time": "2026-07-08T09:05:00+08:00",
                            "content": "买菜安排。",
                        },
                        {
                            "platform": "企业微信",
                            "chat": "投研讨论群",
                            "sender": "研究员A",
                            "time": "2026-07-08T09:10:00+08:00",
                            "content": "讨论半导体仓位。",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--platform",
                "dingtalk",
                "--input",
                str(package),
                "--out-dir",
                str(out),
                "--allow-source-platform",
                "dingtalk",
                "--allow-chat",
                "投研讨论群",
                "--allow-sender",
                "研究员A",
                "--deny-keyword",
                "买菜",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out, "dingtalk")
        assert len(events) == 1
        assert events[0]["data"]["content_preview"] == "讨论半导体订单和估值。"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        policy = manifest["source_audit"]["collaboration_scope_policy"]
        assert manifest["source_audit"]["candidate_record_count"] == 3
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert policy["enabled"] is True
        assert policy["filtered_record_count"] == 2
        assert policy["filter_reason_counts"] == {"keyword_denied": 1, "source_platform_not_allowed": 1}
        assert manifest["source_audit"]["collaboration_scope_policy_filtered_all"] is False
        assert manifest["source_audit"]["path_results"][0]["scope_policy_filtered_record_count"] == 2


def test_collect_collaboration_scope_policy_filtered_all_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "dingtalk-export.json"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "messages": [
                        {
                            "platform": "钉钉",
                            "chat": "投研讨论群",
                            "sender": "研究员A",
                            "content": "讨论半导体订单。",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--platform",
                "dingtalk",
                "--input",
                str(package),
                "--out-dir",
                str(out),
                "--allow-chat",
                "不存在的群",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events_path = out / "lake" / "dingtalk" / "events.jsonl"
        assert events_path.read_text(encoding="utf-8") == ""
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 0
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "scope_policy_excluded_all"
        assert manifest["source_audit"]["collaboration_scope_policy"]["filter_reason_counts"] == {"chat_not_allowed": 1}
        assert manifest["source_audit"]["collaboration_scope_policy_filtered_all"] is True


if __name__ == "__main__":
    test_collect_dingtalk_package()
    test_collect_wecom_csv_and_gap()
    test_collect_collaboration_scope_policy_filters_platform_chat_sender_and_keyword()
    test_collect_collaboration_scope_policy_filtered_all_status()
    print("collaboration-exports tests passed.")
