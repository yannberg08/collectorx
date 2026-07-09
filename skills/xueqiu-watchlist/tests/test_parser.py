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
REPO_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "scripts" / "xueqiu_query.py"
PACKAGE_VALIDATOR = REPO_ROOT / "tools" / "validate_collector_package.py"


def read_events(out: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (out / "lake" / "xueqiu-watchlist" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def assert_package_valid(out: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE_VALIDATOR),
            str(out),
            "--collector",
            "xueqiu-watchlist",
            "--require-evidence",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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
        assert_package_valid(out)
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
        assert manifest["usable_event_count"] == 7
        assert manifest["watchlist_event_count"] == 7
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_enter_xueqiu_watchlist_lake"] is True
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is False
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is True
        assert manifest["collection_readiness"]["usable_event_count"] == 7
        assert manifest["collection_readiness"]["can_claim_complete_xueqiu_watchlist_boundary"] is False
        assert manifest["market_counts"]["HK"] == 2
        assert manifest["archive_member_event_count"] == 1
        assert manifest["evidence_policy"]["xueqiu_watchlist_is_strong_trade_source"] is False
        assert manifest["collection_audit"]["archive_member_count"] == 2
        assert manifest["collection_audit"]["skipped_archive_member_count"] == 1
        assert manifest["collection_audit"]["filtered_record_count"] >= 1
        assert manifest["field_coverage"]["fields"]["symbol"]["present"] == 7
        proof = manifest["xueqiu_watchlist_boundary_proof"]
        assert proof["can_enter_xueqiu_watchlist_lake"] is True
        assert proof["can_enter_data_quality_lake"] is False
        assert proof["can_feed_investor_wiki_evidence"] is True
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["generated_from"]["event_count"] == manifest["usable_event_count"]
        assert evidence["coverage_summary"]["xueqiu_watchlist_is_strong_trade_source"] is False
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


def test_watchlist_scope_policy_filters_authorized_attention_universe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "xueqiu_watchlist.csv"
        out = root / "out"
        csv_path.write_text(
            "代码,名称,分组,行业,备注\n"
            "600519,贵州茅台,核心观察,白酒,长期跟踪\n"
            "688981,中芯国际,半导体,芯片,产业链观察\n"
            "000858,五粮液,白酒池,白酒,私人观察\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(csv_path),
                "--out-dir",
                str(out),
                "--allow-symbol",
                "600519",
                "--allow-market",
                "SH",
                "--allow-group",
                "核心",
                "--allow-industry",
                "白酒",
                "--allow-keyword",
                "长期",
                "--deny-keyword",
                "私人",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = read_events(out)
        assert len(events) == 1
        assert events[0]["data"]["symbol"] == "SH600519"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["xueqiu_watchlist_scope_policy"]["configured"] is True
        assert audit["scope_policy_candidate_event_count"] == 3
        assert audit["scope_policy_retained_event_count"] == 1
        assert audit["scope_policy_filtered_event_count"] == 2
        assert audit["scope_policy_filter_reason_counts"] == {
            "allow_group_mismatch": 2,
            "allow_industry_mismatch": 1,
            "allow_keyword_mismatch": 2,
            "allow_market_mismatch": 1,
            "allow_symbol_mismatch": 2,
            "deny_keyword": 1,
        }
        proof = manifest["xueqiu_watchlist_boundary_proof"]
        assert proof["authorization_scope_boundary"]["policy_configured"] is True
        assert proof["authorization_scope_boundary"]["retained_event_count"] == 1
        assert proof["complete_xueqiu_watchlist_boundary_claimed"] is False


def test_watchlist_scope_policy_filtered_all_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "xueqiu_watchlist.csv"
        out = root / "out"
        csv_path.write_text("代码,名称\n600519,贵州茅台\n", encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(csv_path),
                "--out-dir",
                str(out),
                "--allow-symbol",
                "SH688981",
                "--collected-at",
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = read_events(out)
        assert len(events) == 1
        assert_package_valid(out)
        gap = events[0]
        assert gap["kind"] == "profile"
        assert gap["time"] == "2026-07-08T12:00:00+08:00"
        assert gap["collected_at"] == "2026-07-08T12:00:00+08:00"
        assert gap["data"]["gap"] == "xueqiu_watchlist_scope_policy_filtered_all"
        assert gap["data"]["status"] == "scope_policy_filtered_all"
        assert gap["data"]["profile_type"] == "xueqiu_watchlist_scope_policy_filtered_all"
        assert gap["data"]["candidate_event_count"] == 1
        assert gap["data"]["retained_event_count"] == 0
        assert gap["data"]["filtered_event_count"] == 1
        assert gap["data"]["filter_reason_counts"] == {"allow_symbol_mismatch": 1}
        assert gap["data"]["broker_trade_fact_claimed"] is False
        assert gap["data"]["holding_fact_claimed"] is False
        assert gap["data"]["order_or_fund_flow_claimed"] is False
        assert gap["wiki_targets"] == ["collectorx.data_quality.collection_gaps"]
        assert gap["raw_ref"] == {
            "preflight": True,
            "reason": "xueqiu_watchlist_scope_policy_filtered_all",
            "scope_policy_enabled": True,
        }
        assert str(csv_path) not in json.dumps(gap, ensure_ascii=False)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["usable_event_count"] == 0
        assert manifest["watchlist_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["can_enter_xueqiu_watchlist_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is False
        assert manifest["collection_readiness"]["usable_event_count"] == 0
        assert manifest["collection_readiness"]["source_collection_scope"] == "scope_policy_excluded_all"
        assert manifest["collection_audit"]["xueqiu_watchlist_scope_policy_filtered_all"] is True
        assert manifest["xueqiu_watchlist_boundary_proof"]["proof_level"] == "scope_policy_filtered_all"
        assert manifest["xueqiu_watchlist_boundary_proof"]["authorization_scope_boundary"]["filtered_all"] is True
        assert manifest["xueqiu_watchlist_boundary_proof"]["can_enter_data_quality_lake"] is True


def test_gap_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
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
        assert len(events) == 1
        assert_package_valid(out)
        assert events[0]["kind"] == "profile"
        assert events[0]["time"] == "2026-07-08T12:00:00+08:00"
        assert events[0]["data"]["gap"] == "xueqiu_watchlist_authorized_input_missing"
        assert events[0]["data"]["status"] == "needs_xueqiu_watchlist_authorized_input"
        assert events[0]["data"]["candidate_event_count"] == 0
        assert events[0]["data"]["retained_event_count"] == 0
        assert events[0]["data"]["filtered_event_count"] == 0
        assert events[0]["data"]["broker_trade_fact_claimed"] is False
        assert events[0]["wiki_targets"] == ["collectorx.data_quality.collection_gaps"]
        assert events[0]["raw_ref"] == {
            "preflight": True,
            "reason": "xueqiu_watchlist_authorized_input_missing",
            "scope_policy_enabled": False,
        }
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["usable_event_count"] == 0
        assert manifest["watchlist_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["can_enter_xueqiu_watchlist_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is False


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
    test_watchlist_scope_policy_filters_authorized_attention_universe()
    test_watchlist_scope_policy_filtered_all_gap()
    test_gap_event()
    test_legacy_cli_export()
    print("xueqiu-watchlist tests passed.")
