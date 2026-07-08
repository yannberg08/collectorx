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
        unsupported = root / "ignore.bin"
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
                                "currency": "HKD",
                                "total_assets": "25000",
                                "cash": "5000",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"broker": "IBKR", "record_type": "order"}], ensure_ascii=False))
            archive.writestr("..\\windows-traversal.json", json.dumps([{"broker": "IBKR", "record_type": "order"}], ensure_ascii=False))
            archive.writestr("C:\\unsafe.json", json.dumps([{"broker": "IBKR", "record_type": "order"}], ensure_ascii=False))
        unsupported.write_bytes(b"not a supported brokerage export")

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
        zip_event = next(event for event in events if event["data"].get("broker") == "ibkr")
        assert zip_event["raw_ref"]["path"] == f"{ibkr_zip}::statements/ibkr_asset.json"
        assert zip_event["raw_ref"]["source_archive"] == str(ibkr_zip)
        assert zip_event["raw_ref"]["archive_member"] == "statements/ibkr_asset.json"
        assert all("../unsafe" not in event["raw_ref"]["path"] for event in events)
        assert all("windows-traversal" not in event["raw_ref"]["path"] for event in events)
        assert all("C:/unsafe" not in event["raw_ref"]["path"] for event in events)
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
        assert manifest["strong_trade_surface_summary"]["strong_trade_event_count"] == 10
        assert manifest["strong_trade_surface_summary"]["asset_snapshot_count"] == 2
        assert manifest["strong_trade_surface_summary"]["events_with_margin"] == 1
        assert manifest["strong_trade_surface_summary"]["events_with_tax"] == 2
        account_boundary = manifest["account_boundary_summary"]
        assert account_boundary["account_id_count"] == 3
        assert account_boundary["accounts_by_broker"] == {
            "futu": ["F-1"],
            "ibkr": ["U123"],
            "tiger": ["T-888"],
        }
        assert account_boundary["event_counts_by_account"]["tiger:T-888"] == 7
        assert account_boundary["event_counts_by_account"]["futu:F-1"] == 2
        assert account_boundary["event_counts_by_account"]["ibkr:U123"] == 1
        assert account_boundary["missing_expected_subtypes_by_account"]["tiger:T-888"] == []
        assert account_boundary["full_surface_account_candidates"] == ["tiger:T-888"]
        assert account_boundary["complete_account_boundary_claimed"] is False
        currency_market = manifest["currency_market_summary"]
        assert currency_market["currency_count"] == 2
        assert currency_market["currency_counts"] == {"HKD": 2, "USD": 2}
        assert currency_market["fx_pair_counts"] == {"USD->HKD": 1}
        assert currency_market["multi_currency_observed"] is True
        fee_tax_margin = manifest["fee_tax_margin_summary"]
        assert fee_tax_margin["events_with_fees"] == 1
        assert fee_tax_margin["events_with_tax"] == 2
        assert fee_tax_margin["events_with_margin"] == 1
        assert fee_tax_margin["margin_requirement_by_currency"]["USD"] == 3000.0
        assert fee_tax_margin["maintenance_margin_by_currency"]["USD"] == 2000.0
        assert manifest["asset_value_summary"]["multi_currency_observed"] is True
        assert manifest["asset_value_summary"]["reported_total_assets_by_currency"]["USD"] == 100000.5
        assert manifest["asset_value_summary"]["reported_total_assets_by_currency"]["HKD"] == 25000.0
        assert manifest["asset_value_summary"]["reported_cash_by_currency"]["USD"] == 12000.0
        assert manifest["asset_value_summary"]["reported_cash_by_currency"]["HKD"] == 5000.0
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["resolved_input_file_count"] == 3
        assert manifest["source_audit"]["parsed_record_count"] == 10
        assert manifest["source_audit"]["emitted_event_count"] == 10
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
        assert manifest["evidence_policy"]["read_only_collection"] is True
        assert manifest["evidence_policy"]["order_side_effects_allowed"] is False
        assert manifest["collection_readiness"]["broker_coverage_status"] == "all_expected_brokers_observed"
        assert manifest["collection_readiness"]["trade_surface_coverage_status"] == "all_expected_trade_surfaces_observed"
        assert manifest["collection_readiness"]["field_coverage_status"] == "all_expected_fields_observed"
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["read_only_collection"] is True
        assert evidence["coverage_summary"]["order_side_effects_allowed"] is False
        assert evidence["coverage_summary"]["account_boundary_summary"]["full_surface_account_candidates"] == ["tiger:T-888"]
        assert evidence["coverage_summary"]["currency_market_summary"]["multi_currency_observed"] is True


def test_collect_zip_limit_counts_only_emitted_records() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "futu.zip"
        out = root / "out"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "positions.json",
                json.dumps(
                    [
                        {
                            "record_type": "position",
                            "broker": "Futu",
                            "account_id": "F-1",
                            "symbol": "AAPL",
                            "quantity": "10",
                        },
                        {
                            "record_type": "position",
                            "broker": "Futu",
                            "account_id": "F-1",
                            "symbol": "MSFT",
                            "quantity": "5",
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
        events = [json.loads(line) for line in (out / "lake" / "hk-us-brokerage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
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
                "2026-07-08T04:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "hk-us-brokerage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["data"]["gap"] == "hk_us_brokerage_authorized_input_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "needs_hk_us_brokerage_authorized_input"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["source_audit"]["input_count"] == 1
        assert manifest["source_audit"]["input_missing_count"] == 1
        assert manifest["source_audit"]["parsed_record_count"] == 0
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert manifest["source_audit"]["skipped_reason_counts"] == {"input_missing": 1}
        assert manifest["source_audit"]["path_results"][0]["status"] == "missing"


if __name__ == "__main__":
    test_collect_brokerage_exports()
    test_collect_nested_sections_and_workbook()
    test_collect_zip_limit_counts_only_emitted_records()
    test_collect_missing_input_writes_gap_audit()
    print("hk-us-brokerage tests passed.")
