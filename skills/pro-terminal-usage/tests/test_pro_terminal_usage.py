#!/usr/bin/env python3
"""Tests for pro-terminal-usage collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pro_terminal_usage.py"


def test_collect_terminal_workflow_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "wind_usage.json"
        csv_path = root / "ifind_watchlist.csv"
        html_path = root / "choice_workspace.html"
        out = root / "out"
        export.write_text(
            json.dumps(
                {
                    "usage": [
                        {
                            "terminal": "Wind",
                            "activity_type": "search",
                            "query": "半导体 ROE 估值",
                            "time": "2026-07-08T09:00:00+08:00",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "model_template",
                            "template_name": "DCF估值模板",
                            "symbols": ["NVDA.US", "00700.HK"],
                            "factors": "DCF, ROE, PE",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        csv_path.write_text(
            "terminal,activity_type,title,symbols,industries,time\n"
            "同花顺 iFinD,watchlist,港股互联网自选,\"00700.HK,09988.HK\",互联网,2026-07-08T10:00:00+08:00\n"
            "同花顺 iFinD,download,半导体财务指标导出,,半导体,2026-07-08T11:00:00+08:00\n",
            encoding="utf-8",
        )
        html_path.write_text(
            "<html><head><title>Choice 宏观看板</title>"
            "<meta name=\"application-name\" content=\"Choice\"></head>"
            "<body>工作区：宏观利率与汇率监控。</body></html>",
            encoding="utf-8",
        )
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
                "2026-07-08T04:30:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "pro-terminal-usage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 5
        assert {event["data"]["activity_type"] for event in events} == {"download", "model_template", "search", "watchlist", "workspace"}
        assert {event["data"]["terminal"] for event in events} == {"choice", "ifind", "wind"}
        watchlist = next(event for event in events if event["data"]["activity_type"] == "watchlist")
        assert watchlist["kind"] == "watchlist"
        assert watchlist["data"]["symbols"] == ["00700.HK", "09988.HK"]
        model = next(event for event in events if event["data"]["activity_type"] == "model_template")
        assert "PE" in model["data"]["factors"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_terminal_usage"] is False
        assert manifest["collection_readiness"]["license_boundary"] == "workflow_metadata_only"
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["licensed_content_mirrored"] is False
        assert evidence["generated_from"]["event_count"] == 5


def test_collect_nested_sections_workbook_and_sanitizes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "bloomberg_workflow.json"
        workbook_path = root / "choice_workflow.xlsx"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "terminal": "Bloomberg",
                    "user_workspace": "credit research",
                    "workspaces": [
                        {
                            "title": "US Credit Monitor",
                            "module": "Launchpad",
                            "content": "licensed-content-" * 200,
                            "license_key": "must-not-leak",
                        }
                    ],
                    "searches": [{"query": "AI capex credit spread", "symbols": ["NVDA US Equity"], "time": "2026-07-08T09:00:00+08:00"}],
                    "downloads": [{"dataset": "FA", "fields": "Revenue, EBITDA", "format": "xlsx", "date_range": "2024-2026"}],
                    "templates": [{"template_name": "Credit model", "function_code": "XLTP", "project": "AI infra"}],
                    "factors": [{"factor": "OAS", "universe": "US IG Tech"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        workbook = openpyxl.Workbook()
        watchlists = workbook.active
        watchlists.title = "Watchlists"
        watchlists.append(["Terminal", "Title", "Symbols", "Markets", "Project"])
        watchlists.append(["Choice", "央企红利自选", "600900.SH,00883.HK", "CN,HK", "红利策略"])
        downloads = workbook.create_sheet("Downloads")
        downloads.append(["Terminal", "Title", "Datasets", "Fields", "Format", "Date Range", "File Name"])
        downloads.append(["Wind", "宏观利率导出", "EDB", "M2,社融,十年国债", "xlsx", "2020-2026", "macro_rates.xlsx"])
        workbook.save(workbook_path)

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "pro-terminal-usage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 7
        assert {event["data"]["activity_type"] for event in events} == {
            "download",
            "factor_attention",
            "model_template",
            "search",
            "watchlist",
            "workspace",
        }
        assert {event["data"]["terminal"] for event in events} == {"bloomberg", "choice", "wind"}
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        workspace = next(event for event in events if event["data"]["activity_type"] == "workspace")
        assert len(workspace["data"]["raw"]["content"]) == 800
        download = next(event for event in events if event["data"].get("file_name") == "macro_rates.xlsx")
        assert download["data"]["datasets"] == ["EDB"]
        assert "十年国债" in download["data"]["fields"]
        watchlist = next(event for event in events if event["data"].get("title") == "央企红利自选")
        assert watchlist["data"]["regions"] == ["CN", "HK"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["activity_counts"]["download"] == 2


if __name__ == "__main__":
    test_collect_terminal_workflow_exports()
    test_collect_nested_sections_workbook_and_sanitizes()
    print("pro-terminal-usage tests passed.")
