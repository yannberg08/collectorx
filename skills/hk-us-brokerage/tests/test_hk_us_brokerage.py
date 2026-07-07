#!/usr/bin/env python3
"""Tests for hk-us-brokerage collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


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


if __name__ == "__main__":
    test_collect_brokerage_exports()
    print("hk-us-brokerage tests passed.")
