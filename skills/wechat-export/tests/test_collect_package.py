#!/usr/bin/env python3
"""Fixture tests for WeChat CollectorX package output."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import wechat_query  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wechat_query.py"
PACKAGE_VALIDATOR = Path(__file__).resolve().parents[3] / "tools" / "validate_collector_package.py"


def _args():
    return argparse.Namespace(
        days=7,
        after=None,
        limit=None,
        exclude="广告号",
        include_groups="投资讨论群",
        active_group_days=30,
        participated_only=False,
    )


def main():
    records = [
        {
            "id": "wx-abc1234567890000",
            "source": "跟张三在 2026-07-08 的微信聊天",
            "data": {
                "chat": "张三",
                "sender": "我",
                "time": "2026-07-08 09:30:00",
                "text": "先观察这家公司半年报，仓位不要太重。",
            },
        },
        {
            "id": "wx-def1234567890000",
            "source": "微信群「投资讨论群」· 2026-07-08 的聊天",
            "data": {
                "chat": "投资讨论群",
                "sender": "李四",
                "time": "2026-07-08 10:15:00",
                "text": "这份研报里提到的现金流假设偏乐观。",
            },
        },
    ]

    with tempfile.TemporaryDirectory(prefix="wechat_package_test_") as tmp:
        manifest = wechat_query._write_collect_package(
            records,
            tmp,
            args=_args(),
            platform="fixture",
            collected_at="2026-07-08T12:00:00+08:00",
        )
        out_dir = Path(tmp)
        event_path = out_dir / "lake" / "wechat" / "events.jsonl"
        manifest_path = out_dir / "manifest.json"
        summary_path = out_dir / "SUMMARY.md"

        assert event_path.exists(), "events.jsonl missing"
        assert manifest_path.exists(), "manifest.json missing"
        assert summary_path.exists(), "SUMMARY.md missing"

        events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
        assert len(events) == 2
        assert events[0]["schema"] == "collectorx.event.v1"
        assert events[0]["collector"] == "wechat"
        assert events[0]["kind"] == "message"
        assert events[0]["data"]["sender_is_owner"] is True
        assert events[0]["privacy"]["contains"] == ["personal_message", "contact"]
        assert events[0]["time"].startswith("2026-07-08T09:30:00")
        assert events[0]["wiki_targets"] == ["internal.communication.wechat"]
        assert events[1]["data"]["sender_is_owner"] is False

        disk_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert disk_manifest == manifest
        assert manifest["collection_readiness"]["status"] == "baseline+audit"
        assert manifest["event_count"] == 2
        assert manifest["message_event_count"] == 2
        assert manifest["usable_event_count"] == 2
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_enter_personal_channel_lake"] is True
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is False
        assert manifest["field_coverage"]["text"] is True
        assert manifest["message_surface_summary"]["chat_count"] == 2
        assert manifest["message_surface_summary"]["owner_sent_events"] == 1
        assert manifest["evidence_policy"]["routes_to_lens"] == "wechat-investment-dialogue"
        assert manifest["evidence_policy"]["investment_claim_allowed"] is False
        assert manifest["source_audit"]["writes_final_wiki_directly"] is False
        subprocess.run(
            [sys.executable, str(PACKAGE_VALIDATOR), str(out_dir), "--collector", "wechat"],
            text=True,
            capture_output=True,
            check=True,
        )

        summary = summary_path.read_text(encoding="utf-8")
        assert "wechat-investment-dialogue" in summary
        assert "Messages: `2`" in summary
        assert "Gaps: `0`" in summary

    with tempfile.TemporaryDirectory(prefix="wechat_empty_package_test_") as tmp:
        manifest = wechat_query._write_collect_package(
            [],
            tmp,
            args=_args(),
            platform="fixture",
            collected_at="2026-07-08T12:00:00+08:00",
        )
        out_dir = Path(tmp)
        events = [
            json.loads(line)
            for line in (out_dir / "lake" / "wechat" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 1
        assert events[0]["kind"] == "profile"
        assert events[0]["data"]["gap"] == "no_wechat_messages_collected"
        assert events[0]["data"]["profile_type"] == "wechat_collection_gap"
        assert events[0]["data"]["subtype"] == "collector_gap"
        assert events[0]["data"]["action_type"] == "collector_gap"
        assert events[0]["data"]["message_text_collected"] is False
        assert events[0]["data"]["personal_message_fact_collected"] is False
        assert events[0]["data"]["direct_investment_conclusion_claimed"] is False
        assert events[0]["wiki_targets"] == [wechat_query.DATA_QUALITY_TARGET]
        assert manifest["collection_readiness"]["status"] == "no_wechat_messages_collected"
        assert manifest["collection_readiness"]["can_enter_investor_lens"] is False
        assert manifest["collection_readiness"]["can_enter_personal_channel_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["event_count"] == 1
        assert manifest["message_event_count"] == 0
        assert manifest["usable_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        subprocess.run(
            [sys.executable, str(PACKAGE_VALIDATOR), str(out_dir), "--collector", "wechat"],
            text=True,
            capture_output=True,
            check=True,
        )

    with tempfile.TemporaryDirectory(prefix="wechat_preflight_gap_test_") as tmp:
        out_dir = Path(tmp) / "out"
        missing_db = Path(tmp) / "missing-db-storage"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--collect",
                "--db-dir",
                str(missing_db),
                "--out-dir",
                str(out_dir),
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        cli_summary = json.loads(result.stdout)
        assert cli_summary["status"] == "needs_readable_wechat_db_dir"
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "needs_readable_wechat_db_dir"
        assert manifest["collection_readiness"]["can_enter_investor_lens"] is False
        assert manifest["collection_readiness"]["can_enter_personal_channel_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["message_event_count"] == 0
        assert manifest["usable_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        events = [
            json.loads(line)
            for line in (out_dir / "lake" / "wechat" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 1
        assert events[0]["data"]["gap"] == "needs_readable_wechat_db_dir"
        assert events[0]["data"]["profile_type"] == "wechat_collection_gap"
        assert events[0]["data"]["raw_database_access_performed"] is False
        assert events[0]["data"]["raw_database_pages_collected"] is False
        assert events[0]["data"]["message_text_collected"] is False
        assert events[0]["wiki_targets"] == [wechat_query.DATA_QUALITY_TARGET]
        assert str(missing_db) not in json.dumps(events[0], ensure_ascii=False)
        subprocess.run(
            [sys.executable, str(PACKAGE_VALIDATOR), str(out_dir), "--collector", "wechat"],
            text=True,
            capture_output=True,
            check=True,
        )

    print("wechat collect package tests passed.")


if __name__ == "__main__":
    main()
