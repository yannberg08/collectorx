#!/usr/bin/env python3
"""Tests for china-wealth-assets."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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


def test_collect_without_input_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        event = json.loads((out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["data"]["subtype"] == "collector_gap"


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


if __name__ == "__main__":
    test_collect_fund_holding_and_transaction()
    test_collect_without_input_gap()
    test_collects_mixed_platform_json_and_sanitizes_raw()
    test_collects_xlsx_exports()
    test_syncs_package_to_soulmirror_lake()
    print("china-wealth-assets tests passed.")
