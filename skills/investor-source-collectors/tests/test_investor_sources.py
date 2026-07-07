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


def test_research_documents_extracts_office_and_pdf_content_when_authorized() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        from docx import Document
        from openpyxl import Workbook
        from reportlab.pdfgen import canvas

        root = Path(tmp)
        out_dir = root / "out"

        xlsx_path = root / "semiconductor-model.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "估值表"
        sheet.append(["公司", "财报", "估值", "风险点"])
        sheet.append(["半导体公司A", "现金流改善", "DCF低估", "库存周期"])
        workbook.save(xlsx_path)

        docx_path = root / "roadshow-notes.docx"
        document = Document()
        document.add_heading("路演纪要", level=1)
        document.add_paragraph("讨论买入理由、财报、估值和安全边际。")
        document.save(docx_path)

        pdf_path = root / "factor-report.pdf"
        pdf = canvas.Canvas(str(pdf_path))
        pdf.drawString(72, 720, "DCF ROE PE PB research report risk review")
        pdf.save()

        run_cli(
            "collect",
            "--source",
            "research-documents",
            "--input",
            str(root),
            "--include-content",
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-08T06:00:00+08:00",
        )
        events = [
            json.loads(line)
            for line in (out_dir / "lake" / "research-documents" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 3
        assert {event["data"]["payload"]["extension"] for event in events} == {".docx", ".pdf", ".xlsx"}
        assert all(event["kind"] == "file" for event in events)
        assert all(event["raw_ref"]["content_read"] is True for event in events)
        assert all(event["data"]["payload"]["content_extract"]["status"] == "extracted" for event in events)
        assert any("DCF低估" in event["data"]["payload"].get("content", "") for event in events)
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "events_collected"
        audit = manifest["collection_audit"]
        assert audit["content_extraction_policy"]["include_content_enabled"] is True
        assert audit["content_extraction_policy"]["content_read_requires_explicit_include_content"] is True
        assert audit["content_read_event_count"] == 3
        assert audit["content_extract_status_counts"] == {"extracted": 3}
        assert audit["parser_counts"] == {"openpyxl": 1, "pdfplumber": 1, "python-docx": 1}
        assert audit["filtered_candidate_count"] == 0


def test_research_documents_without_include_content_keeps_binary_metadata_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        from docx import Document

        root = Path(tmp)
        out_dir = root / "out"
        docx_path = root / "财报复盘.docx"
        document = Document()
        document.add_paragraph("这段正文包含 DCF 低估和买入理由，但本轮没有授权读取正文。")
        document.save(docx_path)

        run_cli(
            "collect",
            "--source",
            "research-documents",
            "--input",
            str(root),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-08T06:20:00+08:00",
        )
        event = json.loads((out_dir / "lake" / "research-documents" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["kind"] == "file"
        assert event["raw_ref"]["parser"] == "metadata"
        assert event["data"]["payload"]["metadata_only"] is True
        assert "content" not in event["data"]["payload"]
        assert "content_extract" not in event["data"]["payload"]
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["content_extraction_policy"]["include_content_enabled"] is False
        assert audit["content_read_event_count"] == 0


def test_research_documents_filters_broad_titles_and_skips_unsupported_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "out"
        (root / "股票计划.png").write_bytes(b"not-an-image-but-metadata-only")
        (root / "研报工具.py").write_text("print('internal helper')\n", encoding="utf-8")

        run_cli(
            "collect",
            "--source",
            "research-documents",
            "--input",
            str(root),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-08T06:30:00+08:00",
        )
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "no_investment_evidence_matched"
        audit = manifest["collection_audit"]
        assert audit["candidate_record_count"] == 1
        assert audit["filtered_candidate_count"] == 1
        assert audit["skipped_file_count"] == 1
        assert audit["skipped_extension_counts"] == {".py": 1}
        assert audit["content_extraction_policy"]["unsupported_extensions_are_skipped"] is True
        evidence = json.loads((out_dir / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["usable_for_wiki_now"] == []


def test_task_calendar_lens_keeps_investment_task_and_calendar_only() -> None:
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
            {
                "schema": "collectorx.event.v1",
                "id": "calendar:1",
                "collector": "calendar",
                "source": "用户授权日历事件",
                "owner_scope": "personal",
                "kind": "calendar",
                "time": "2026-07-10T09:30:00+08:00",
                "collected_at": "2026-07-08T01:10:00+08:00",
                "data": {
                    "title": "贵州茅台财报电话会",
                    "description_preview": "关注现金流、估值、卖出纪律和仓位计划",
                    "calendar_name": "投资日历",
                },
                "raw_ref": {"event_id": "calendar-1"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["calendar"]},
            },
            {
                "schema": "collectorx.event.v1",
                "id": "calendar:2",
                "collector": "calendar",
                "source": "用户授权日历事件",
                "owner_scope": "personal",
                "kind": "calendar",
                "time": "2026-07-10T12:00:00+08:00",
                "collected_at": "2026-07-08T01:10:00+08:00",
                "data": {"title": "牙医预约", "calendar_name": "生活"},
                "raw_ref": {"event_id": "calendar-2"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["calendar"]},
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
        assert len(lens_events) == 2
        assert {event["data"]["payload"]["title"] for event in lens_events} == {"复盘贵州茅台财报", "贵州茅台财报电话会"}


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


def test_wechat_article_favorites_lens_keeps_investment_articles_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_path = root / "wechat-favorites-events.jsonl"
        out_dir = root / "out"
        events = [
            {
                "schema": "collectorx.event.v1",
                "id": "wechat-favorites:1",
                "collector": "wechat-favorites",
                "source": "微信收藏/公众号文章",
                "owner_scope": "personal",
                "kind": "file",
                "time": "2026-07-08T09:00:00+08:00",
                "collected_at": "2026-07-08T10:00:00+08:00",
                "data": {
                    "item_type": "public_account_article",
                    "action_type": "favorite",
                    "title": "半导体行业景气跟踪",
                    "source_account": "券商研究公众号",
                    "text_preview": "讨论财报、估值、风险点和安全边际。",
                },
                "raw_ref": {"url": "https://mp.weixin.qq.com/s/investment"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["personal_message"]},
            },
            {
                "schema": "collectorx.event.v1",
                "id": "wechat-favorites:2",
                "collector": "wechat-favorites",
                "source": "微信收藏/公众号文章",
                "owner_scope": "personal",
                "kind": "file",
                "time": "2026-07-08T10:00:00+08:00",
                "collected_at": "2026-07-08T11:00:00+08:00",
                "data": {
                    "item_type": "public_account_article",
                    "action_type": "favorite",
                    "title": "周末做饭清单",
                    "source_account": "生活号",
                    "text_preview": "采购食材和聚餐安排。",
                },
                "raw_ref": {"url": "https://mp.weixin.qq.com/s/life"},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["personal_message"]},
            },
        ]
        source_path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
        run_cli(
            "collect",
            "--source",
            "wechat-article-favorites",
            "--input",
            str(source_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-08T11:30:00+08:00",
        )
        lens_events = [
            json.loads(line)
            for line in (out_dir / "lake" / "wechat-article-favorites" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(lens_events) == 1
        assert lens_events[0]["data"]["payload"]["title"] == "半导体行业景气跟踪"
        assert lens_events[0]["raw_ref"]["upstream_event_id"] == "wechat-favorites:1"


def test_social_investment_influence_lens_keeps_investment_activity_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_path = root / "social-events.jsonl"
        out_dir = root / "out"
        events = [
            {
                "schema": "collectorx.event.v1",
                "id": "social-activity:1",
                "collector": "social-activity",
                "source": "社交平台用户授权活动",
                "owner_scope": "personal",
                "kind": "note",
                "time": "2026-07-08T10:00:00+08:00",
                "collected_at": "2026-07-08T11:00:00+08:00",
                "data": {
                    "platform": "bilibili",
                    "action_type": "watch",
                    "title": "半导体投资复盘：财报、估值和安全边际",
                    "creator": "财经博主A",
                    "tags": ["股票", "半导体"],
                    "content_preview": "实盘复盘行业景气、估值和风险点。",
                },
                "raw_ref": {"path": "bilibili.csv", "row": 1},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["personal_message", "contact"]},
            },
            {
                "schema": "collectorx.event.v1",
                "id": "social-activity:2",
                "collector": "social-activity",
                "source": "社交平台用户授权活动",
                "owner_scope": "personal",
                "kind": "note",
                "time": "2026-07-08T11:00:00+08:00",
                "collected_at": "2026-07-08T12:00:00+08:00",
                "data": {
                    "platform": "bilibili",
                    "action_type": "like",
                    "title": "游戏直播剪辑",
                    "creator": "娱乐UP主",
                    "tags": ["游戏"],
                    "content_preview": "娱乐内容。",
                },
                "raw_ref": {"path": "bilibili.csv", "row": 2},
                "privacy": {"sensitive": True, "local_only": True, "contains": ["personal_message", "contact"]},
            },
        ]
        source_path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
        run_cli(
            "collect",
            "--source",
            "social-investment-influence",
            "--input",
            str(source_path),
            "--out-dir",
            str(out_dir),
            "--collected-at",
            "2026-07-08T12:30:00+08:00",
        )
        lens_events = [
            json.loads(line)
            for line in (out_dir / "lake" / "social-investment-influence" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(lens_events) == 1
        assert lens_events[0]["data"]["payload"]["title"].startswith("半导体投资复盘")
        assert lens_events[0]["raw_ref"]["upstream_event_id"] == "social-activity:1"


if __name__ == "__main__":
    test_list_sources_contains_all_priorities()
    test_collect_xueqiu_csv_outputs_event_and_evidence()
    test_collect_without_input_writes_gap_event()
    test_wechat_lens_keeps_only_investment_dialogue()
    test_lens_without_investment_match_does_not_fill_wiki_coverage()
    test_email_research_reads_upstream_collectorx_event()
    test_research_documents_extracts_office_and_pdf_content_when_authorized()
    test_task_calendar_lens_keeps_investment_task_and_calendar_only()
    test_meeting_minutes_lens_keeps_investment_minutes_only()
    test_wechat_article_favorites_lens_keeps_investment_articles_only()
    test_social_investment_influence_lens_keeps_investment_activity_only()
    print("investor-source-collectors tests passed.")
