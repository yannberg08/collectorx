#!/usr/bin/env python3
"""Tests for Feishu CollectorX collect mode."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "feishu_api.py"


def read_events(out: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (out / "lake" / "feishu" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_collect_feishu_authorized_export_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "feishu-export.json"
        meeting_csv = root / "feishu-meeting.csv"
        zip_path = root / "feishu-package.zip"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "workspace": "投研空间",
                    "messages": [
                        {
                            "chat": "投研讨论群",
                            "sender": "研究员A",
                            "time": "2026-07-08T09:00:00+08:00",
                            "content": "讨论半导体订单和估值。",
                            "app_secret": "must-not-leak",
                        }
                    ],
                    "documents": [
                        {
                            "title": "半导体调研纪要",
                            "docs_token": "doccnexample",
                            "url": "https://example.feishu.cn/docx/doccnexample",
                            "content": "调研纪要正文，包含供需和风险。",
                            "updated_at": "2026-07-08T10:00:00+08:00",
                        }
                    ],
                    "files": [
                        {
                            "file_name": "估值表.xlsx",
                            "file_type": "sheet",
                            "link": "https://example.feishu.cn/file/boxcnexample",
                        }
                    ],
                    "recordings": [
                        {
                            "title": "文字记录：路演 2026年7月8日",
                            "summary": "管理层讨论收入、现金流和风险。",
                            "participants": "研究员A、基金经理B",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        meeting_csv.write_text(
            "平台,类型,标题,内容,参会人,会议链接\n"
            "飞书,meeting,飞书投委会,讨论仓位和风控,研究员A、基金经理C,https://example.feishu.cn/minutes/mincnexample\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("feishu/roadshow.md", "# 飞书路演纪要\n参会人：研究员D，基金经理E\n讨论行业空间。\n")
            archive.writestr("../unsafe.md", "# 不应读取\n")
            archive.writestr("..\\windows-traversal.md", "# 不应读取\n")
            archive.writestr("C:\\unsafe.md", "# 不应读取\n")

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
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = read_events(out)
        assert len(events) == 6
        assert {event["collector"] for event in events} == {"feishu"}
        assert {event["data"]["record_kind"] for event in events} == {
            "document",
            "file",
            "meeting",
            "message",
            "recording",
        }
        assert {event["kind"] for event in events} == {"file", "message", "note"}
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("windows-traversal" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("C:/unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        zip_event = next(event for event in events if event["raw_ref"].get("archive_member") == "feishu/roadshow.md")
        assert zip_event["raw_ref"]["source_archive"] == str(zip_path)
        assert zip_event["wiki_targets"] == ["internal.collaboration.meetings"]
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        assert any(event["data"].get("document_ref") == "doccnexample" for event in events)
        assert any("基金经理C" in event["data"].get("participants", []) for event in events)

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collector"] == "feishu"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is True
        assert manifest["collection_readiness"]["can_claim_investment_evidence"] is False
        assert manifest["evidence_policy"]["collector_writes_investor_wiki_directly"] is False
        assert manifest["field_coverage"]["field_counts"]["platform"] == 6
        assert manifest["field_coverage"]["field_counts"]["document_ref"] == 1
        assert manifest["feishu_surface_summary"]["message_event_count"] == 1
        assert manifest["feishu_surface_summary"]["document_event_count"] == 1
        assert manifest["feishu_surface_summary"]["meeting_event_count"] == 3
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["extension_counts"] == {".csv": 1, ".json": 1, ".zip": 1}
        assert manifest["source_audit"]["parsed_record_count"] == 6
        assert manifest["source_audit"]["emitted_event_count"] == 6
        assert len(manifest["source_audit"]["path_results"]) == 3


def test_collect_feishu_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        events = read_events(out)
        assert len(events) == 1
        assert events[0]["data"]["record_kind"] == "collector_gap"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["source_audit"]["input_count"] == 0
        assert manifest["source_audit"]["resolved_input_file_count"] == 0


if __name__ == "__main__":
    test_collect_feishu_authorized_export_package()
    test_collect_feishu_gap()
    print("feishu collect tests passed.")
