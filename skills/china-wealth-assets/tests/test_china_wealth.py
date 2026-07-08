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
SCRIPT = ROOT / "scripts" / "china_wealth.py"


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
        assert manifest["collection_readiness"]["can_claim_complete_asset_boundary"] is False
        assert manifest["collection_readiness"]["asset_boundary_scope"] == "partial_authorized_input"
        assert manifest["platform_counts"] == {"tiantian-fund": 2}
        assert manifest["platform_coverage"]["missing_expected_platforms"] == ["alipay", "danjuan", "qieman", "bank-wealth"]


def test_collect_without_input_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        event = json.loads((out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["data"]["subtype"] == "collector_gap"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_audit"]["resolved_input_file_count"] == 0
        assert manifest["collection_audit"]["complete_asset_boundary_claimed"] is False


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

        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["account_boundary_summary"]["observed_named_account_group_count"] == 5
        assert evidence["coverage_summary"]["asset_surface_summary"]["missing_expected_asset_surfaces"] == []
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


if __name__ == "__main__":
    test_collect_fund_holding_and_transaction()
    test_collect_without_input_gap()
    test_collects_mixed_platform_json_and_sanitizes_raw()
    test_collects_xlsx_exports()
    test_syncs_package_to_soulmirror_lake()
    test_manifest_reports_expected_platform_coverage()
    test_collects_zip_package_with_value_summary()
    test_manifest_reports_account_asset_currency_and_transaction_boundaries()
    print("china-wealth-assets tests passed.")
