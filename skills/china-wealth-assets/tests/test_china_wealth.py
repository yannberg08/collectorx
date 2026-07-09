#!/usr/bin/env python3
"""Tests for china-wealth-assets."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "scripts" / "china_wealth.py"
PACKAGE_VALIDATOR = REPO_ROOT / "tools" / "validate_collector_package.py"
FIVE_PLATFORM_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "china-wealth-five-platform" / "five_platform_assets.json"
SENSITIVE_TERMS = ("cookie", "token", "authorization", "password", "session")
SECRET_MARKER = "SHOULD_NOT_LEAK"


def read_events(out: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def string_values(payload: object) -> list[str]:
    if isinstance(payload, dict):
        values: list[str] = []
        for value in payload.values():
            values.extend(string_values(value))
        return values
    if isinstance(payload, list):
        values = []
        for item in payload:
            values.extend(string_values(item))
        return values
    return [payload] if isinstance(payload, str) else []


def assert_sensitive_terms_absent_from_values(payload: object) -> None:
    for value in string_values(payload):
        lowered = value.lower()
        assert not any(term in lowered for term in SENSITIVE_TERMS), value


def assert_sensitive_keys_absent(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            assert not any(term in lowered for term in SENSITIVE_TERMS), key
            assert_sensitive_keys_absent(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_sensitive_keys_absent(item)


def assert_secret_marker_absent_from_package(out: Path) -> None:
    for path in [
        out / "lake" / "china-wealth-assets" / "events.jsonl",
        out / "manifest.json",
        out / "investor_wiki_evidence.v1.json",
        out / "SUMMARY.md",
    ]:
        assert SECRET_MARKER not in path.read_text(encoding="utf-8")


def test_collect_fund_holding_and_transaction() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "fund.csv"
        out = root / "out"
        csv_path.write_text(
            "平台,类型,基金代码,基金名称,份额,单位净值,持仓金额,持仓成本,持有收益,日期\n"
            "天天基金,持仓,000001,华夏成长混合,1000,1.234,1234,1000,234,2026-07-07\n"
            "天天基金,申购,000001,华夏成长混合,, ,1000,, ,2026-07-06\n",
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(csv_path), "--out-dir", str(out), "--collected-at", "2026-07-07T15:00:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["kind"] for event in events] == ["holding", "trade"]
        assert events[0]["data"]["product_code"] == "000001"
        assert events[0]["data"]["market_value"] == 1234.0
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "events_collected"
        assert manifest["usable_event_count"] == 2
        assert manifest["asset_event_count"] == 2
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_enter_china_wealth_lake"] is True
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is False
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is True
        assert manifest["collection_readiness"]["usable_event_count"] == 2
        assert manifest["collection_readiness"]["can_claim_complete_asset_boundary"] is False
        assert manifest["collection_readiness"]["asset_boundary_scope"] == "partial_authorized_input"
        assert manifest["platform_counts"] == {"tiantian-fund": 2}
        assert manifest["platform_coverage"]["missing_expected_platforms"] == ["alipay", "danjuan", "qieman", "bank-wealth"]
        proof = manifest["asset_boundary_proof"]
        assert proof["can_enter_china_wealth_lake"] is True
        assert proof["can_enter_data_quality_lake"] is False
        assert proof["can_feed_investor_wiki_evidence"] is True
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["generated_from"]["event_count"] == manifest["usable_event_count"]
        assert evidence["generated_from"]["gap_event_count"] == 0


def test_collect_without_input_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        event = json.loads((out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["kind"] == "profile"
        assert event["time"]
        assert event["data"]["subtype"] == "collector_gap"
        assert event["data"]["gap"] == "china_wealth_authorized_input_missing"
        assert event["data"]["status"] == "needs_china_wealth_authorized_input"
        assert event["data"]["profile_type"] == "china_wealth_authorized_input_missing"
        assert event["data"]["business_records_written"] is False
        assert event["data"]["payment_or_transfer_performed"] is False
        assert event["wiki_targets"] == ["collectorx.data_quality.collection_gaps"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["usable_event_count"] == 0
        assert manifest["asset_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["can_enter_china_wealth_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is False
        assert manifest["collection_audit"]["resolved_input_file_count"] == 0
        assert manifest["collection_audit"]["complete_asset_boundary_claimed"] is False
        proof = manifest["asset_boundary_proof"]
        assert proof["proof_scope"] == "none"
        assert proof["overall_proof_level"] == "no_authorized_asset_evidence"
        assert proof["complete_asset_boundary_claimed"] is False
        assert proof["can_enter_china_wealth_lake"] is False
        assert proof["can_enter_data_quality_lake"] is True
        assert proof["can_feed_investor_wiki_evidence"] is False
        assert proof["missing_global_requirements"] == ["authorized_asset_input"]
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["generated_from"]["event_count"] == 0
        assert evidence["generated_from"]["raw_event_count"] == 1
        assert evidence["generated_from"]["gap_event_count"] == 1
        assert evidence["coverage_summary"]["asset_value_summary"] == {}
        subprocess.run(
            [sys.executable, str(PACKAGE_VALIDATOR), str(out), "--collector", "china-wealth-assets"],
            check=True,
            text=True,
            capture_output=True,
        )


def test_collects_mixed_platform_json_and_sanitizes_raw() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "wealth.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                {
                    "assets": [
                        {"平台": "支付宝", "类型": "资产快照", "总资产": "12345.67", "可用余额": "456.7", "token": "must-not-leak"}
                    ],
                    "holdings": [
                        {"平台": "招商银行", "类型": "银行理财", "产品代码": "CMB001", "产品名称": "稳健理财", "持仓金额": "20000", "持有收益": "120.5"}
                    ],
                    "transactions": [
                        {"平台": "蛋卷", "交易类型": "赎回", "基金代码": "110022", "基金名称": "易方达消费", "确认金额": "800", "手续费": "1.2"}
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(json_path), "--out-dir", str(out), "--collected-at", "2026-07-08T12:00:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["data"]["subtype"] for event in events] == ["asset_snapshot", "wealth_holding", "fund_transaction"]
        assert [event["data"]["platform"] for event in events] == ["alipay", "bank-wealth", "danjuan"]
        assert events[0]["data"]["total_asset"] == 12345.67
        assert events[2]["data"]["transaction_amount"] == 800.0
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        assert "token" not in events[0]["data"]["raw"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_coverage"]["observed_platforms"] == ["alipay", "bank-wealth", "danjuan"]
        assert manifest["platform_coverage"]["real_account_validation"] is False


def test_collects_har_network_export_with_platform_audit_and_credential_stripping() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        har_path = root / "china-wealth-network.har"
        out = root / "out"
        har_path.write_text(
            json.dumps(
                {
                    "log": {
                        "entries": [
                            {
                                "request": {
                                    "url": "https://mobile.alipay.com/fund/asset/list?auth_token=must-not-leak",
                                    "headers": [
                                        {"name": "Cookie", "value": "ALIPAYJSESSIONID=must-not-leak"},
                                        {"name": "Authorization", "value": "Bearer must-not-leak"},
                                    ],
                                    "cookies": [{"name": "ALIPAYJSESSIONID", "value": "must-not-leak"}],
                                },
                                "response": {
                                    "status": 200,
                                    "headers": [{"name": "Set-Cookie", "value": "session=must-not-leak"}],
                                    "content": {
                                        "mimeType": "application/json",
                                        "text": json.dumps(
                                            {
                                                "success": True,
                                                "data": {
                                                    "holdings": [
                                                        {
                                                            "account_name": "alipay-main",
                                                            "type": "货币基金",
                                                            "fund_code": "000001",
                                                            "fund_name": "余额宝货币",
                                                            "shares": "1000",
                                                            "unit_nav": "1.23456",
                                                            "holding_amount": "1234.56",
                                                            "profit": "12.3",
                                                            "cookie": "must-not-leak",
                                                        }
                                                    ]
                                                },
                                            },
                                            ensure_ascii=False,
                                        ),
                                    },
                                },
                            },
                            {
                                "request": {
                                    "url": "https://fundmobapi.eastmoney.com/FundMApi/FundTrade/Records?token=must-not-leak",
                                },
                                "response": {
                                    "status": 200,
                                    "content": {
                                        "mimeType": "application/json",
                                        "text": json.dumps(
                                            {
                                                "data": {
                                                    "transactions": [
                                                        {
                                                            "account": "tt-001",
                                                            "transaction_type": "申购",
                                                            "fund_code": "110022",
                                                            "fund_name": "易方达消费",
                                                            "amount": "800",
                                                            "fee": "1.2",
                                                            "confirm_date": "2026-07-08",
                                                        }
                                                    ]
                                                }
                                            },
                                            ensure_ascii=False,
                                        ),
                                    },
                                },
                            },
                            {
                                "request": {"url": "https://example.com/profile"},
                                "response": {"status": 200, "content": {"mimeType": "application/json", "text": "{}"}},
                            },
                            {
                                "request": {"url": "https://www.cmbchina.com/wealth/list"},
                                "response": {"status": 200, "content": {"mimeType": "text/html", "text": "<html>not json</html>"}},
                            },
                        ]
                    }
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
                str(har_path),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T14:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["data"]["platform"] for event in events] == ["alipay", "tiantian-fund"]
        assert events[0]["data"]["subtype"] == "cash_management"
        assert events[0]["data"]["account"] == "alipay-main"
        assert events[0]["data"]["market_value"] == 1234.56
        assert events[0]["data"]["quantity"] == 1000.0
        assert events[1]["kind"] == "trade"
        assert events[1]["data"]["side"] == "buy"
        assert events[1]["data"]["transaction_amount"] == 800.0
        assert events[1]["data"]["fee"] == 1.2
        assert events[0]["raw_ref"]["parser"] == "har"
        assert events[0]["raw_ref"]["har_endpoint"] == "/fund/asset/list"
        assert events[1]["raw_ref"]["har_endpoint"] == "/FundMApi/FundTrade/Records"
        assert "?" not in events[0]["raw_ref"]["har_endpoint"]
        serialized_events = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized_events
        assert "auth_token" not in serialized_events
        assert "Authorization" not in serialized_events
        assert "Cookie" not in serialized_events

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["extension_counts"] == {".har": 1}
        assert audit["authorized_browser_network_export_used"] is True
        assert audit["browser_network_export_file_count"] == 1
        assert audit["har_entry_count"] == 4
        assert audit["har_investment_entry_count"] == 3
        assert audit["har_response_record_count"] == 2
        assert audit["har_skipped_entry_count"] == 2
        assert audit["har_skip_reason_counts"] == {
            "non_investment_platform_url": 1,
            "non_json_response": 1,
        }
        assert audit["har_platform_entry_counts"] == {"alipay": 1, "bank-wealth": 1, "tiantian-fund": 1}
        assert audit["har_endpoint_counts"] == {
            "/FundMApi/FundTrade/Records": 1,
            "/fund/asset/list": 1,
            "/wealth/list": 1,
        }
        assert audit["har_secret_material_stripped_count"] >= 4
        assert audit["har_query_string_stripped_count"] == 2
        assert manifest["platform_counts"] == {"alipay": 1, "tiantian-fund": 1}
        assert manifest["asset_value_summary"]["alipay"]["market_value"] == 1234.56
        assert manifest["asset_surface_summary"]["transaction_amount_by_side"] == {"buy": 800.0}


def test_collects_xlsx_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        from openpyxl import Workbook

        root = Path(tmp)
        xlsx_path = root / "qieman.xlsx"
        out = root / "out"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "且慢持仓"
        sheet.append(["平台", "类型", "基金代码", "基金名称", "持有份额", "单位净值", "持有金额", "持有收益率"])
        sheet.append(["且慢", "持仓", "000300", "沪深300指数", "300", "5.000", "1500", "12.5%"])
        workbook.save(xlsx_path)
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(xlsx_path), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        event = json.loads((out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["data"]["platform"] == "qieman"
        assert event["data"]["market_value"] == 1500.0
        assert event["data"]["pnl_rate"] == 0.125
        assert event["raw_ref"]["sheet"] == "且慢持仓"


def test_collects_legacy_xls_html_and_xml_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        html_xls = root / "alipay-fund.xls"
        xml_xls = root / "bank-wealth.xls"
        out = root / "out"

        html_xls.write_text(
            """
            <html>
              <body>
                <table>
                  <tr><th>平台</th><th>类型</th><th>基金代码</th><th>基金名称</th><th>持有份额</th><th>单位净值</th><th>持有金额</th><th>持有收益</th></tr>
                  <tr><td>支付宝</td><td>持仓</td><td>001234</td><td>测试基金</td><td>100</td><td>1.5</td><td>150</td><td>30</td></tr>
                </table>
              </body>
            </html>
            """,
            encoding="utf-8",
        )
        xml_xls.write_text(
            """<?xml version="1.0"?>
            <Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
              <Worksheet ss:Name="银行理财">
                <Table>
                  <Row>
                    <Cell><Data ss:Type="String">平台</Data></Cell>
                    <Cell><Data ss:Type="String">类型</Data></Cell>
                    <Cell><Data ss:Type="String">产品代码</Data></Cell>
                    <Cell><Data ss:Type="String">产品名称</Data></Cell>
                    <Cell><Data ss:Type="String">持仓金额</Data></Cell>
                  </Row>
                  <Row>
                    <Cell><Data ss:Type="String">招商银行</Data></Cell>
                    <Cell><Data ss:Type="String">银行理财</Data></Cell>
                    <Cell><Data ss:Type="String">CMB001</Data></Cell>
                    <Cell><Data ss:Type="String">稳健理财</Data></Cell>
                    <Cell><Data ss:Type="Number">20000</Data></Cell>
                  </Row>
                </Table>
              </Worksheet>
            </Workbook>
            """,
            encoding="utf-8",
        )

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )

        events = [json.loads(line) for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["data"]["platform"] for event in events] == ["alipay", "bank-wealth"]
        assert [event["data"]["subtype"] for event in events] == ["fund_holding", "wealth_holding"]
        assert events[0]["data"]["market_value"] == 150.0
        assert events[0]["raw_ref"]["sheet"] == "html_table_1"
        assert events[1]["data"]["market_value"] == 20000.0
        assert events[1]["raw_ref"]["sheet"] == "银行理财"

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_audit"]["extension_counts"] == {".xls": 2}
        assert manifest["platform_coverage"]["observed_platforms"] == ["alipay", "bank-wealth"]
        assert manifest["asset_value_summary"] == {
            "alipay": {"market_value": 150.0},
            "bank-wealth": {"market_value": 20000.0},
        }


def test_collects_pdf_statement_tables_with_pdf_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

        root = Path(tmp)
        pdf_path = root / "bank-wealth-statement.pdf"
        out = root / "out"

        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        table = Table(
            [
                ["platform", "account", "type", "product_code", "product_name", "market_value", "total_asset", "date"],
                ["bank", "cmb-001", "bank wealth", "CMB008", "Stable Wealth", "20000.50", "", "2026-07-09"],
                ["alipay", "ali-main", "asset snapshot", "", "", "", "12345.67", "2026-07-09"],
            ]
        )
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ]
            )
        )
        doc.build([table])

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(pdf_path),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-09T10:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = [json.loads(line) for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["data"]["platform"] for event in events] == ["bank-wealth", "alipay"]
        assert [event["data"]["subtype"] for event in events] == ["wealth_holding", "asset_snapshot"]
        assert events[0]["data"]["account"] == "cmb-001"
        assert events[0]["data"]["product_code"] == "CMB008"
        assert events[0]["data"]["market_value"] == 20000.5
        assert events[1]["data"]["account"] == "ali-main"
        assert events[1]["data"]["total_asset"] == 12345.67
        assert events[0]["raw_ref"]["parser"] == "pdfplumber"
        assert events[0]["raw_ref"]["pdf_page"] == 1
        assert events[0]["raw_ref"]["pdf_table"] == 1

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["extension_counts"] == {".pdf": 1}
        assert audit["pdf_parser_available"] is True
        assert audit["pdf_file_count"] == 1
        assert audit["pdf_page_count"] == 1
        assert audit["pdf_table_count"] == 1
        assert audit["pdf_table_record_count"] == 2
        assert audit["pdf_text_ocr_used"] is False
        assert audit["pdf_parse_error_count"] == 0
        assert manifest["asset_value_summary"] == {
            "alipay": {"total_asset": 12345.67},
            "bank-wealth": {"market_value": 20000.5},
        }
        proof = manifest["asset_boundary_proof"]
        assert proof["overall_proof_level"] == "medium_partial_asset_boundary"
        assert proof["complete_asset_boundary_claimed"] is False


def test_syncs_package_to_soulmirror_lake() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "fund.csv"
        out = root / "out"
        soulmirror = root / "soulmirror"
        csv_path.write_text("平台,类型,基金代码,基金名称,持仓金额\n天天基金,持仓,000001,华夏成长混合,1234\n", encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(csv_path),
                "--out-dir",
                str(out),
                "--sync-soulmirror",
                "--soulmirror-home",
                str(soulmirror),
                "--collected-at",
                "2026-07-08T13:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        assert (soulmirror / "lake" / "china-wealth-assets" / "events.jsonl").exists()
        assert (soulmirror / "lake" / "china-wealth-assets" / "latest" / "manifest.json").exists()
        assert (soulmirror / "lake" / "china-wealth-assets" / "latest" / "soulmirror_sync.json").exists()


def test_manifest_reports_expected_platform_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "all-platforms.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                {
                    "holdings": [
                        {"平台": "支付宝", "类型": "持仓", "基金代码": "000001", "基金名称": "支付宝基金", "持仓金额": "100"},
                        {"平台": "天天基金", "类型": "持仓", "基金代码": "000002", "基金名称": "天天基金", "持仓金额": "200"},
                        {"平台": "蛋卷", "类型": "持仓", "基金代码": "000003", "基金名称": "蛋卷基金", "持仓金额": "300"},
                        {"平台": "且慢", "类型": "持仓", "基金代码": "000004", "基金名称": "且慢基金", "持仓金额": "400"},
                        {"平台": "招商银行", "类型": "银行理财", "产品代码": "CMB005", "产品名称": "招行理财", "持仓金额": "500"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(json_path), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        coverage = manifest["platform_coverage"]
        assert coverage["missing_expected_platforms"] == []
        assert coverage["complete_expected_platforms_observed"] is True
        assert coverage["real_account_validation"] is False


def test_collects_five_platform_offline_fixture_with_boundary_and_secret_guards() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(FIVE_PLATFORM_FIXTURE),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-09T18:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = read_events(out)
        assert len(events) == 5
        assert [event["data"]["platform"] for event in events] == [
            "alipay",
            "tiantian-fund",
            "danjuan",
            "qieman",
            "bank-wealth",
        ]
        assert [event["data"]["subtype"] for event in events] == [
            "asset_snapshot",
            "fund_holding",
            "fund_transaction",
            "cash_management",
            "wealth_holding",
        ]
        assert [event["kind"] for event in events] == ["other", "holding", "trade", "holding", "holding"]

        by_platform = {event["data"]["platform"]: event for event in events}
        assert by_platform["alipay"]["data"]["total_asset"] == 12500.5
        assert by_platform["alipay"]["data"]["available_cash"] == 350.25
        assert by_platform["tiantian-fund"]["data"]["product_code"] == "000001"
        assert by_platform["tiantian-fund"]["data"]["quantity"] == 1000.0
        assert by_platform["tiantian-fund"]["data"]["nav"] == 1.234
        assert by_platform["tiantian-fund"]["data"]["market_value"] == 1234.0
        assert by_platform["danjuan"]["data"]["side"] == "buy"
        assert by_platform["danjuan"]["data"]["transaction_amount"] == 800.0
        assert by_platform["danjuan"]["data"]["fee"] == 1.2
        assert by_platform["qieman"]["data"]["subtype"] == "cash_management"
        assert by_platform["qieman"]["data"]["market_value"] == 5000.0
        assert by_platform["bank-wealth"]["data"]["product_code"] == "CMB-WM-008"
        assert by_platform["bank-wealth"]["data"]["market_value"] == 20000.0

        for event in events:
            assert_sensitive_terms_absent_from_values(event["data"])
            assert_sensitive_keys_absent(event["data"].get("raw", {}))

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 5
        assert manifest["usable_event_count"] == 5
        assert manifest["asset_event_count"] == 5
        assert manifest["gap_event_count"] == 0
        assert manifest["platform_counts"] == {
            "alipay": 1,
            "bank-wealth": 1,
            "danjuan": 1,
            "qieman": 1,
            "tiantian-fund": 1,
        }
        coverage = manifest["platform_coverage"]
        assert coverage["observed_platforms"] == ["alipay", "bank-wealth", "danjuan", "qieman", "tiantian-fund"]
        assert coverage["missing_expected_platforms"] == []
        assert coverage["complete_expected_platforms_observed"] is True
        assert coverage["real_account_validation"] is False

        field_counts = manifest["field_coverage"]["field_counts"]
        assert field_counts["platform"] == 5
        assert field_counts["account"] == 5
        assert field_counts["product_code"] == 4
        assert field_counts["product_name"] == 4
        assert field_counts["market_value"] == 3
        assert field_counts["total_asset"] == 1
        assert field_counts["available_cash"] == 1
        assert field_counts["cost"] == 2
        assert field_counts["pnl"] == 3
        assert field_counts["transaction_amount"] == 1
        assert field_counts["fee"] == 1
        assert field_counts["side"] == 5

        surface_summary = manifest["asset_surface_summary"]
        assert surface_summary["missing_expected_asset_surfaces"] == []
        assert surface_summary["kind_counts"] == {"holding": 3, "other": 1, "trade": 1}
        assert surface_summary["holding_event_count"] == 3
        assert surface_summary["transaction_event_count"] == 1
        assert surface_summary["asset_snapshot_event_count"] == 1
        assert surface_summary["transaction_side_counts"] == {"buy": 1}
        assert surface_summary["platform_surface_matrix"] == {
            "alipay": {"asset_snapshot": 1},
            "bank-wealth": {"wealth_holding": 1},
            "danjuan": {"fund_transaction": 1},
            "qieman": {"cash_management": 1},
            "tiantian-fund": {"fund_holding": 1},
        }

        account_summary = manifest["account_boundary_summary"]
        assert account_summary["observed_account_group_count"] == 5
        assert account_summary["observed_named_account_group_count"] == 5
        assert account_summary["unknown_account_event_count"] == 0
        assert account_summary["complete_account_boundary_claimed"] is False
        assert account_summary["requires_real_account_validation"] is True

        proof = manifest["asset_boundary_proof"]
        assert proof["proof_scope"] == "partial_authorized_input"
        assert proof["overall_proof_level"] == "medium_partial_asset_boundary"
        assert proof["complete_asset_boundary_claimed"] is False
        assert proof["requires_real_account_validation"] is True
        assert proof["missing_expected_platforms"] == []
        assert proof["missing_global_requirements"] == []
        assert proof["account_proof_level_counts"] == {"medium_partial_account_boundary": 5}
        assert manifest["evidence_policy"]["complete_asset_boundary_claimed"] is False
        assert manifest["evidence_policy"]["real_account_validation"] is False
        assert manifest["evidence_policy"]["does_not_place_orders"] is True
        assert manifest["evidence_policy"]["does_not_move_money"] is True

        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["generated_from"]["event_count"] == 5
        assert evidence["generated_from"]["gap_event_count"] == 0
        assert evidence["coverage_summary"]["platform_coverage"]["missing_expected_platforms"] == []
        assert evidence["coverage_summary"]["platform_coverage"]["real_account_validation"] is False
        assert evidence["coverage_summary"]["asset_boundary_proof"]["complete_asset_boundary_claimed"] is False
        assert evidence["coverage_summary"]["asset_surface_summary"]["missing_expected_asset_surfaces"] == []

        manifest_without_audit = {key: value for key, value in manifest.items() if key != "collection_audit"}
        assert_sensitive_terms_absent_from_values(events)
        assert_sensitive_terms_absent_from_values(manifest_without_audit)
        assert_sensitive_terms_absent_from_values(evidence)
        assert_secret_marker_absent_from_package(out)

        subprocess.run(
            [sys.executable, str(PACKAGE_VALIDATOR), str(out), "--collector", "china-wealth-assets"],
            check=True,
            text=True,
            capture_output=True,
        )


def test_collects_zip_package_with_value_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        zip_path = root / "wealth-package.zip"
        out = root / "out"
        with zipfile.ZipFile(zip_path, "w") as package:
            package.writestr(
                "alipay/holding.csv",
                "平台,类型,基金代码,基金名称,持有份额,单位净值,持有金额,持仓成本,持有收益\n"
                "支付宝,持仓,001234,测试基金,100,1.5,150,120,30\n",
            )
            package.writestr("../escape.csv", "平台,类型,基金代码,基金名称,持有金额\n天天基金,持仓,000001,应跳过,999\n")

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(zip_path), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["data"]["platform"] == "alipay"
        assert events[0]["data"]["market_value"] == 150.0
        assert events[0]["raw_ref"]["archive_member"] == "alipay/holding.csv"
        assert events[0]["raw_ref"]["member_row"] == 1
        serialized = json.dumps(events, ensure_ascii=False)
        assert "应跳过" not in serialized
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["archive_member_event_count"] == 1
        assert manifest["collection_audit"]["archive_member_count"] == 2
        assert manifest["collection_audit"]["skipped_archive_member_count"] == 1
        assert manifest["collection_audit"]["extension_counts"] == {".zip": 1}
        assert manifest["collection_audit"]["parsed_record_count"] == 1
        assert manifest["collection_audit"]["emitted_event_count"] == 1
        assert manifest["asset_value_summary"]["alipay"]["market_value"] == 150.0
        assert manifest["field_coverage"]["field_counts"]["market_value"] == 1
        assert manifest["evidence_policy"]["complete_asset_boundary_claimed"] is False


def test_manifest_reports_account_asset_currency_and_transaction_boundaries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "multi-account.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                {
                    "records": [
                        {"平台": "支付宝", "账户名称": "alipay-main", "类型": "资产快照", "总资产": "10000", "可用余额": "500", "币种": "CNY"},
                        {"平台": "支付宝", "账户名称": "alipay-main", "类型": "货币基金", "产品名称": "余额宝", "持有金额": "2000", "币种": "CNY"},
                        {"平台": "天天基金", "基金账号": "tt-001", "类型": "持仓", "基金代码": "000001", "基金名称": "测试混合", "持仓金额": "3000", "持仓成本": "2500", "持有收益": "500", "币种": "CNY"},
                        {"平台": "蛋卷", "账户名称": "dj-001", "交易类型": "申购", "基金代码": "110022", "基金名称": "测试消费", "确认金额": "800", "手续费": "1", "币种": "CNY"},
                        {"平台": "且慢", "账户名称": "qm-001", "交易类型": "赎回", "基金代码": "000300", "基金名称": "测试指数", "确认金额": "120", "币种": "USD"},
                        {"平台": "招商银行", "理财账号": "cmb-001", "类型": "银行理财", "产品代码": "CMB001", "产品名称": "稳健理财", "持仓金额": "5000", "币种": "CNY"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(json_path), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        account_summary = manifest["account_boundary_summary"]
        assert account_summary["account_boundary_scope"] == "partial_authorized_input"
        assert account_summary["observed_account_group_count"] == 5
        assert account_summary["observed_named_account_group_count"] == 5
        assert account_summary["unknown_account_event_count"] == 0
        assert account_summary["complete_account_boundary_claimed"] is False
        assert account_summary["requires_real_account_validation"] is True

        alipay_account = next(account for account in account_summary["accounts"] if account["platform"] == "alipay")
        assert alipay_account["account_ref"] == "alipay-main"
        assert alipay_account["subtype_counts"] == {"asset_snapshot": 1, "cash_management": 1}
        assert alipay_account["value_summary"]["CNY"]["total_asset"] == 10000.0
        assert alipay_account["value_summary"]["CNY"]["market_value"] == 2000.0

        surface_summary = manifest["asset_surface_summary"]
        assert surface_summary["missing_expected_asset_surfaces"] == []
        assert surface_summary["holding_event_count"] == 3
        assert surface_summary["transaction_event_count"] == 2
        assert surface_summary["asset_snapshot_event_count"] == 1
        assert surface_summary["transaction_side_counts"] == {"buy": 1, "sell": 1}
        assert surface_summary["transaction_amount_by_side"] == {"buy": 800.0, "sell": 120.0}
        assert surface_summary["platform_surface_matrix"]["bank-wealth"] == {"wealth_holding": 1}

        currency_summary = manifest["currency_summary"]
        assert currency_summary["currency_counts"] == {"CNY": 5, "USD": 1}
        assert currency_summary["value_fields_by_currency"]["CNY"]["market_value"] == 10000.0
        assert currency_summary["value_fields_by_currency"]["CNY"]["total_asset"] == 10000.0
        assert currency_summary["value_fields_by_currency"]["USD"]["transaction_amount"] == 120.0
        assert manifest["evidence_policy"]["personal_authorized_assets_only"] is True
        assert manifest["evidence_policy"]["does_not_place_orders"] is True
        assert manifest["evidence_policy"]["does_not_move_money"] is True
        proof = manifest["asset_boundary_proof"]
        assert proof["proof_scope"] == "partial_authorized_input"
        assert proof["overall_proof_level"] == "strong_partial_asset_boundary"
        assert proof["complete_asset_boundary_claimed"] is False
        assert proof["requires_real_account_validation"] is True
        assert proof["missing_expected_platforms"] == []
        assert proof["missing_global_requirements"] == []
        assert proof["account_proof_level_counts"] == {
            "medium_partial_account_boundary": 4,
            "strong_partial_account_boundary": 1,
        }
        alipay_proof = next(item for item in proof["account_proofs"] if item["platform"] == "alipay")
        assert alipay_proof["account_ref"] == "alipay-main"
        assert alipay_proof["proof_level"] == "strong_partial_account_boundary"
        assert alipay_proof["has_asset_snapshot"] is True
        assert alipay_proof["has_holding_surface"] is True
        assert alipay_proof["has_transaction_surface"] is False
        assert alipay_proof["missing_requirements"] == ["transaction_surface"]
        danjuan_proof = next(item for item in proof["account_proofs"] if item["platform"] == "danjuan")
        assert danjuan_proof["proof_level"] == "medium_partial_account_boundary"
        assert danjuan_proof["missing_requirements"] == ["asset_snapshot", "holding_surface"]
        bank_platform = next(item for item in proof["platform_proofs"] if item["platform"] == "bank-wealth")
        assert bank_platform["proof_level"] == "medium_partial_account_boundary"
        assert bank_platform["missing_requirements"] == ["asset_snapshot", "transaction_surface"]
        summary = (out / "SUMMARY.md").read_text(encoding="utf-8")
        assert "资产边界证明：`strong_partial_asset_boundary`" in summary
        assert "缺失平台：`none`" in summary

        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["account_boundary_summary"]["observed_named_account_group_count"] == 5
        assert evidence["coverage_summary"]["asset_surface_summary"]["missing_expected_asset_surfaces"] == []
        assert evidence["coverage_summary"]["asset_boundary_proof"]["overall_proof_level"] == "strong_partial_asset_boundary"
        assert evidence["coverage_summary"]["asset_boundary_proof"]["complete_asset_boundary_claimed"] is False
        assert evidence["coverage_summary"]["dimension_count"] == 7
        assert evidence["coverage_summary"]["subdimension_count"] == 20
        portfolio_preference = next(
            child
            for dimension in evidence["dimensions"]
            for child in dimension["children"]
            if child["subdimension_id"] == "inv-portfolio-preference"
        )
        assert portfolio_preference["support_level"] == "strong"
        assert portfolio_preference["evidence_count"] == 4


def test_scope_policy_filters_authorized_asset_records() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "scoped-wealth.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                {
                    "records": [
                        {"平台": "支付宝", "账户名称": "ali-main", "类型": "货币基金", "基金代码": "000001", "基金名称": "余额宝货币", "持有金额": "1000", "币种": "CNY"},
                        {"平台": "天天基金", "账户名称": "ali-main", "类型": "货币基金", "基金代码": "000001", "基金名称": "余额宝货币", "持有金额": "2000", "币种": "CNY"},
                        {"平台": "支付宝", "账户名称": "ali-other", "类型": "货币基金", "基金代码": "000001", "基金名称": "余额宝货币", "持有金额": "3000", "币种": "CNY"},
                        {"平台": "支付宝", "账户名称": "ali-main", "类型": "持仓", "基金代码": "000001", "基金名称": "余额宝货币", "持有金额": "4000", "币种": "CNY"},
                        {"平台": "支付宝", "账户名称": "ali-main", "类型": "货币基金", "基金代码": "000002", "基金名称": "余额宝货币", "持有金额": "5000", "币种": "CNY"},
                        {"平台": "支付宝", "账户名称": "ali-main", "类型": "货币基金", "基金代码": "000001", "基金名称": "普通货币", "持有金额": "6000", "币种": "CNY"},
                        {"平台": "支付宝", "账户名称": "ali-main", "类型": "货币基金", "基金代码": "000001", "基金名称": "余额宝货币", "持有金额": "7000", "币种": "USD"},
                        {"平台": "支付宝", "账户名称": "ali-main", "类型": "货币基金", "基金代码": "000001", "基金名称": "余额宝私人货币", "持有金额": "8000", "币种": "CNY"},
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
                str(json_path),
                "--out-dir",
                str(out),
                "--allow-platform",
                "alipay",
                "--allow-account",
                "ali-main",
                "--allow-subtype",
                "cash_management",
                "--allow-product-code",
                "000001",
                "--allow-product-name",
                "余额宝",
                "--allow-currency",
                "CNY",
                "--deny-keyword",
                "私人",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["data"]["platform"] == "alipay"
        assert events[0]["data"]["account"] == "ali-main"
        assert events[0]["data"]["subtype"] == "cash_management"
        assert events[0]["data"]["product_code"] == "000001"
        assert events[0]["data"]["product_name"] == "余额宝货币"
        assert events[0]["data"]["market_value"] == 1000.0

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "events_collected"
        assert manifest["usable_event_count"] == 1
        assert manifest["asset_event_count"] == 1
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_enter_china_wealth_lake"] is True
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is False
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is True
        audit = manifest["collection_audit"]
        assert audit["candidate_record_count"] == 8
        assert audit["parsed_record_count"] == 8
        assert audit["emitted_event_count"] == 1
        assert audit["scope_policy_filtered_record_count"] == 7
        assert audit["china_wealth_scope_policy"]["enabled"] is True
        assert audit["china_wealth_scope_policy"]["allow_platforms"] == ["alipay"]
        assert audit["china_wealth_scope_policy"]["allow_subtypes"] == ["cash_management"]
        assert audit["scope_policy_filter_reason_counts"] == {
            "account_not_allowed": 1,
            "currency_not_allowed": 1,
            "keyword_denied": 1,
            "platform_not_allowed": 1,
            "product_code_not_allowed": 1,
            "product_name_not_allowed": 1,
            "subtype_not_allowed": 1,
        }
        assert audit["path_results"][0]["scope_policy_filter_status"] == "partially_filtered"
        boundary = manifest["asset_boundary_proof"]["authorization_scope_boundary"]
        assert boundary["candidate_record_count"] == 8
        assert boundary["scope_policy_filtered_record_count"] == 7
        assert boundary["china_wealth_scope_policy_filtered_all"] is False


def test_scope_policy_filtered_all_readiness() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "filtered-all.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                {"records": [{"平台": "天天基金", "账户名称": "tt-main", "类型": "持仓", "基金代码": "000001", "基金名称": "测试基金", "持仓金额": "100"}]},
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
                str(json_path),
                "--out-dir",
                str(out),
                "--allow-platform",
                "alipay",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        event_lines = (out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(event_lines) == 1
        event = json.loads(event_lines[0])
        assert event["kind"] == "profile"
        assert event["time"]
        assert event["data"]["subtype"] == "collector_gap"
        assert event["data"]["gap"] == "china_wealth_scope_policy_filtered_all"
        assert event["data"]["status"] == "scope_policy_filtered_all"
        assert event["data"]["candidate_record_count"] == 1
        assert event["data"]["retained_record_count"] == 0
        assert event["data"]["filtered_record_count"] == 1
        assert event["data"]["filter_reason_counts"] == {"platform_not_allowed": 1}
        assert event["data"]["business_records_written"] is False
        assert event["wiki_targets"] == ["collectorx.data_quality.collection_gaps"]
        assert "product_code" not in event["data"]
        assert "market_value" not in event["data"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["usable_event_count"] == 0
        assert manifest["asset_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["can_enter_china_wealth_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is False
        assert manifest["collection_readiness"]["usable_event_count"] == 0
        assert manifest["collection_readiness"]["asset_boundary_scope"] == "scope_policy_excluded_all"
        audit = manifest["collection_audit"]
        assert audit["candidate_record_count"] == 1
        assert audit["scope_policy_filtered_record_count"] == 1
        assert audit["china_wealth_scope_policy_filtered_all"] is True
        assert audit["scope_policy_filter_reason_counts"] == {"platform_not_allowed": 1}
        assert audit["path_results"][0]["status"] == "filtered_by_scope_policy"
        proof = manifest["asset_boundary_proof"]
        assert proof["overall_proof_level"] == "scope_policy_filtered_all"
        assert proof["proof_scope"] == "scope_policy_excluded_all"
        assert proof["can_enter_china_wealth_lake"] is False
        assert proof["can_enter_data_quality_lake"] is True
        assert proof["can_feed_investor_wiki_evidence"] is False
        assert proof["authorization_scope_boundary"]["china_wealth_scope_policy_filtered_all"] is True
        assert proof["missing_global_requirements"] == ["scope_policy_retained_records"]
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["generated_from"]["event_count"] == 0
        assert evidence["generated_from"]["raw_event_count"] == 1
        assert evidence["generated_from"]["gap_event_count"] == 1
        assert evidence["coverage_summary"]["support_level_counts"] == {"none": 20}
        assert evidence["coverage_summary"]["asset_value_summary"] == {}
        subprocess.run(
            [sys.executable, str(PACKAGE_VALIDATOR), str(out), "--collector", "china-wealth-assets"],
            check=True,
            text=True,
            capture_output=True,
        )


if __name__ == "__main__":
    test_collect_fund_holding_and_transaction()
    test_collect_without_input_gap()
    test_collects_mixed_platform_json_and_sanitizes_raw()
    test_collects_har_network_export_with_platform_audit_and_credential_stripping()
    test_collects_xlsx_exports()
    test_collects_legacy_xls_html_and_xml_exports()
    test_collects_pdf_statement_tables_with_pdf_audit()
    test_syncs_package_to_soulmirror_lake()
    test_manifest_reports_expected_platform_coverage()
    test_collects_five_platform_offline_fixture_with_boundary_and_secret_guards()
    test_collects_zip_package_with_value_summary()
    test_manifest_reports_account_asset_currency_and_transaction_boundaries()
    test_scope_policy_filters_authorized_asset_records()
    test_scope_policy_filtered_all_readiness()
    print("china-wealth-assets tests passed.")
