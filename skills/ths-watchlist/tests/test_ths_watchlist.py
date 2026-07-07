#!/usr/bin/env python3
"""Tests for ths-watchlist collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ths_watchlist.py"


def read_events(out: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (out / "lake" / "ths-watchlist" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_collect_ths_watchlist_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "自选股.csv"
        json_path = root / "ths_watchlist.json"
        xlsx_path = root / "ths_watchlist.xlsx"
        text_path = root / "watchlist.txt"
        out = root / "out"
        csv_path.write_text(
            "证券代码,证券名称,分组,行业,备注,添加时间\n"
            "600519,贵州茅台,核心观察,白酒,长期跟踪,2026-07-08T09:00:00+08:00\n"
            "300750,宁德时代,新能源,电池,,2026-07-08T09:10:00+08:00\n",
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(
                {
                    "group": "AI",
                    "watchlist": [
                        {"code": "688981.SH", "name": "中芯国际", "tags": ["半导体"], "auth": {"token": "must-not-leak"}},
                        {"code": "000001", "name": "平安银行", "market": "SZ"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "港股观察"
        sheet.append(["代码", "名称", "备注"])
        sheet.append(["00700", "腾讯控股", "港股代码不会补 A 股市场"])
        workbook.save(xlsx_path)
        text_path.write_text("短线观察：002475 立讯精密\n忽略普通文字\n", encoding="utf-8")

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
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 6
        assert {event["collector"] for event in events} == {"ths-watchlist"}
        assert {event["kind"] for event in events} == {"watchlist"}
        assert all("investor.opportunity_watchlist.watchlist" in event["wiki_targets"] for event in events)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        maotai = next(event for event in events if event["data"]["symbol"] == "600519")
        assert maotai["data"]["market"] == "SH"
        assert maotai["data"]["group"] == "核心观察"
        smic = next(event for event in events if event["data"]["symbol"] == "688981")
        assert smic["data"]["tags"] == ["半导体"]
        tencent = next(event for event in events if event["data"]["symbol"] == "00700")
        assert tencent["data"]["market"] == "unknown"
        text_event = next(event for event in events if event["data"]["symbol"] == "002475")
        assert text_event["data"]["name"] == "短线观察： 立讯精密"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_ths_attention_universe"] is False
        assert manifest["market_counts"]["SH"] >= 2


def test_gap_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        assert events[0]["data"]["gap"] == "ths_watchlist_authorized_input_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False


if __name__ == "__main__":
    test_collect_ths_watchlist_exports()
    test_gap_event()
    print("ths-watchlist tests passed.")
