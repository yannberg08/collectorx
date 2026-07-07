#!/usr/bin/env python3
"""Tests for notes-collector event output."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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
        assert "content" not in event["data"]
        assert event["wiki_targets"] == ["internal.knowledge.notes"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_notes"] is False


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


if __name__ == "__main__":
    test_obsidian_outputs_collectorx_events_without_full_content_by_default()
    test_import_outputs_youdao_evernote_and_markdown_events()
    print("notes-collector tests passed.")
