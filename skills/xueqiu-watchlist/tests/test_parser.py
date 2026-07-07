#!/usr/bin/env python3
"""Tests for xueqiu-watchlist collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from xueqiu.parser import parse_watchlist_csv


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xueqiu_query.py"


def read_events(out: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (out / "lake" / "xueqiu-watchlist" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_parse_csv() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        test_csv = Path(tmp) / "xueqiu.csv"
        test_csv.write_text(
            "代码,名称,行业,备注\n"
            "600519,贵州茅台,白酒,核心关注\n"
            "000858,五粮液,白酒,观察\n",
            encoding="utf-8",
        )
        records = parse_watchlist_csv(str(test_csv))
        assert len(records) == 2
        assert records[0]["code"] == "600519"
        assert records[0]["symbol"] == "SH600519"
        assert records[1]["code"] == "000858"
        assert records[1]["symbol"] == "SZ000858"


def test_collect_xueqiu_watchlist_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "xueqiu_watchlist.csv"
        json_path = root / "xueqiu_watchlist.json"
        xlsx_path = root / "xueqiu_watchlist.xlsx"
        text_path = root / "watchlist.txt"
        zip_path = root / "watchlist-package.zip"
        out = root / "out"

        csv_path.write_text(
            "代码,名称,分组,行业,备注,关注时间\n"
            "600519,贵州茅台,核心观察,白酒,长期跟踪,2026-07-08T09:00:00+08:00\n"
            "000858,五粮液,白酒池,白酒,估值观察,2026-07-08T09:10:00+08:00\n",
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(
                {
                    "group": "半导体",
                    "watchlist": [
                        {"symbol": "SH688981", "name": "中芯国际", "tags": ["芯片"], "auth": {"token": "must-not-leak"}},
                        {"symbol": "HK00700", "name": "腾讯控股", "market": "HK"},
                        {"name": "缺少代码的观察项"},
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
        sheet.append(["00700", "腾讯控股", "港股代码保持港股市场"])
        workbook.save(xlsx_path)
        text_path.write_text("短线观察：SZ002475 立讯精密\n忽略普通文字\n", encoding="utf-8")
        with zipfile.ZipFile(zip_path, "w") as package:
            package.writestr("nested/zip-watchlist.csv", "代码,名称,分组\n300750,宁德时代,新能源\n")
            package.writestr("../escape.csv", "代码,名称\n600000,浦发银行\n")

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
        assert len(events) == 7
        assert {event["collector"] for event in events} == {"xueqiu-watchlist"}
        assert {event["kind"] for event in events} == {"watchlist"}
        assert all("investor.opportunity_watchlist.watchlist" in event["wiki_targets"] for event in events)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        maotai = next(event for event in events if event["data"]["symbol"] == "SH600519")
        assert maotai["data"]["market"] == "SH"
        assert maotai["data"]["group"] == "核心观察"
        smic = next(event for event in events if event["data"]["symbol"] == "SH688981")
        assert smic["data"]["tags"] == ["芯片"]
        hk = [event for event in events if event["data"]["symbol"] == "HK00700"]
        assert len(hk) == 2
        assert all(event["data"]["market"] == "HK" for event in hk)
        text_event = next(event for event in events if event["data"]["symbol"] == "SZ002475")
        assert "立讯精密" in text_event["data"]["name"]
        zip_event = next(event for event in events if event["data"]["symbol"] == "SZ300750")
        assert zip_event["raw_ref"]["archive_member"] == "nested/zip-watchlist.csv"
        assert zip_event["raw_ref"]["member_row"] == 1
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_xueqiu_watchlist_boundary"] is False
        assert manifest["market_counts"]["HK"] == 2
        assert manifest["archive_member_event_count"] == 1
        assert manifest["evidence_policy"]["xueqiu_watchlist_is_strong_trade_source"] is False
        assert manifest["collection_audit"]["archive_member_count"] == 2
        assert manifest["collection_audit"]["skipped_archive_member_count"] == 1
        assert manifest["collection_audit"]["filtered_record_count"] >= 1
        assert manifest["field_coverage"]["fields"]["symbol"]["present"] == 7


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
        assert events[0]["data"]["gap"] == "xueqiu_watchlist_authorized_input_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False


def test_legacy_cli_export() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "xueqiu.csv"
        export_path = root / "watchlist.json"
        csv_path.write_text("代码,名称\n600519,贵州茅台\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPT), "--file", str(csv_path), "--export", str(export_path), "--list"],
            check=True,
            text=True,
            capture_output=True,
        )
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        assert exported[0]["symbol"] == "SH600519"


if __name__ == "__main__":
    test_parse_csv()
    test_collect_xueqiu_watchlist_exports()
    test_gap_event()
    test_legacy_cli_export()
    print("xueqiu-watchlist tests passed.")
