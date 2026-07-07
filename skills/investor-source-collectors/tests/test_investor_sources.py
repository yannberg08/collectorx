#!/usr/bin/env python3
"""Tests for investor-source-collectors."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "investor_sources.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=True)


def test_list_sources_contains_all_priorities() -> None:
    result = run_cli("list-sources", "--format", "json")
    profiles = json.loads(result.stdout)
    ids = {profile["id"] for profile in profiles}
    assert "wechat-investment-dialogue" in ids
    assert "xueqiu-investor-activity" in ids
    assert "social-investment-influence" in ids
    priorities = {profile["priority"] for profile in profiles}
    assert {"P0", "P1", "P2"}.issubset(priorities)
    classes = {profile["collector_class"] for profile in profiles}
    assert {"vertical", "lens"}.issubset(classes)


def test_collect_xueqiu_csv_outputs_event_and_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "xueqiu.csv"
        out_dir = root / "out"
        csv_path.write_text("code,name,group,note\n600519,贵州茅台,白酒,长期观察\n", encoding="utf-8")
        run_cli(
            "collect",
            "--source",
            "xueqiu-investor-activity",
            "--input",
            str(csv_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-07T15:00:00+08:00",
        )
        event_path = out_dir / "lake" / "xueqiu-investor-activity" / "events.jsonl"
        events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["schema"] == "collectorx.event.v1"
        assert events[0]["kind"] == "watchlist"
        assert events[0]["data"]["normalized"]["symbol"] == "600519"
        evidence = json.loads((out_dir / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["schema"] == "finclaw.investor_wiki_evidence.v1"
        assert evidence["coverage_summary"]["subdimension_count"] == 20


def test_collect_without_input_writes_gap_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        run_cli(
            "collect",
            "--source",
            "china-wealth-assets",
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-07T15:00:00+08:00",
        )
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "needs_source_authorization_or_input"
        event = json.loads((out_dir / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["data"]["payload"]["signal_type"] == "collector_preflight_gap"


def test_wechat_lens_keeps_only_investment_dialogue() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_path = root / "wechat.json"
        out_dir = root / "out"
        source_path.write_text(
            json.dumps(
                [
                    {
                        "id": "wx-1",
                        "source": "跟投研朋友在 2026-07-07 的微信聊天",
                        "data": {
                            "chat": "投研朋友",
                            "sender": "我",
                            "time": "2026-07-07 10:00:00",
                            "text": "准备买入贵州茅台，仓位先到10%，等财报后再复盘。",
                        },
                    },
                    {
                        "id": "wx-2",
                        "source": "跟朋友在 2026-07-07 的微信聊天",
                        "data": {
                            "chat": "朋友",
                            "sender": "朋友",
                            "time": "2026-07-07 11:00:00",
                            "text": "今晚吃饭吗？",
                        },
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        run_cli(
            "collect",
            "--source",
            "wechat-investment-dialogue",
            "--input",
            str(source_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-07T15:00:00+08:00",
        )
        events = [
            json.loads(line)
            for line in (out_dir / "lake" / "wechat-investment-dialogue" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 1
        assert events[0]["kind"] == "message"
        assert events[0]["data"]["payload"]["text"].startswith("准备买入")
        assert events[0]["data"]["classification"]["is_investment_evidence"] is True
        assert "matched_trade_action_terms" in events[0]["data"]["classification"]["reasons"]


def test_lens_without_investment_match_does_not_fill_wiki_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_path = root / "casual.json"
        out_dir = root / "out"
        source_path.write_text(
            json.dumps(
                [
                    {
                        "id": "wx-1",
                        "source": "跟朋友在 2026-07-07 的微信聊天",
                        "data": {
                            "chat": "朋友",
                            "sender": "朋友",
                            "time": "2026-07-07 11:00:00",
                            "text": "今晚吃饭吗？",
                        },
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        run_cli(
            "collect",
            "--source",
            "wechat-investment-dialogue",
            "--input",
            str(source_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-07T15:00:00+08:00",
        )
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "no_investment_evidence_matched"
        assert manifest["collection_readiness"]["can_claim_complete_source_collection"] is False
        evidence = json.loads((out_dir / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["generated_from"]["event_count"] == 0
        assert evidence["coverage_summary"]["usable_for_wiki_now"] == []


def test_email_research_reads_upstream_collectorx_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_path = root / "email-events.jsonl"
        out_dir = root / "out"
        email_event = {
            "schema": "collectorx.event.v1",
            "id": "email:fixture",
            "collector": "email",
            "source": "IMAP 邮件",
            "owner_scope": "personal",
            "kind": "email",
            "time": "2026-07-07T08:00:00+08:00",
            "collected_at": "2026-07-07T15:00:00+08:00",
            "data": {
                "from": "某证券研究所 <research@example.com>",
                "subject": "晨会纪要：半导体行业跟踪",
                "body_preview": "今日晨会讨论半导体行业景气度和重点公司财报。",
            },
            "raw_ref": {"imap_uid": "1", "folder": "INBOX"},
            "privacy": {"sensitive": True, "local_only": True, "contains": ["email"]},
        }
        source_path.write_text(json.dumps(email_event, ensure_ascii=False) + "\n", encoding="utf-8")
        run_cli(
            "collect",
            "--source",
            "email-research",
            "--input",
            str(source_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-07T15:00:00+08:00",
        )
        event = json.loads((out_dir / "lake" / "email-research" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["kind"] == "email"
        assert event["raw_ref"]["parser"] == "collectorx.event.v1"
        assert event["raw_ref"]["upstream_event_id"] == "email:fixture"
        assert event["data"]["classification"]["confidence"] >= 0.3
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"
        assert manifest["collection_readiness"]["can_claim_complete_source_collection"] is False


def test_task_calendar_lens_keeps_investment_task_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_path = root / "ticktick-events.jsonl"
        out_dir = root / "out"
        events = [
            {
                "schema": "collectorx.event.v1",
                "id": "ticktick:1",
                "collector": "ticktick",
                "source": "滴答清单用户授权任务数据",
                "owner_scope": "personal",
                "kind": "task",
                "time": "2026-07-09T10:00:00+08:00",
                "collected_at": "2026-07-08T01:10:00+08:00",
                "data": {
                    "title": "复盘贵州茅台财报",
                    "content_preview": "看现金流、估值和买入纪律",
                    "project_name": "投资研究",
                },
                "raw_ref": {"task_id": "1"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["task"]},
            },
            {
                "schema": "collectorx.event.v1",
                "id": "ticktick:2",
                "collector": "ticktick",
                "source": "滴答清单用户授权任务数据",
                "owner_scope": "personal",
                "kind": "task",
                "time": "2026-07-09T12:00:00+08:00",
                "collected_at": "2026-07-08T01:10:00+08:00",
                "data": {"title": "买牛奶", "project_name": "生活"},
                "raw_ref": {"task_id": "2"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["task"]},
            },
        ]
        source_path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
        run_cli(
            "collect",
            "--source",
            "task-calendar-investor",
            "--input",
            str(source_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-08T01:10:00+08:00",
        )
        lens_events = [
            json.loads(line)
            for line in (out_dir / "lake" / "task-calendar-investor" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(lens_events) == 1
        assert lens_events[0]["data"]["payload"]["title"] == "复盘贵州茅台财报"


def test_meeting_minutes_lens_keeps_investment_minutes_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_path = root / "meeting-events.jsonl"
        out_dir = root / "out"
        events = [
            {
                "schema": "collectorx.event.v1",
                "id": "meeting:1",
                "collector": "meeting-artifacts",
                "source": "用户授权会议产物",
                "owner_scope": "personal",
                "kind": "note",
                "time": "2026-07-08T10:00:00+08:00",
                "collected_at": "2026-07-08T11:00:00+08:00",
                "data": {
                    "artifact_type": "minutes",
                    "title": "半导体公司路演纪要",
                    "text_preview": "讨论财报、估值、风险点和买入框架。",
                    "participants": ["研究员A", "基金经理B"],
                },
                "raw_ref": {"path": "roadshow.md"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["work_confidential"]},
            },
            {
                "schema": "collectorx.event.v1",
                "id": "meeting:2",
                "collector": "meeting-artifacts",
                "source": "用户授权会议产物",
                "owner_scope": "personal",
                "kind": "note",
                "time": "2026-07-08T12:00:00+08:00",
                "collected_at": "2026-07-08T13:00:00+08:00",
                "data": {
                    "artifact_type": "minutes",
                    "title": "周五团建安排",
                    "text_preview": "讨论聚餐地点和出发时间。",
                },
                "raw_ref": {"path": "team.md"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["work_confidential"]},
            },
        ]
        source_path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
        run_cli(
            "collect",
            "--source",
            "meeting-minutes",
            "--input",
            str(source_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-08T13:30:00+08:00",
        )
        lens_events = [
            json.loads(line)
            for line in (out_dir / "lake" / "meeting-minutes" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(lens_events) == 1
        assert lens_events[0]["data"]["payload"]["title"] == "半导体公司路演纪要"
        assert "matched_source_profile_terms" in lens_events[0]["data"]["classification"]["reasons"]


if __name__ == "__main__":
    test_list_sources_contains_all_priorities()
    test_collect_xueqiu_csv_outputs_event_and_evidence()
    test_collect_without_input_writes_gap_event()
    test_wechat_lens_keeps_only_investment_dialogue()
    test_lens_without_investment_match_does_not_fill_wiki_coverage()
    test_email_research_reads_upstream_collectorx_event()
    test_task_calendar_lens_keeps_investment_task_only()
    test_meeting_minutes_lens_keeps_investment_minutes_only()
    print("investor-source-collectors tests passed.")
