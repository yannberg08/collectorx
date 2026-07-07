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


def test_collect_without_input_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)], check=True, text=True, capture_output=True)
        event = json.loads((out / "lake" / "china-wealth-assets" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["data"]["subtype"] == "collector_gap"


if __name__ == "__main__":
    test_collect_fund_holding_and_transaction()
    test_collect_without_input_gap()
    print("china-wealth-assets tests passed.")
