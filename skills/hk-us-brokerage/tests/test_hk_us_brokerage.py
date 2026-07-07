#!/usr/bin/env python3
"""Tests for hk-us-brokerage collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hk_us_brokerage.py"


def test_collect_brokerage_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "futu_positions_trades.csv"
        json_path = root / "ibkr_assets_orders.json"
        out = root / "out"
        csv_path.write_text(
            "\n".join(
                [
                    "record_type,broker,account,currency,market,symbol,name,side,quantity,price,avg_cost,market_value,amount,fees,time",
                    "position,富途,ACC-1,HKD,HK,00700,Tencent,,100,380.5,350.0,38050,,,2026-07-08T09:00:00+08:00",
                    "execution,富途,ACC-1,USD,US,AAPL,Apple,buy,10,190.2,,1902,1902,1.2,2026-07-08T10:00:00+08:00",
                    "cashflow,富途,ACC-1,USD,,,,,,1000,,,,deposit,,2026-07-08T11:00:00+08:00",
                ]
            ),
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "record_type": "asset",
                            "broker": "IBKR",
                            "account_id": "U123",
                            "currency": "USD",
                            "total_assets": "50000",
                            "cash": "12000",
                            "buying_power": "24000",
                        },
                        {
                            "record_type": "order",
                            "broker": "IBKR",
                            "account_id": "U123",
                            "symbol": "TSLA",
                            "side": "sell",
                            "order_quantity": "5",
                            "limit_price": "260",
                            "status": "submitted",
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
                str(root),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T04:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "hk-us-brokerage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 5
        assert {event["data"]["subtype"] for event in events} == {"asset_snapshot", "cashflow", "execution", "order", "position"}
        assert {event["kind"] for event in events} == {"holding", "other", "trade"}
        position = next(event for event in events if event["data"]["subtype"] == "position")
        assert position["data"]["symbol"] == "00700"
        assert position["data"]["market_value"] == 38050.0
        execution = next(event for event in events if event["data"]["subtype"] == "execution")
        assert execution["data"]["side"] == "buy"
        assert execution["data"]["amount"] == 1902.0
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_hk_us_trade_boundary"] is False
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["strong_trade_source"] is True
        assert evidence["generated_from"]["event_count"] == 5


def test_collect_nested_sections_and_workbook() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "tiger_full_statement.json"
        workbook_path = root / "futu_statement.xlsx"
        ibkr_zip = root / "ibkr_activity.zip"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "broker": "Tiger",
                    "account_id": "T-888",
                    "assets": [
                        {
                            "currency": "USD",
                            "Total Assets": "US$100,000.50",
                            "Net Liquidation": "US$100,000.50",
                            "Cash": "12000",
                            "Buying Power": "24000",
                            "Margin Requirement": "3000",
                            "Maintenance Margin": "2000",
                        }
                    ],
                    "positions": [{"symbol": "NVDA", "quantity": "3", "avg_cost": "800", "market_value": "2700"}],
                    "executions": [{"symbol": "MSFT", "side": "BOT", "filled_qty": "2", "avg_price": "400", "amount": "800", "fees": "1.1", "settlement_date": "2026-07-10"}],
                    "orders": [{"symbol": "TSLA", "side": "SELL", "order_qty": "4", "status": "Cancelled"}],
                    "cashflows": [{"type": "入金", "amount": "5000", "profile": {"token": "must-not-leak"}}],
                    "dividends": [{"symbol": "AAPL", "gross_amount": "12.3", "withholding_tax": "(1.23)", "net_amount": "11.07", "ex_date": "2026-06-20", "pay_date": "2026-07-08"}],
                    "fx": [{"from_currency": "USD", "to_currency": "HKD", "from_amount": "100", "to_amount": "780", "exchange_rate": "7.8"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        workbook = openpyxl.Workbook()
        positions = workbook.active
        positions.title = "Positions"
        positions.append(["Broker", "Account ID", "Symbol", "Qty", "Avg Cost", "Market Value", "Unrealized PnL"])
        positions.append(["富途", "F-1", "00700", 100, 350, 38050, 3050])
        dividends = workbook.create_sheet("Dividends")
        dividends.append(["Broker", "Account ID", "Symbol", "Gross Amount", "Tax", "Net Amount", "Pay Date"])
        dividends.append(["富途", "F-1", "00700", 100, 10, 90, "2026-07-08"])
        workbook.save(workbook_path)
        with zipfile.ZipFile(ibkr_zip, "w") as archive:
            archive.writestr(
                "statements/ibkr_asset.json",
                json.dumps(
                    {
                        "records": [
                            {
                                "record_type": "asset",
                                "broker": "IBKR",
                                "account_id": "U123",
                                "currency": "USD",
                                "total_assets": "25000",
                                "cash": "5000",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"broker": "IBKR", "record_type": "order"}], ensure_ascii=False))

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "hk-us-brokerage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        subtype_counts = {}
        for event in events:
            subtype = event["data"]["subtype"]
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
        assert subtype_counts == {
            "asset_snapshot": 2,
            "cashflow": 1,
            "dividend": 2,
            "execution": 1,
            "fx": 1,
            "order": 1,
            "position": 2,
        }
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        asset = next(event for event in events if event["data"].get("broker") == "tiger" and event["data"]["subtype"] == "asset_snapshot")
        assert asset["data"]["net_liquidation"] == 100000.5
        cancelled_order = next(event for event in events if event["data"].get("symbol") == "TSLA")
        assert cancelled_order["data"]["status"] == "cancelled"
        fx = next(event for event in events if event["data"]["subtype"] == "fx")
        assert fx["data"]["exchange_rate"] == 7.8
        assert fx["data"]["from_amount"] == 100.0
        workbook_dividend = next(event for event in events if event["data"].get("net_amount") == 90.0)
        assert workbook_dividend["data"]["broker"] == "futu"
        assert any(event["raw_ref"]["path"] == "ibkr_activity.zip::statements/ibkr_asset.json" for event in events)
        assert all("../unsafe" not in event["raw_ref"]["path"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["subtype_counts"]["position"] == 2
        assert manifest["broker_coverage"]["observed_expected_brokers"] == ["futu", "tiger", "ibkr"]
        assert manifest["broker_coverage"]["missing_expected_brokers"] == []
        assert manifest["trade_surface_coverage"]["observed_expected_subtypes"] == [
            "asset_snapshot",
            "position",
            "execution",
            "order",
            "cashflow",
            "dividend",
            "fx",
        ]
        assert manifest["trade_surface_coverage"]["missing_expected_subtypes"] == []
        assert manifest["field_coverage"]["missing_recommended_fields"] == []
        assert manifest["collection_readiness"]["broker_coverage_status"] == "all_expected_brokers_observed"
        assert manifest["collection_readiness"]["trade_surface_coverage_status"] == "all_expected_trade_surfaces_observed"
        assert manifest["collection_readiness"]["field_coverage_status"] == "all_expected_fields_observed"


if __name__ == "__main__":
    test_collect_brokerage_exports()
    test_collect_nested_sections_and_workbook()
    print("hk-us-brokerage tests passed.")
