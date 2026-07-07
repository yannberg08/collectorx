#!/usr/bin/env python3
"""Tests for notes-collector event output."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "notes_api.py"


def test_obsidian_outputs_collectorx_events_without_full_content_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault = root / "vault"
        vault.mkdir()
        (vault / "investment.md").write_text("#复盘\n贵州茅台 估值和买入纪律\n", encoding="utf-8")
        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "obsidian",
                "--vault",
                str(vault),
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "notes" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        event = events[0]
        assert event["schema"] == "collectorx.event.v1"
        assert event["collector"] == "notes"
        assert event["kind"] == "note"
        assert event["data"]["source_app"] == "obsidian"
        assert event["data"]["content_preview"].startswith("#复盘")
        assert event["data"]["content_length"] == len("#复盘\n贵州茅台 估值和买入纪律\n")
        assert event["data"]["content_included"] is False
        assert len(event["data"]["content_digest"]) == 64
        assert "content" not in event["data"]
        assert event["wiki_targets"] == ["internal.knowledge.notes"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_notes"] is False
        assert manifest["content_policy"]["full_content_event_count"] == 0
        assert manifest["content_policy"]["preview_only_event_count"] == 1
        assert manifest["evidence_policy"]["required_lens"] == "investment-notes"
        assert manifest["field_coverage"]["field_counts"]["content_length"] == 1
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["obsidian"]
        assert set(manifest["platform_coverage"]["missing_expected_platforms"]) == {"notion", "youdao", "evernote"}
        assert manifest["collection_readiness"]["platform_coverage_status"] == "partial_expected_platforms_observed"


def test_import_outputs_youdao_evernote_and_markdown_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        exports.mkdir()
        (exports / "youdao-notes.json").write_text(
            json.dumps(
                {
                    "notes": [
                        {
                            "source": "有道云笔记",
                            "title": "半导体复盘",
                            "content": "估值、库存周期、买入纪律",
                            "updated": "2026-07-08T10:00:00+08:00",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (exports / "evernote.enex").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>白酒跟踪</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note>现金流和估值复盘</en-note>]]></content>
    <created>20260708T020000Z</created>
    <tag>投资</tag>
  </note>
</en-export>
""",
            encoding="utf-8",
        )
        (exports / "rules.md").write_text("# 交易规则\n控制仓位和回撤\n", encoding="utf-8")
        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(exports),
                "--source-app",
                "auto",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "notes" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 3
        assert {event["data"]["source_app"] for event in events} == {"youdao", "evernote", "markdown"}
        assert {event["data"]["title"] for event in events} == {"半导体复盘", "白酒跟踪", "交易规则"}
        assert all("content" not in event["data"] for event in events)
        assert any("现金流和估值复盘" in event["data"]["content_preview"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_coverage"]["source_app_counts"] == {
            "evernote": 1,
            "markdown": 1,
            "youdao": 1,
        }
        assert set(manifest["platform_coverage"]["missing_expected_platforms"]) == {"obsidian", "notion"}


def test_import_zip_and_all_expected_platform_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        exports.mkdir()
        (exports / "obsidian-review.md").write_text("# 复盘\n组合调整纪律\n", encoding="utf-8")
        (exports / "youdao.json").write_text(
            json.dumps({"notes": [{"source": "有道云笔记", "title": "煤炭跟踪", "content": "供需和估值"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (exports / "evernote.enex").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>银行股规则</title>
    <content><![CDATA[<en-note>分红率和资产质量 checklist</en-note>]]></content>
  </note>
</en-export>
""",
            encoding="utf-8",
        )
        zip_path = exports / "notion-export.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("Notion Export/半导体研究.md", "# 半导体研究\n库存周期和订单验证\n")
            archive.writestr("../unsafe.md", "# 不应读取\n")
            archive.writestr("..\\windows-traversal.md", "# 不应读取\n")
            archive.writestr("C:\\unsafe.md", "# 不应读取\n")

        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(exports),
                "--source-app",
                "auto",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "notes" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 4
        assert {event["data"]["source_app"] for event in events} == {"obsidian", "notion", "youdao", "evernote"}
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("windows-traversal" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("C:/unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        notion_event = next(event for event in events if event["data"]["source_app"] == "notion")
        assert notion_event["raw_ref"]["source_archive"] == str(zip_path)
        assert notion_event["raw_ref"]["archive_member"] == "Notion Export/半导体研究.md"
        assert notion_event["data"]["path"] == f"{zip_path}::Notion Export/半导体研究.md"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["obsidian", "notion", "youdao", "evernote"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == []
        assert manifest["collection_readiness"]["platform_coverage_status"] == "all_expected_platforms_observed"
        assert manifest["platform_coverage"]["real_account_validation"] is False
        assert manifest["field_coverage"]["field_counts"]["source_app"] == 4
        assert manifest["field_coverage"]["field_counts"]["content_length"] == 4
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False
        assert manifest["content_policy"]["full_content_event_count"] == 0
        assert manifest["content_policy"]["investment_classification_done"] is False


if __name__ == "__main__":
    test_obsidian_outputs_collectorx_events_without_full_content_by_default()
    test_import_outputs_youdao_evernote_and_markdown_events()
    test_import_zip_and_all_expected_platform_coverage()
    print("notes-collector tests passed.")
