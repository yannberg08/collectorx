#!/usr/bin/env python3
"""Tests for pro-terminal-usage collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
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
        assert all(event["data"].get("workflow_topics") for event in events)
        watchlist = next(event for event in events if event["data"]["activity_type"] == "watchlist")
        assert watchlist["kind"] == "watchlist"
        assert watchlist["data"]["symbols"] == ["00700.HK", "09988.HK"]
        model = next(event for event in events if event["data"]["activity_type"] == "model_template")
        assert "PE" in model["data"]["factors"]
        assert "valuation_model" in model["data"]["workflow_topics"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_terminal_usage"] is False
        assert manifest["collection_readiness"]["license_boundary"] == "workflow_metadata_only"
        assert manifest["workflow_surface_summary"]["events_with_workflow_topics"] == 5
        assert manifest["workflow_surface_summary"]["workflow_topic_counts"]["macro_policy"] == 1
        assert manifest["workflow_surface_summary"]["workflow_topic_counts"]["valuation_model"] >= 1
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["licensed_content_mirrored"] is False
        assert evidence["coverage_summary"]["workflow_surface_summary"]["events_with_workflow_topics"] == 5
        assert evidence["generated_from"]["event_count"] == 5
        assert evidence["coverage_summary"]["dimension_count"] == 7
        assert evidence["coverage_summary"]["subdimension_count"] == 20
        analysis_ability = next(
            child
            for dimension in evidence["dimensions"]
            for child in dimension["children"]
            if child["subdimension_id"] == "inv-analysis-ability"
        )
        assert analysis_ability["support_level"] == "medium"
        assert analysis_ability["evidence_count"] >= 2


def test_collect_nested_sections_workbook_and_sanitizes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "bloomberg_workflow.json"
        workbook_path = root / "choice_workflow.xlsx"
        ifind_zip = root / "ifind_workflow.zip"
        unsupported = root / "ignore.bin"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "terminal": "Bloomberg",
                    "user_workspace": "credit research",
                    "workspaces": [
                        {
                            "title": "US Credit Monitor",
                            "workspace": "credit research",
                            "module": "Launchpad",
                            "menu_path": "Launchpad/Credit Monitor",
                            "content": "licensed-content-" * 200,
                            "license_key": "must-not-leak",
                        }
                    ],
                    "searches": [{"query": "AI capex credit spread", "symbols": ["NVDA US Equity"], "industries": "AI,Semiconductor", "time": "2026-07-08T09:00:00+08:00"}],
                    "downloads": [{"dataset": "FA", "fields": "Revenue, EBITDA", "format": "xlsx", "frequency": "quarterly", "date_range": "2024-2026"}],
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
        with zipfile.ZipFile(ifind_zip, "w") as archive:
            archive.writestr(
                "usage/ifind_watchlist.json",
                json.dumps(
                    {
                        "watchlists": [
                            {
                                "terminal": "同花顺 iFinD",
                                "title": "半导体设备观察",
                                "symbols": ["688012.SH"],
                                "project": "设备国产化",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"terminal": "iFinD", "activity_type": "download"}], ensure_ascii=False))
            archive.writestr("..\\windows-traversal.json", json.dumps([{"terminal": "iFinD", "activity_type": "download"}], ensure_ascii=False))
            archive.writestr("C:\\unsafe.json", json.dumps([{"terminal": "iFinD", "activity_type": "download"}], ensure_ascii=False))
        unsupported.write_bytes(b"not a supported terminal export")

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "pro-terminal-usage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 8
        assert {event["data"]["activity_type"] for event in events} == {
            "download",
            "factor_attention",
            "model_template",
            "search",
            "watchlist",
            "workspace",
        }
        assert {event["data"]["terminal"] for event in events} == {"bloomberg", "choice", "ifind", "wind"}
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        workspace = next(event for event in events if event["data"]["activity_type"] == "workspace")
        assert len(workspace["data"]["raw"]["content"]) == 800
        assert workspace["data"]["content_length"] > 800
        assert workspace["data"]["menu_path"] == "Launchpad/Credit Monitor"
        download = next(event for event in events if event["data"].get("file_name") == "macro_rates.xlsx")
        assert download["data"]["datasets"] == ["EDB"]
        assert "十年国债" in download["data"]["fields"]
        watchlist = next(event for event in events if event["data"].get("title") == "央企红利自选")
        assert watchlist["data"]["regions"] == ["CN", "HK"]
        zip_event = next(event for event in events if event["data"].get("title") == "半导体设备观察")
        assert zip_event["raw_ref"]["path"] == f"{ifind_zip}::usage/ifind_watchlist.json"
        assert zip_event["raw_ref"]["source_archive"] == str(ifind_zip)
        assert zip_event["raw_ref"]["archive_member"] == "usage/ifind_watchlist.json"
        assert all("../unsafe" not in event["raw_ref"]["path"] for event in events)
        assert all("windows-traversal" not in event["raw_ref"]["path"] for event in events)
        assert all("C:/unsafe" not in event["raw_ref"]["path"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["activity_counts"]["download"] == 2
        assert manifest["terminal_coverage"]["observed_expected_terminals"] == ["wind", "choice", "ifind", "bloomberg"]
        assert manifest["terminal_coverage"]["missing_expected_terminals"] == []
        assert manifest["activity_coverage"]["observed_expected_activities"] == [
            "workspace",
            "watchlist",
            "search",
            "download",
            "model_template",
            "factor_attention",
        ]
        assert manifest["activity_coverage"]["missing_expected_activities"] == []
        assert manifest["workflow_field_coverage"]["missing_recommended_fields"] == []
        assert manifest["workflow_surface_summary"]["workflow_event_count"] == 8
        assert manifest["workflow_surface_summary"]["events_with_workflow_topics"] == 8
        assert manifest["workflow_surface_summary"]["missing_expected_workflow_topics"] == []
        assert manifest["workflow_surface_summary"]["workflow_topic_counts"] == {
            "macro_policy": 1,
            "market_strategy": 1,
            "industry_theme": 3,
            "company_fundamental": 1,
            "valuation_model": 1,
            "credit_fixed_income": 4,
            "factor_quant": 1,
            "portfolio_monitoring": 3,
            "data_export": 2,
            "hk_us_market": 4,
        }
        assert manifest["workflow_surface_summary"]["activity_topic_counts"]["download:data_export"] == 2
        assert manifest["workflow_surface_summary"]["terminal_topic_counts"]["bloomberg:credit_fixed_income"] == 4
        assert manifest["workflow_surface_summary"]["events_with_symbols"] >= 3
        assert manifest["workflow_surface_summary"]["events_with_datasets"] == 2
        assert manifest["workflow_surface_summary"]["events_with_fields"] == 2
        assert manifest["workflow_surface_summary"]["events_with_content_preview"] == 1
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["source_section_event_count"] == 8
        assert manifest["source_audit"]["resolved_input_file_count"] == 3
        assert manifest["source_audit"]["parsed_record_count"] == 8
        assert manifest["source_audit"]["emitted_event_count"] == 8
        assert manifest["source_audit"]["skipped_file_count"] == 1
        assert manifest["source_audit"]["skipped_reason_counts"] == {"unsupported_extension": 1}
        assert manifest["source_audit"]["skipped_extension_counts"] == {".bin": 1}
        assert manifest["source_audit"]["extension_counts"] == {
            ".bin": 1,
            ".json": 1,
            ".xlsx": 1,
            ".zip": 1,
        }
        assert len(manifest["source_audit"]["path_results"]) == 4
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False
        assert manifest["source_audit"]["windows_drive_archive_members_collected"] is False
        assert manifest["license_policy"]["licensed_content_mirrored"] is False
        assert manifest["license_policy"]["content_preview_max_chars"] == 800
        assert manifest["evidence_policy"]["personal_workflow_only"] is True
        assert manifest["collection_readiness"]["terminal_coverage_status"] == "all_expected_terminals_observed"
        assert manifest["collection_readiness"]["activity_coverage_status"] == "all_expected_activity_types_observed"
        assert manifest["collection_readiness"]["workflow_field_coverage_status"] == "all_expected_workflow_fields_observed"
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["personal_workflow_only"] is True
        assert evidence["coverage_summary"]["workflow_metadata_only"] is True
        assert evidence["coverage_summary"]["vendor_database_mirror"] is False
        assert evidence["coverage_summary"]["workflow_surface_summary"]["missing_expected_workflow_topics"] == []
        assert evidence["coverage_summary"]["dimension_count"] == 7
        assert evidence["coverage_summary"]["subdimension_count"] == 20


def test_collect_zip_limit_counts_only_emitted_records() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "wind.zip"
        out = root / "out"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "usage.json",
                json.dumps(
                    [
                        {
                            "terminal": "Wind",
                            "activity_type": "search",
                            "query": "半导体景气度",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "search",
                            "query": "AI 服务器",
                        },
                    ],
                    ensure_ascii=False,
                ),
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
                "--limit",
                "1",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "pro-terminal-usage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        source_audit = manifest["source_audit"]
        assert source_audit["limit_reached"] is True
        assert source_audit["archive_member_event_count"] == 1
        assert source_audit["parsed_record_count"] == 1
        assert source_audit["emitted_event_count"] == 1
        assert source_audit["path_results"][0]["parsed_record_count"] == 1


def test_collect_missing_input_writes_gap_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "out"
        missing = root / "missing-export"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(missing),
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
        assert len(events) == 1
        assert events[0]["data"]["gap"] == "pro_terminal_usage_authorized_input_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "needs_pro_terminal_usage_input"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["source_audit"]["input_count"] == 1
        assert manifest["source_audit"]["input_missing_count"] == 1
        assert manifest["source_audit"]["parsed_record_count"] == 0
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert manifest["source_audit"]["skipped_reason_counts"] == {"input_missing": 1}
        assert manifest["source_audit"]["path_results"][0]["status"] == "missing"


if __name__ == "__main__":
    test_collect_terminal_workflow_exports()
    test_collect_nested_sections_workbook_and_sanitizes()
    test_collect_zip_limit_counts_only_emitted_records()
    test_collect_missing_input_writes_gap_audit()
    print("pro-terminal-usage tests passed.")
