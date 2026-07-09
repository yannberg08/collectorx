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
REPO_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "scripts" / "meeting_artifacts.py"
PACKAGE_VALIDATOR = REPO_ROOT / "tools" / "validate_collector_package.py"


def read_events(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "lake" / "meeting-artifacts" / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def assert_package_valid(out: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(PACKAGE_VALIDATOR),
            str(out),
            "--collector",
            "meeting-artifacts",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def test_collect_minutes_and_transcript_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        minutes = root / "roadshow.md"
        transcript = root / "meeting.vtt"
        unsupported = root / "recording.mp4"
        missing = root / "missing.srt"
        out = root / "out"
        minutes.write_text(
            "# 半导体公司路演纪要\n"
            "参会人：研究员A，基金经理B\n"
            "决策点：暂缓买入，等待 600519 财报确认。\n"
            "行动项：研究员A 跟进现金流假设。\n"
            "风险点：估值偏高和回撤风险。\n",
            encoding="utf-8",
        )
        transcript.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n今天讨论买入框架。\n", encoding="utf-8")
        unsupported.write_bytes(b"not-collected")
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(root),
                "--input",
                str(missing),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T01:20:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 2
        assert {event["data"]["artifact_type"] for event in events} == {"minutes", "transcript"}
        assert all(event["collector"] == "meeting-artifacts" for event in events)
        assert all(event["kind"] == "note" for event in events)
        assert all(event["wiki_targets"] == ["internal.collaboration.meetings"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 2
        assert manifest["meeting_artifact_event_count"] == 2
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_claim_investment_meeting_minutes"] is False
        assert manifest["platform_coverage"]["observed_platforms"] == ["local-file"]
        assert manifest["collection_readiness"]["platform_coverage_status"] == "partial_expected_platforms_observed"
        assert manifest["field_coverage"]["field_counts"]["artifact_type"] == 2
        assert manifest["meeting_surface_summary"]["events_with_text"] == 2
        assert manifest["meeting_surface_summary"]["events_with_participants"] == 1
        assert manifest["meeting_surface_summary"]["events_with_participant_roles"] == 1
        assert manifest["meeting_surface_summary"]["participant_role_counts"] == {"analyst": 1, "portfolio_manager": 1}
        assert manifest["meeting_surface_summary"]["events_with_action_items"] == 1
        assert manifest["meeting_surface_summary"]["events_with_decision_points"] == 1
        assert manifest["meeting_surface_summary"]["events_with_risk_items"] == 1
        assert manifest["meeting_surface_summary"]["events_with_mentioned_symbols"] == 1
        assert manifest["source_audit"]["input_count"] == 2
        assert manifest["source_audit"]["resolved_input_file_count"] == 2
        assert manifest["source_audit"]["input_missing_count"] == 1
        assert manifest["source_audit"]["skipped_file_count"] == 1
        assert manifest["source_audit"]["skipped_reason_counts"] == {"unsupported_extension": 1}
        assert manifest["source_audit"]["skipped_extension_counts"] == {".mp4": 1}
        assert manifest["source_audit"]["skipped_file_samples"][0]["path"] == str(unsupported)
        assert manifest["source_audit"]["extension_counts"] == {".md": 1, ".vtt": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 2
        assert manifest["source_audit"]["emitted_event_count"] == 2
        assert manifest["evidence_policy"]["required_lens"] == "meeting-minutes"
        assert_package_valid(out)


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
                            "summary": "决策点：加仓半导体；行动项：基金经理B 复核仓位；风险点：回撤扩大。",
                            "start_time": "2026-07-08T09:00:00+08:00",
                            "end_time": "2026-07-08T10:00:00+08:00",
                            "duration": "60m",
                            "participants": [{"name": "研究员A"}, {"name": "基金经理B"}],
                            "meeting_url": "https://dingtalk.example/meeting",
                            "attachments": [{"path": "recording-ref.mp3"}],
                            "recording_refs": [{"url": "https://dingtalk.example/recording/1"}],
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
        events = read_events(out)
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
        dingtalk_event = next(event for event in events if event["data"]["platform"] == "dingtalk")
        assert dingtalk_event["data"]["decision_point_count"] == 1
        assert dingtalk_event["data"]["action_item_count"] == 1
        assert dingtalk_event["data"]["risk_item_count"] == 1
        assert dingtalk_event["data"]["recording_ref_count"] == 1
        assert dingtalk_event["data"]["artifact_ref_summary"]["recording_body_collected"] is False
        assert dingtalk_event["data"]["participant_role_counts"] == {"analyst": 1, "portfolio_manager": 1}
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 4
        assert manifest["meeting_artifact_event_count"] == 4
        assert manifest["gap_event_count"] == 0
        assert manifest["platform_counts"]["tencent-meeting"] == 1
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["feishu", "dingtalk", "wecom", "tencent-meeting"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == []
        assert manifest["collection_readiness"]["platform_coverage_status"] == "all_expected_platforms_observed"
        assert manifest["platform_coverage"]["real_account_validation"] is False
        assert manifest["field_coverage"]["field_counts"]["platform"] == 4
        assert manifest["meeting_surface_summary"]["events_with_attachments"] == 1
        assert manifest["meeting_surface_summary"]["events_with_recording_refs"] == 1
        assert manifest["meeting_surface_summary"]["decision_point_count"] == 1
        assert manifest["meeting_surface_summary"]["action_item_count"] == 1
        assert manifest["meeting_surface_summary"]["risk_item_count"] == 1
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["extension_counts"] == {".csv": 1, ".html": 1, ".json": 1, ".zip": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 4
        assert manifest["source_audit"]["emitted_event_count"] == 4
        assert len(manifest["source_audit"]["path_results"]) == 4
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False
        assert_package_valid(out)


def test_collect_meeting_scope_policy_filters_platform_participant_and_keyword() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "meetings.json"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "meetings": [
                        {
                            "platform": "钉钉",
                            "title": "投委会讨论半导体",
                            "summary": "决策点：保留仓位；行动项：研究员A 更新模型。",
                            "participants": [{"name": "研究员A"}],
                        },
                        {
                            "platform": "钉钉",
                            "title": "行政例会",
                            "summary": "讨论牙医报销和团建安排。",
                            "participants": [{"name": "研究员A"}],
                        },
                        {
                            "platform": "企业微信",
                            "title": "投委会复盘",
                            "summary": "讨论半导体仓位。",
                            "participants": [{"name": "研究员A"}],
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
                "--input",
                str(package),
                "--out-dir",
                str(out),
                "--allow-source-platform",
                "dingtalk",
                "--allow-participant",
                "研究员A",
                "--deny-keyword",
                "牙医",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        assert events[0]["data"]["title"] == "投委会讨论半导体"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        policy = manifest["source_audit"]["meeting_scope_policy"]
        assert manifest["event_count"] == 1
        assert manifest["meeting_artifact_event_count"] == 1
        assert manifest["gap_event_count"] == 0
        assert manifest["source_audit"]["candidate_record_count"] == 3
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert policy["enabled"] is True
        assert policy["filtered_record_count"] == 2
        assert policy["filter_reason_counts"] == {"keyword_denied": 1, "source_platform_not_allowed": 1}
        assert manifest["source_audit"]["meeting_scope_policy_filtered_all"] is False
        assert manifest["source_audit"]["path_results"][0]["scope_policy_filtered_record_count"] == 2
        assert_package_valid(out)


def test_collect_meeting_scope_policy_filtered_all_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "meetings.json"
        out = root / "out"
        package.write_text(
            json.dumps(
                [{"platform": "钉钉", "title": "投委会讨论", "summary": "讨论组合回撤。", "participants": ["研究员A"]}],
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
                str(package),
                "--out-dir",
                str(out),
                "--allow-participant",
                "不存在的参会人",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        gap = events[0]
        assert gap["schema"] == "collectorx.event.v1"
        assert gap["collector"] == "meeting-artifacts"
        assert gap["kind"] == "profile"
        assert gap["time"]
        assert gap["data"]["subtype"] == "collector_gap"
        assert gap["data"]["action_type"] == "collector_gap"
        assert gap["data"]["gap"] == "meeting_scope_policy_filtered_all"
        assert gap["data"]["status"] == "scope_policy_filtered_all"
        assert gap["data"]["profile_type"] == "meeting_artifact_collection_gap"
        assert gap["data"]["candidate_record_count"] == 1
        assert gap["data"]["meeting_artifact_event_count"] == 0
        assert gap["data"]["scope_policy_filtered_record_count"] == 1
        assert gap["data"]["scope_policy_filter_reason_counts"] == {"participant_not_allowed": 1}
        assert gap["data"]["policy_is_user_authorization_scope"] is True
        assert gap["data"]["investment_meeting_fact_claimed"] is False
        assert gap["data"]["complete_meeting_corpus_claimed"] is False
        assert gap["raw_ref"] == {
            "preflight": True,
            "reason": "meeting_scope_policy_filtered_all",
            "scope_policy_enabled": True,
        }
        assert "collection_gap" in gap["privacy"]["contains"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["meeting_artifact_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "scope_policy_excluded_all"
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert manifest["source_audit"]["meeting_scope_policy"]["filter_reason_counts"] == {"participant_not_allowed": 1}
        assert manifest["source_audit"]["meeting_scope_policy_filtered_all"] is True
        assert_package_valid(out)


def test_collect_without_input_gap_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        events = read_events(out)
        assert len(events) == 1
        gap = events[0]
        assert gap["kind"] == "profile"
        assert gap["time"]
        assert gap["data"]["gap"] == "meeting_artifact_input_missing"
        assert gap["data"]["status"] == "needs_meeting_artifact_input"
        assert gap["data"]["candidate_record_count"] == 0
        assert gap["data"]["meeting_artifact_event_count"] == 0
        assert "collection_gap" in gap["privacy"]["contains"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["meeting_artifact_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["source_audit"]["input_count"] == 0
        assert manifest["source_audit"]["resolved_input_file_count"] == 0
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert_package_valid(out)


if __name__ == "__main__":
    test_collect_minutes_and_transcript_events()
    test_collect_platform_exports_and_sanitizes_raw()
    test_collect_meeting_scope_policy_filters_platform_participant_and_keyword()
    test_collect_meeting_scope_policy_filtered_all_status()
    test_collect_without_input_gap_package()
    print("meeting-artifacts tests passed.")
