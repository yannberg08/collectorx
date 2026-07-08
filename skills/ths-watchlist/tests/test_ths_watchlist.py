#!/usr/bin/env python3
"""Tests for ths-watchlist collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
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
        zip_path = root / "watchlist-package.zip"
        unsupported_path = root / "notes.doc"
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
        sheet.append(["00700", "腾讯控股", "港股代码不会补 A 股市场"])
        workbook.save(xlsx_path)
        text_path.write_text("短线观察：002475 立讯精密\n忽略普通文字\n", encoding="utf-8")
        unsupported_path.write_text("not a watchlist export", encoding="utf-8")
        with zipfile.ZipFile(zip_path, "w") as package:
            package.writestr("nested/ths-watchlist.csv", "代码,名称,分组\n300750,宁德时代,新能源\n")
            package.writestr("../escape.csv", "代码,名称\n600000,浦发银行\n")
            package.writestr("nested/readme.doc", "not supported")

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
        zip_event = next(event for event in events if event["data"]["symbol"] == "300750")
        assert zip_event["raw_ref"]["archive_member"] == "nested/ths-watchlist.csv"
        assert zip_event["raw_ref"]["member_row"] == 1
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_ths_attention_universe"] is False
        assert manifest["market_counts"]["SH"] >= 2
        assert manifest["archive_member_event_count"] == 1
        assert manifest["field_coverage"]["fields"]["symbol"]["present"] == 7
        assert manifest["evidence_policy"]["ths_watchlist_is_strong_trade_source"] is False
        audit = manifest["collection_audit"]
        assert audit["source_type"] == "authorized_local_ths_watchlist_export"
        assert audit["input_count"] == 1
        assert audit["resolved_input_file_count"] == 5
        assert audit["skipped_file_count"] == 1
        assert audit["skipped_reason_counts"] == {"unsupported_extension": 1}
        assert audit["skipped_extension_counts"] == {".doc": 1}
        assert audit["archive_count"] == 1
        assert audit["archive_member_count"] == 3
        assert audit["archive_member_imported_record_count"] == 1
        assert audit["skipped_archive_member_count"] == 2
        assert audit["skipped_archive_member_reason_counts"] == {
            "unsafe_path": 1,
            "unsupported_extension": 1,
        }
        assert audit["parsed_record_count"] == 8
        assert audit["filtered_record_count"] == 1
        assert audit["emitted_event_count"] == 7
        proof = manifest["ths_watchlist_boundary_proof"]
        assert proof["proof_level"] == "authorized_ths_watchlist_package_partial"
        assert proof["event_count"] == 7
        assert proof["format_boundary"]["archive_member_imported_record_count"] == 1
        assert proof["strong_trade_boundary"]["watchlist_attention_universe_only"] is True
        assert proof["strong_trade_boundary"]["holdings_collected"] is False
        assert proof["complete_attention_universe_claimed"] is False
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["ths_watchlist_is_strong_trade_source"] is False
        assert evidence["coverage_summary"]["dimension_count"] == 7
        assert evidence["coverage_summary"]["subdimension_count"] == 20
        industry_circle = next(
            child
            for dimension in evidence["dimensions"]
            for child in dimension["children"]
            if child["subdimension_id"] == "inv-industry-circle"
        )
        assert industry_circle["support_level"] == "medium"
        assert industry_circle["evidence_count"] == 7


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
        assert manifest["collection_audit"]["input_count"] == 0
        assert manifest["ths_watchlist_boundary_proof"]["proof_level"] == "no_authorized_ths_watchlist_input"


def test_local_scan_discovers_watchlist_candidates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        local_root = root / "AppData" / "Roaming" / "10jqka" / "users" / "13800138000"
        local_root.mkdir(parents=True)
        (local_root / "自选股.csv").write_text(
            "代码,名称,分组\n600036,招商银行,银行观察\n",
            encoding="utf-8",
        )
        (local_root / "watchlist-extra.json").write_text(
            json.dumps({"watchlist": [{"code": "300760", "name": "迈瑞医疗", "group": "医疗器械"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (local_root / "ordinary.csv").write_text("代码,名称\n600000,浦发银行\n", encoding="utf-8")
        (local_root / "watchlist-secret.cookie").write_text("cookie=must-not-read", encoding="utf-8")
        out = root / "out"
        probe = root / "probe.json"

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--local-scan",
                "--platform",
                "windows",
                "--container-root",
                str(local_root),
                "--probe-export",
                str(probe),
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
        assert len(events) == 2
        assert {event["data"]["symbol"] for event in events} == {"600036", "300760"}
        assert all(event["source"] == "同花顺自选股用户授权本机扫描" for event in events)
        assert all(event["data"]["local_scan"] is True for event in events)
        assert all(event["data"]["source_platform"] == "windows" for event in events)
        assert all(event["raw_ref"]["local_scan"] is True for event in events)
        assert all(event["raw_ref"]["source_platform"] == "windows" for event in events)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "13800138000" not in serialized
        assert "must-not-read" not in serialized
        assert "ordinary.csv" not in serialized

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["local_scan_event_count"] == 2
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input_or_local_scan"
        audit = manifest["collection_audit"]
        assert audit["source_type"] == "authorized_local_ths_watchlist_export_or_local_scan"
        assert audit["input_count"] == 0
        assert audit["resolved_input_file_count"] == 2
        assert audit["local_scan_requested"] is True
        assert audit["local_scan_platform"]["resolved"] == "windows"
        assert audit["local_scan_candidate_file_count"] == 2
        assert audit["local_scan_event_count"] == 2
        assert all("13800138000" not in path for path in audit["local_scan_candidate_files"])
        assert "13800138000" not in json.dumps(manifest, ensure_ascii=False)
        proof = manifest["ths_watchlist_boundary_proof"]
        assert proof["proof_level"] == "authorized_ths_local_scan_partial"
        assert proof["local_scan_boundary"]["local_scan_event_count"] == 2
        assert proof["local_scan_boundary"]["credentials_read"] is False
        assert proof["strong_trade_boundary"]["holdings_collected"] is False

        probe_payload = json.loads(probe.read_text(encoding="utf-8"))
        assert probe_payload["probe_type"] == "ths_watchlist_local_scan"
        assert probe_payload["platform"]["resolved"] == "windows"
        assert probe_payload["watchlist_candidates"]["file_count"] == 2
        assert probe_payload["privacy_policy"]["credentials"] == "not_read"
        assert "13800138000" not in json.dumps(probe_payload, ensure_ascii=False)


if __name__ == "__main__":
    test_collect_ths_watchlist_exports()
    test_gap_event()
    test_local_scan_discovers_watchlist_candidates()
    print("ths-watchlist tests passed.")
