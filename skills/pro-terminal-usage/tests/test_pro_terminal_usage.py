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
REPO_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "scripts" / "pro_terminal_usage.py"
PACKAGE_VALIDATOR = REPO_ROOT / "tools" / "validate_collector_package.py"


def read_events(out: Path) -> list[dict]:
    event_file = out / "lake" / "pro-terminal-usage" / "events.jsonl"
    return [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]


def assert_package_valid(out: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(PACKAGE_VALIDATOR),
            str(out),
            "--collector",
            "pro-terminal-usage",
            "--require-evidence",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )


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
                            "parameters": {"market": "A股", "period": "2024-2026"},
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
        assert_package_valid(out)
        events = read_events(out)
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
        assert manifest["workflow_event_count"] == 5
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_claim_complete_terminal_usage"] is False
        assert manifest["collection_readiness"]["license_boundary"] == "workflow_metadata_only"
        assert manifest["workflow_surface_summary"]["events_with_workflow_topics"] == 5
        assert manifest["workflow_surface_summary"]["workflow_topic_counts"]["macro_policy"] == 1
        assert manifest["workflow_surface_summary"]["workflow_topic_counts"]["valuation_model"] >= 1
        assert manifest["workflow_intensity_summary"]["events_with_query_terms"] == 1
        assert manifest["workflow_intensity_summary"]["events_with_parameters"] == 1
        assert manifest["workflow_intensity_summary"]["total_watchlist_size"] == 2
        proof = manifest["workflow_boundary_proof"]
        assert proof["proof_level"] == "medium_partial_workflow_boundary"
        assert proof["can_enter_finclaw_lake"] is True
        assert proof["workflow_metadata_only"] is True
        assert proof["workflow_intensity_boundary"]["query_terms_observed"] is True
        assert proof["workflow_intensity_boundary"]["parameters_observed"] is True
        assert proof["terminal_boundary"]["observed_terminals"] == ["wind", "choice", "ifind"]
        assert proof["license_boundary"]["licensed_content_mirrored"] is False
        assert proof["false_claims"]["vendor_database_mirrored"] is False
        assert "missing_expected_terminals:bloomberg" in proof["completion_blockers"]
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["licensed_content_mirrored"] is False
        assert evidence["coverage_summary"]["workflow_boundary_proof"]["can_feed_investor_wiki_evidence"] is True
        assert evidence["coverage_summary"]["workflow_boundary_proof"]["source_boundary"]["path_level_audit_available"] is True
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
                            "workspace_id": "bbg-ws-credit",
                            "module": "Launchpad",
                            "menu_path": "Launchpad/Credit Monitor",
                            "content": "licensed-content-" * 200,
                            "license_key": "must-not-leak",
                        }
                    ],
                    "searches": [
                        {
                            "query": "AI capex credit spread",
                            "query_terms": ["AI capex", "credit spread"],
                            "parameters": {"spread_min_bp": 120, "period": "2024-2026"},
                            "symbols": ["NVDA US Equity"],
                            "industries": "AI,Semiconductor",
                            "time": "2026-07-08T09:00:00+08:00",
                        }
                    ],
                    "downloads": [
                        {
                            "dataset": "FA",
                            "fields": "Revenue, EBITDA",
                            "format": "xlsx",
                            "frequency": "quarterly",
                            "date_range": "2024-2026",
                            "row_count": 240,
                            "export_path": "/exports/fa_ai_infra.xlsx",
                        }
                    ],
                    "templates": [{"template_name": "Credit model", "template_id": "tpl-credit", "function_code": "XLTP", "project": "AI infra"}],
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
        downloads.append(["Terminal", "Title", "Datasets", "Fields", "Format", "Date Range", "File Name", "Row Count", "Export Path"])
        downloads.append(["Wind", "宏观利率导出", "EDB", "M2,社融,十年国债", "xlsx", "2020-2026", "macro_rates.xlsx", "120", "/Users/me/exports/macro_rates.xlsx"])
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
        assert_package_valid(out)
        events = read_events(out)
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
        assert workspace["data"]["workspace_id"] == "bbg-ws-credit"
        search = next(event for event in events if event["data"]["activity_type"] == "search")
        assert search["data"]["query_terms"] == ["AI capex", "credit spread"]
        assert search["data"]["parameters"]["spread_min_bp"] == 120
        download = next(event for event in events if event["data"].get("file_name") == "macro_rates.xlsx")
        assert download["data"]["datasets"] == ["EDB"]
        assert "十年国债" in download["data"]["fields"]
        assert download["data"]["row_count"] == 120
        assert download["data"]["export_path"] == "/Users/me/exports/macro_rates.xlsx"
        bbg_download = next(event for event in events if event["data"].get("export_path") == "/exports/fa_ai_infra.xlsx")
        assert bbg_download["data"]["row_count"] == 240
        template = next(event for event in events if event["data"]["activity_type"] == "model_template")
        assert template["data"]["template_id"] == "tpl-credit"
        watchlist = next(event for event in events if event["data"].get("title") == "央企红利自选")
        assert watchlist["data"]["regions"] == ["CN", "HK"]
        assert watchlist["data"]["watchlist_size"] == 2
        zip_event = next(event for event in events if event["data"].get("title") == "半导体设备观察")
        assert zip_event["raw_ref"]["path"] == f"{ifind_zip}::usage/ifind_watchlist.json"
        assert zip_event["raw_ref"]["source_archive"] == str(ifind_zip)
        assert zip_event["raw_ref"]["archive_member"] == "usage/ifind_watchlist.json"
        assert all("../unsafe" not in event["raw_ref"]["path"] for event in events)
        assert all("windows-traversal" not in event["raw_ref"]["path"] for event in events)
        assert all("C:/unsafe" not in event["raw_ref"]["path"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["workflow_event_count"] == 8
        assert manifest["gap_event_count"] == 0
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
        assert manifest["workflow_surface_summary"]["events_with_query_terms"] == 1
        assert manifest["workflow_surface_summary"]["events_with_parameters"] == 1
        assert manifest["workflow_surface_summary"]["events_with_export_path"] == 2
        assert manifest["workflow_surface_summary"]["events_with_row_count"] == 2
        assert manifest["workflow_surface_summary"]["events_with_workspace_id"] == 1
        assert manifest["workflow_surface_summary"]["events_with_template_id"] == 1
        assert manifest["workflow_surface_summary"]["events_with_content_preview"] == 1
        intensity = manifest["workflow_intensity_summary"]
        assert intensity["events_with_query_terms"] == 1
        assert intensity["unique_query_term_count"] == 2
        assert intensity["events_with_parameters"] == 1
        assert intensity["events_with_export_path"] == 2
        assert intensity["events_with_row_count"] == 2
        assert intensity["total_export_rows"] == 360
        assert intensity["max_export_rows"] == 240
        assert intensity["events_with_workspace_id"] == 1
        assert intensity["events_with_template_id"] == 1
        assert intensity["total_symbol_refs"] == 4
        assert intensity["total_field_refs"] == 5
        assert intensity["total_dataset_refs"] == 2
        assert intensity["total_factor_refs"] == 1
        assert intensity["total_watchlist_size"] == 3
        assert intensity["function_code_counts"] == {"XLTP": 1}
        assert intensity["dataset_counts"] == {"EDB": 1, "FA": 1}
        assert intensity["download_format_counts"] == {"xlsx": 2}
        boundary_proof = manifest["workflow_boundary_proof"]
        assert boundary_proof["proof_level"] == "strong_partial_workflow_boundary"
        assert boundary_proof["authorized_input_observed"] is True
        assert boundary_proof["terminal_boundary"]["observed_terminals"] == ["wind", "choice", "ifind", "bloomberg"]
        assert boundary_proof["terminal_boundary"]["missing_expected_terminals"] == []
        assert boundary_proof["activity_boundary"]["missing_expected_activities"] == []
        assert boundary_proof["workflow_field_boundary"]["missing_recommended_fields"] == []
        assert boundary_proof["workflow_topic_boundary"]["missing_expected_workflow_topics"] == []
        assert boundary_proof["workflow_surface_boundary"]["events_with_content_preview"] == 1
        assert boundary_proof["workflow_intensity_boundary"]["query_terms_observed"] is True
        assert boundary_proof["workflow_intensity_boundary"]["parameters_observed"] is True
        assert boundary_proof["workflow_intensity_boundary"]["export_paths_observed"] is True
        assert boundary_proof["workflow_intensity_boundary"]["row_counts_observed"] is True
        assert boundary_proof["workflow_intensity_boundary"]["total_export_rows"] == 360
        assert boundary_proof["source_boundary"]["requested_input_count"] == 1
        assert boundary_proof["source_boundary"]["resolved_input_file_count"] == 3
        assert boundary_proof["source_boundary"]["archive_member_count"] == 4
        assert boundary_proof["source_boundary"]["skipped_archive_member_count"] == 3
        assert boundary_proof["license_boundary"]["content_preview_max_chars"] == 800
        assert boundary_proof["license_boundary"]["license_keys_collected"] is False
        assert boundary_proof["wiki_boundary"]["collector_writes_wiki_directly"] is False
        assert boundary_proof["false_claims"]["complete_terminal_usage_history_claimed"] is False
        assert boundary_proof["false_claims"]["licensed_content_body_mirrored"] is False
        assert "complete_terminal_usage_history_not_proven" in boundary_proof["completion_blockers"]
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
        assert evidence["coverage_summary"]["workflow_intensity_summary"]["total_export_rows"] == 360
        assert evidence["coverage_summary"]["workflow_boundary_proof"]["proof_level"] == "strong_partial_workflow_boundary"
        assert evidence["coverage_summary"]["workflow_boundary_proof"]["source_boundary"]["archive_member_count"] == 4
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
        assert_package_valid(out)
        events = read_events(out)
        assert len(events) == 1
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["workflow_event_count"] == 1
        assert manifest["gap_event_count"] == 0
        source_audit = manifest["source_audit"]
        assert source_audit["limit_reached"] is True
        assert source_audit["archive_member_event_count"] == 1
        assert source_audit["parsed_record_count"] == 1
        assert source_audit["emitted_event_count"] == 1
        assert source_audit["path_results"][0]["parsed_record_count"] == 1


def test_collect_respects_authorization_scope_policy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "terminal_scope.json"
        out = root / "out"
        export.write_text(
            json.dumps(
                {
                    "usage": [
                        {
                            "terminal": "Wind",
                            "activity_type": "download",
                            "workspace": "Macro Desk",
                            "project": "AI Infra",
                            "dataset": "FA",
                            "fields": "Revenue, EBITDA",
                            "query": "AI capex revenue export",
                            "row_count": 120,
                        },
                        {
                            "terminal": "Choice",
                            "activity_type": "download",
                            "workspace": "Macro Desk",
                            "project": "AI Infra",
                            "dataset": "FA",
                            "fields": "Revenue",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "search",
                            "workspace": "Macro Desk",
                            "project": "AI Infra",
                            "dataset": "FA",
                            "fields": "Revenue",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "download",
                            "workspace": "Other Desk",
                            "project": "AI Infra",
                            "dataset": "FA",
                            "fields": "Revenue",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "download",
                            "workspace": "Macro Desk",
                            "project": "Rates",
                            "dataset": "FA",
                            "fields": "Revenue",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "download",
                            "workspace": "Macro Desk",
                            "project": "AI Infra",
                            "dataset": "EDB",
                            "fields": "Revenue",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "download",
                            "workspace": "Macro Desk",
                            "project": "AI Infra",
                            "dataset": "FA",
                            "fields": "PB",
                        },
                        {
                            "terminal": "Wind",
                            "activity_type": "download",
                            "workspace": "Macro Desk",
                            "project": "AI Infra",
                            "dataset": "FA",
                            "fields": "Revenue",
                            "title": "secret strategy export",
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
                str(export),
                "--out-dir",
                str(out),
                "--allow-terminal",
                "wind",
                "--allow-activity",
                "download",
                "--allow-workspace",
                "Macro Desk",
                "--allow-project",
                "AI Infra",
                "--allow-dataset",
                "FA",
                "--allow-field",
                "Revenue",
                "--deny-keyword",
                "secret strategy",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        assert_package_valid(out)
        events = read_events(out)
        assert len(events) == 1
        assert events[0]["data"]["terminal"] == "wind"
        assert events[0]["data"]["activity_type"] == "download"
        assert events[0]["data"]["workspace"] == "Macro Desk"
        assert events[0]["data"]["project"] == "AI Infra"
        assert events[0]["data"]["datasets"] == ["FA"]
        assert "Revenue" in events[0]["data"]["fields"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["workflow_event_count"] == 1
        assert manifest["gap_event_count"] == 0
        source_audit = manifest["source_audit"]
        assert source_audit["candidate_record_count"] == 8
        assert source_audit["parsed_record_count"] == 8
        assert source_audit["emitted_event_count"] == 1
        assert source_audit["scope_policy_filtered_record_count"] == 7
        assert source_audit["scope_policy_filter_reason_counts"] == {
            "activity_not_allowed": 1,
            "dataset_not_allowed": 1,
            "field_not_allowed": 1,
            "keyword_denied": 1,
            "project_not_allowed": 1,
            "terminal_not_allowed": 1,
            "workspace_not_allowed": 1,
        }
        assert source_audit["pro_terminal_scope_policy"]["enabled"] is True
        assert source_audit["pro_terminal_scope_policy"]["allow_terminals"] == ["wind"]
        assert source_audit["pro_terminal_scope_policy"]["allow_activities"] == ["download"]
        assert source_audit["pro_terminal_scope_policy"]["allow_workspaces"] == ["macro desk"]
        assert source_audit["pro_terminal_scope_policy"]["allow_projects"] == ["ai infra"]
        assert source_audit["pro_terminal_scope_policy"]["allow_datasets"] == ["fa"]
        assert source_audit["pro_terminal_scope_policy"]["allow_fields"] == ["revenue"]
        assert source_audit["path_results"][0]["scope_policy_filter_status"] == "partially_filtered"
        proof = manifest["workflow_boundary_proof"]
        assert proof["authorization_scope_boundary"]["scope_policy_filtered_record_count"] == 7
        assert proof["authorization_scope_boundary"]["pro_terminal_scope_policy_filtered_all"] is False
        assert manifest["collection_readiness"]["status"] == "events_collected"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is True
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["workflow_boundary_proof"]["authorization_scope_boundary"]["candidate_record_count"] == 8


def test_collect_scope_policy_filtered_all_is_not_success() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "choice_scope.json"
        out = root / "out"
        export.write_text(
            json.dumps(
                {
                    "usage": [
                        {
                            "terminal": "Choice",
                            "activity_type": "download",
                            "workspace": "Macro Desk",
                            "dataset": "EDB",
                            "fields": "M2, CPI",
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
                "--input",
                str(export),
                "--out-dir",
                str(out),
                "--allow-terminal",
                "wind",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        assert_package_valid(out)
        events = read_events(out)
        assert len(events) == 1
        gap = events[0]
        assert gap["kind"] == "profile"
        assert gap["time"] == gap["collected_at"]
        assert gap["data"]["subtype"] == "collector_gap"
        assert gap["data"]["activity_type"] == "collector_gap"
        assert gap["data"]["gap"] == "pro_terminal_scope_policy_filtered_all"
        assert gap["data"]["status"] == "scope_policy_filtered_all"
        assert gap["data"]["profile_type"] == "pro_terminal_usage_collection_gap"
        assert gap["data"]["candidate_record_count"] == 1
        assert gap["data"]["workflow_event_count"] == 0
        assert gap["data"]["retained_event_count"] == 0
        assert gap["data"]["scope_policy_filtered_record_count"] == 1
        assert gap["data"]["scope_policy_filter_reason_counts"] == {"terminal_not_allowed": 1}
        assert gap["data"]["policy_is_user_authorization_scope"] is True
        assert gap["data"]["policy_does_not_assert_investment_relevance"] is True
        assert gap["data"]["terminal_workflow_fact_claimed"] is False
        assert gap["data"]["vendor_database_mirrored"] is False
        assert gap["data"]["licensed_content_body_mirrored"] is False
        assert gap["data"]["license_keys_collected"] is False
        assert gap["raw_ref"] == {
            "preflight": True,
            "reason": "pro_terminal_scope_policy_filtered_all",
            "scope_policy_enabled": True,
        }
        assert "collection_gap" in gap["privacy"]["contains"]
        assert str(export) not in json.dumps(gap, ensure_ascii=False)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["workflow_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "scope_policy_excluded_all"
        assert manifest["workflow_boundary_proof"]["proof_level"] == "scope_policy_filtered_all"
        assert manifest["workflow_boundary_proof"]["can_enter_finclaw_lake"] is False
        assert "authorization_scope_excluded_all_records" in manifest["workflow_boundary_proof"]["completion_blockers"]
        source_audit = manifest["source_audit"]
        assert source_audit["candidate_record_count"] == 1
        assert source_audit["parsed_record_count"] == 1
        assert source_audit["emitted_event_count"] == 1
        assert source_audit["scope_policy_filtered_record_count"] == 1
        assert source_audit["scope_policy_filter_reason_counts"] == {"terminal_not_allowed": 1}
        assert source_audit["pro_terminal_scope_policy_filtered_all"] is True
        assert source_audit["path_results"][0]["status"] == "filtered_by_scope_policy"
        assert source_audit["path_results"][0]["reason"] == "scope_policy_excluded_all_records"
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["generated_from"]["event_count"] == 0
        assert evidence["coverage_summary"]["workflow_boundary_proof"]["proof_level"] == "scope_policy_filtered_all"
        assert evidence["coverage_summary"]["workflow_boundary_proof"]["can_feed_investor_wiki_evidence"] is False


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
        assert_package_valid(out)
        events = read_events(out)
        assert len(events) == 1
        assert events[0]["kind"] == "profile"
        assert events[0]["time"] == "2026-07-08T04:30:00+08:00"
        assert events[0]["data"]["gap"] == "pro_terminal_usage_authorized_input_missing"
        assert events[0]["data"]["status"] == "needs_pro_terminal_usage_input"
        assert events[0]["data"]["candidate_record_count"] == 0
        assert events[0]["data"]["workflow_event_count"] == 0
        assert events[0]["data"]["terminal_workflow_fact_claimed"] is False
        assert str(missing) not in json.dumps(events[0], ensure_ascii=False)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["workflow_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["collection_readiness"]["status"] == "needs_pro_terminal_usage_input"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["workflow_boundary_proof"]["proof_level"] == "no_authorized_terminal_input"
        assert manifest["workflow_boundary_proof"]["can_enter_finclaw_lake"] is False
        assert manifest["workflow_boundary_proof"]["source_boundary"]["input_missing_count"] == 1
        assert manifest["workflow_boundary_proof"]["false_claims"]["license_keys_collected"] is False
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
    test_collect_respects_authorization_scope_policy()
    test_collect_scope_policy_filtered_all_is_not_success()
    test_collect_missing_input_writes_gap_audit()
    print("pro-terminal-usage tests passed.")
