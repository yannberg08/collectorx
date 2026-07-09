#!/usr/bin/env python3
"""
同花顺交割单CSV解析测试
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ths.parser import parse_portfolio_csv
from ths.events import (
    gap_status_to_event,
    gui_snapshot_to_events,
    holdings_to_events,
    personal_metadata_to_events,
    records_to_events,
)
from ths.gui import parse_axis_table_records
from ths.local import (
    build_gap_status,
    build_local_probe_report,
    find_xcs_lscj_files,
    infer_holdings,
    local_file_label,
    parse_xcs_lscj,
)
from ths.metadata import parse_watchlist_value
from ths.package import (
    build_investor_wiki_evidence,
    sync_package_to_soulmirror,
    write_collection_package,
)
from ths.scope import (
    build_ths_scope_policy,
    filter_events_with_scope,
    filter_holdings_with_scope,
    filter_records_with_scope,
)
from ths_query import _build_events, build_gui_collection_gap


def ths_tmp(name: str, filename: str | None = None) -> Path:
    root = Path(tempfile.gettempdir()) / f"{name}_{os.getpid()}"
    shutil.rmtree(root, ignore_errors=True)
    if filename is None:
        return root
    root.mkdir(parents=True, exist_ok=True)
    return root / filename


def test_parse_csv():
    """测试CSV解析"""
    # 创建测试CSV
    test_csv = ths_tmp("test_ths_csv", "test_ths.csv")
    test_csv.write_text("""成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税,过户费
2024-01-15,09:30:00,600519,贵州茅台,买入,1800.00,100,180000.00,54.00,0.00,1.80
2024-01-16,10:00:00,600519,贵州茅台,卖出,1850.00,100,185000.00,55.50,185.00,1.85
""", encoding="utf-8")
    
    records = parse_portfolio_csv(str(test_csv))
    
    assert len(records) == 2, f"Expected 2 records, got {len(records)}"
    assert records[0]["code"] == "600519"
    assert records[0]["direction"] == "买入"
    assert records[1]["direction"] == "卖出"
    
    print("test_parse_csv: PASSED")


def test_parse_empty_csv():
    """测试空CSV"""
    test_csv = ths_tmp("test_ths_empty_csv", "test_ths_empty.csv")
    test_csv.write_text("成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税,过户费\n", encoding="utf-8")
    
    records = parse_portfolio_csv(str(test_csv))
    
    assert len(records) == 0, f"Expected 0 records, got {len(records)}"
    
    print("test_parse_empty_csv: PASSED")


def test_records_to_events():
    """测试CollectorX事件输出"""
    test_csv = ths_tmp("test_ths_events_csv", "test_ths_events.csv")
    test_csv.write_text("""成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税,过户费
2024-01-15,09:30:00,600519,贵州茅台,买入,1800.00,100,180000.00,54.00,0.00,1.80
""", encoding="utf-8")

    records = parse_portfolio_csv(str(test_csv))
    events = records_to_events(
        records,
        raw_file=str(test_csv),
        collected_at="2026-07-07T15:00:00+08:00",
    )

    assert len(events) == 1
    event = events[0]
    assert event["schema"] == "collectorx.event.v1"
    assert event["collector"] == "ths-portfolio"
    assert event["kind"] == "trade"
    assert event["owner_scope"] == "personal"
    assert event["data"]["symbol"] == "600519"
    assert event["data"]["side"] == "buy"
    assert event["privacy"]["local_only"] is True
    assert event["raw_ref"]["row"] == 2

    print("test_records_to_events: PASSED")


def test_parse_xcs_lscj_and_infer_holdings():
    """测试同花顺Mac本机XcsLscj历史成交解析和估算持仓"""
    test_xcs = ths_tmp("test_ths_xcs_lscj", "test_ths_xcs_lscj.json")
    test_xcs.write_text(
        """{
  "startdate": "20240101",
  "enddate": "20240105",
  "600519": {
    "20240102": [
      {"cjsj": "09:30:00", "zqdm": "600519", "cjrq": "20240102", "htbh": "A1", "cjbh": "E1", "cjjg": "10.00", "cjsl": "100", "czmc": "买入", "zqmc": "样本A"}
    ],
    "20240103": [
      {"cjsj": "10:00:00", "zqdm": "600519", "cjrq": "20240103", "htbh": "A2", "cjbh": "E2", "cjjg": "12.00", "cjsl": "40", "czmc": "卖出", "zqmc": "样本A"}
    ]
  },
  "000001": {
    "20240104": [
      {"cjsj": "11:00:00", "zqdm": "000001", "cjrq": "20240104", "htbh": "B1", "cjbh": "F1", "cjjg": "5.00", "cjsl": "200", "czmc": "配售中签", "zqmc": "样本B"},
      {"cjsj": "11:01:00", "zqdm": "000001", "cjrq": "20240104", "htbh": "B2", "cjbh": "F2", "cjjg": "0.00", "cjsl": "10", "czmc": "红股", "zqmc": "样本B"}
    ]
  }
}""",
        encoding="utf-8",
    )

    records = parse_xcs_lscj(str(test_xcs), account="sample")
    assert len(records) == 4
    assert records[0]["date"] == "2024-01-02"
    assert records[0]["amount"] == 1000.0
    assert records[0]["source_format"] == "ths_xcs_lscj"
    assert records[0]["raw_order_hash"].startswith("sha256:")

    holdings = infer_holdings(records)
    by_symbol = {holding["symbol"]: holding for holding in holdings}

    assert by_symbol["600519"]["quantity"] == 60
    assert by_symbol["600519"]["cost"] == 600.0
    assert by_symbol["600519"]["is_confirmed"] is False
    assert by_symbol["000001"]["quantity"] == 210
    assert by_symbol["000001"]["cost"] == 1000.0

    holding_events = holdings_to_events(
        holdings,
        source="同花顺本机历史成交 XcsLscj / 估算持仓",
        collected_at="2026-07-07T15:00:00+08:00",
    )
    assert len(holding_events) == 2
    assert holding_events[0]["kind"] == "holding"
    assert holding_events[0]["data"]["snapshot_type"] == "estimated_from_historical_trades"

    gap_event = gap_status_to_event(
        build_gap_status(records, holdings),
        source="同花顺本机历史成交 XcsLscj / 本机采集状态",
        collected_at="2026-07-07T15:00:00+08:00",
    )
    assert gap_event["kind"] == "profile"
    assert gap_event["data"]["current_holding_snapshot"] == "not_found_in_local_plaintext"

    print("test_parse_xcs_lscj_and_infer_holdings: PASSED")


def test_windows_code_level_scan_fixture():
    """测试Windows代码层模拟扫描,不代表真实Windows同花顺结构已验证"""
    fixture_root = (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "fixtures"
        / "ths-windows-simulated"
    )

    files = find_xcs_lscj_files(str(fixture_root), platform="windows")
    assert len(files) == 1
    assert files[0].name.startswith("XcsLscjDataFile_")

    records = parse_xcs_lscj(str(files[0]), account="windows-sim")
    assert len(records) == 3
    holdings = infer_holdings(records)
    by_symbol = {holding["symbol"]: holding for holding in holdings}
    assert by_symbol["600000"]["quantity"] == 60
    assert by_symbol["000002"]["quantity"] == 200

    report = build_local_probe_report(
        platform="windows",
        container_root=str(fixture_root),
        files=files,
    )
    assert report["platform"]["resolved"] == "windows"
    assert report["xcs_lscj"]["file_count"] == 1
    assert report["platform"]["structure_status"] == "candidate_rules_need_real_machine_verification"

    print("test_windows_code_level_scan_fixture: PASSED")


def test_parse_watchlist_value():
    value = b"\n\x08tefL4w==\x12\x00\x1aQ601138|603629|300442|,17|17|33|"
    parsed = parse_watchlist_value(value)

    assert parsed["group_name"] == "电算"
    assert parsed["symbols"] == ["601138", "603629", "300442"]
    assert parsed["markets"] == ["17", "17", "33"]

    print("test_parse_watchlist_value: PASSED")


def test_local_file_label_masks_account_ids():
    path = Path("/tmp/ShortTermWizard/188888888/HXShortTermWizardMarketMapKey.text")
    assert local_file_label(path) == str(Path("188****888") / "HXShortTermWizardMarketMapKey.text")

    xcs_path = Path("/tmp/XcsFold/XcsLscjDataFile_12345678_188888888")
    assert local_file_label(xcs_path) == str(Path("XcsFold") / "XcsLscjDataFile_123****678_188****888")

    print("test_local_file_label_masks_account_ids: PASSED")


def test_personal_metadata_to_events():
    metadata = {
        "counts": {"watchlist_items": 1},
        "watchlist_items": [
            {
                "symbol": "600519",
                "name": "样本A",
                "group_name": "核心观察",
                "group_id": "g1",
                "market": "17",
                "source_file": "blockstock_535****970.dat",
                "source_type": "ths_cloud_blockstock",
                "evidence_level": "medium",
            }
        ],
        "strategy_rules": [],
        "strategy_topics": [],
        "short_term_rules": [],
        "widget_layouts": [],
        "custom_pages": [],
        "strategy_label_summary": [{"label": "消费", "count": 1, "evidence_level": "weak"}],
        "news_read_markers": [],
        "evidence_note": "sample",
    }
    events = personal_metadata_to_events(
        metadata,
        source="同花顺个人化元数据",
        collected_at="2026-07-07T15:00:00+08:00",
    )

    assert len(events) == 3
    assert events[0]["kind"] == "watchlist"
    assert events[0]["wiki_targets"] == [
        "investor.opportunity_watchlist.watchlist",
        "investor.capability_circle.attention_universe",
    ]
    assert events[-1]["data"]["profile_type"] == "ths_personal_metadata_collection_summary"

    print("test_personal_metadata_to_events: PASSED")


def test_parse_axis_table_records():
    records = [
        {"role": "AXButton", "text": "证券代码", "pos": (262.0, 419.0)},
        {"role": "AXButton", "text": "证券名称", "pos": (342.0, 419.0)},
        {"role": "AXButton", "text": "实际数量", "pos": (802.0, 419.0)},
        {"role": "AXButton", "text": "市值", "pos": (1282.0, 419.0)},
        {"role": "AXStaticText", "text": "600519", "pos": (262.0, 447.0)},
        {"role": "AXStaticText", "text": "样本A", "pos": (342.0, 447.0)},
        {"role": "AXStaticText", "text": "100", "pos": (802.0, 447.0)},
        {"role": "AXStaticText", "text": "180000.000", "pos": (1282.0, 447.0)},
    ]
    table = parse_axis_table_records(records)

    assert table["headers"] == ["证券代码", "证券名称", "实际数量", "市值"]
    assert table["row_count"] == 1
    assert table["rows"][0]["symbol"] == "600519"
    assert table["rows"][0]["actual_quantity"] == 100
    assert table["rows"][0]["market_value"] == 180000.0

    print("test_parse_axis_table_records: PASSED")


def test_gui_snapshot_to_events():
    snapshot = {
        "collected_at": "2026-07-07T15:00:00+08:00",
        "account": {"broker": "样本券商", "display_name": "样本用户"},
        "asset_snapshot": {
            "total_assets": 1000.0,
            "available_cash": 100.0,
            "snapshot_type": "broker_gui_current_snapshot",
            "is_confirmed": True,
        },
        "tabs": {
            "holding": {
                "rows": [
                    {
                        "symbol": "600519",
                        "name": "样本A",
                        "actual_quantity": 100,
                        "market_value": 1000.0,
                    }
                ],
                "screenshot": "/tmp/holding.png",
            },
            "orders": {"rows": [], "headers": ["委托日期"], "screenshot": "/tmp/orders.png"},
            "deals": {"rows": [], "headers": ["成交日期"], "screenshot": "/tmp/deals.png"},
            "funds_detail": {"rows": [], "headers": ["成交日期"], "screenshot": "/tmp/funds.png"},
        },
    }

    events = gui_snapshot_to_events(
        snapshot,
        source="同花顺Mac交易界面确认快照",
        collected_at="2026-07-07T15:00:00+08:00",
    )

    kinds = [event["kind"] for event in events]
    assert kinds.count("asset_snapshot") == 1
    assert kinds.count("holding") == 1
    assert kinds.count("profile") == 3
    assert events[1]["data"]["is_confirmed"] is True
    assert events[1]["data"]["snapshot_type"] == "broker_gui_current_snapshot"

    print("test_gui_snapshot_to_events: PASSED")


def test_gui_collection_gap_event():
    screenshot_dir = str(ths_tmp("ths_gui_gap"))
    gap = build_gui_collection_gap(
        RuntimeError("macOS Accessibility APIs are unavailable"),
        platform="mac",
        screenshot_dir=screenshot_dir,
        collected_at="2026-07-07T15:00:00+08:00",
    )
    events = _build_events(
        records=[],
        holdings=[],
        metadata=None,
        gui_snapshot=None,
        gui_error_status=gap,
        source="同花顺Mac交易界面确认快照",
        raw_file=None,
        collected_at="2026-07-07T15:00:00+08:00",
        include_holding_events=False,
        include_gap_event=False,
        include_metadata_events=False,
        include_gui_events=True,
        container_root=None,
        platform="mac",
        gui_screenshot_dir=screenshot_dir,
    )

    assert len(events) == 1
    assert events[0]["kind"] == "profile"
    assert events[0]["data"]["profile_type"] == "ths_gui_collection_gap"
    assert events[0]["data"]["status"] == "gui_collection_failed"
    assert events[0]["data"]["is_confirmed"] is False
    assert "investor.data_quality.collection_gaps" in events[0]["wiki_targets"]

    print("test_gui_collection_gap_event: PASSED")


def test_write_collection_package_and_sync():
    records = [
        {
            "date": "2024-01-15",
            "time": "09:30:00",
            "code": "600519",
            "name": "样本A",
            "direction": "买入",
            "price": 10.0,
            "quantity": 100,
            "amount": 1000.0,
            "fee": 1.0,
            "tax": 0.0,
            "account": "sample",
        }
    ]
    holdings = infer_holdings(records)
    events = records_to_events(records, collected_at="2026-07-07T15:00:00+08:00")
    events.extend(
        holdings_to_events(
            holdings,
            source="同花顺估算持仓",
            collected_at="2026-07-07T15:00:00+08:00",
        )
    )

    output = ths_tmp("ths_portfolio_package_test")
    manifest = write_collection_package(
        output,
        events=events,
        collected_at="2026-07-07T15:00:00+08:00",
        records=records,
        holdings=holdings,
    )

    evidence = build_investor_wiki_evidence(events, generated_at="2026-07-07T15:00:00+08:00")
    assert manifest["collector"] == "ths-portfolio"
    assert manifest["event_count"] == len(events)
    assert evidence["coverage_summary"]["dimension_count"] == 7
    assert evidence["coverage_summary"]["subdimension_count"] == 20
    assert (output / "lake" / "ths-portfolio" / "events.jsonl").exists()
    assert (output / "investor_wiki_evidence.v1.json").exists()

    soulmirror_home = ths_tmp("ths_portfolio_soulmirror_test")
    sync_report = sync_package_to_soulmirror(output, soulmirror_home=soulmirror_home)
    assert sync_report["collector"] == "ths-portfolio"
    assert (soulmirror_home / "lake" / "ths-portfolio" / "events.jsonl").exists()
    assert (soulmirror_home / "lake" / "ths-portfolio" / "latest" / "events.jsonl").exists()
    assert not (soulmirror_home / "wiki").exists()

    print("test_write_collection_package_and_sync: PASSED")


def test_ths_scope_policy_filters_trade_package():
    records = [
        {
            "date": "2024-01-15",
            "time": "09:30:00",
            "code": "600519",
            "name": "样本A",
            "direction": "买入",
            "price": 10.0,
            "quantity": 100,
            "amount": 1000.0,
            "fee": 1.0,
            "tax": 0.0,
            "account": "account-a",
        },
        {
            "date": "2024-01-16",
            "time": "10:00:00",
            "code": "000001",
            "name": "样本B",
            "direction": "买入",
            "price": 5.0,
            "quantity": 200,
            "amount": 1000.0,
            "fee": 1.0,
            "tax": 0.0,
            "account": "account-b",
        },
    ]
    holdings = infer_holdings(records)
    events = _build_events(
        records=records,
        holdings=holdings,
        metadata=None,
        gui_snapshot=None,
        gui_error_status=None,
        source="同花顺交割单 CSV",
        raw_file=None,
        collected_at="2026-07-07T15:00:00+08:00",
        include_holding_events=True,
        include_gap_event=True,
        include_metadata_events=False,
        include_gui_events=False,
        container_root=None,
        platform="mac",
        gui_screenshot_dir=None,
    )
    policy = build_ths_scope_policy(
        allow_event_kinds=["trade"],
        allow_symbols=["600519"],
        allow_accounts=["account-a"],
    )
    filtered_events, audit = filter_events_with_scope(events, policy)

    assert len(filtered_events) == 1
    assert filtered_events[0]["kind"] == "trade"
    assert filtered_events[0]["data"]["symbol"] == "600519"
    assert filtered_events[0]["data"]["amount"] == 1000.0
    assert filtered_events[0]["data"]["ths_scope_policy"]["allowed"] is True
    scope = audit["ths_scope_policy"]
    assert scope["candidate_event_count"] == len(events)
    assert scope["retained_event_count"] == 1
    assert scope["filtered_event_count"] == len(events) - 1
    assert scope["filter_reason_counts"] == {
        "allow_event_kind_not_matched": 3,
        "allow_symbol_not_matched": 1,
    }

    output = ths_tmp("ths_portfolio_scope_policy_package_test")
    manifest = write_collection_package(
        output,
        events=filtered_events,
        collected_at="2026-07-07T15:00:00+08:00",
        records=filter_records_with_scope(records, policy),
        holdings=filter_holdings_with_scope(holdings, policy),
        collection_audit=audit,
    )
    sidecar_records = json.loads((output / "trades.normalized.json").read_text(encoding="utf-8"))
    sidecar_holdings = json.loads((output / "estimated_holdings.json").read_text(encoding="utf-8"))
    assert [record["code"] for record in sidecar_records] == ["600519"]
    assert sidecar_holdings == []
    assert manifest["collection_audit"]["ths_scope_policy"]["enabled"] is True
    assert manifest["collection_readiness"]["status"] == "events_ready_but_current_snapshot_incomplete"
    proof = manifest["ths_portfolio_boundary_proof"]
    assert proof["authorization_scope_boundary"]["retained_event_count"] == 1
    assert proof["exact_business_numbers_preserved"] is True
    assert proof["order_mutation_performed"] is False

    print("test_ths_scope_policy_filters_trade_package: PASSED")


def test_ths_scope_policy_filtered_all_package_status():
    records = [
        {
            "date": "2024-01-15",
            "time": "09:30:00",
            "code": "600519",
            "name": "样本A",
            "direction": "买入",
            "price": 10.0,
            "quantity": 100,
            "amount": 1000.0,
            "fee": 1.0,
            "tax": 0.0,
            "account": "account-a",
        }
    ]
    holdings = infer_holdings(records)
    events = _build_events(
        records=records,
        holdings=holdings,
        metadata=None,
        gui_snapshot=None,
        gui_error_status=None,
        source="同花顺交割单 CSV",
        raw_file=None,
        collected_at="2026-07-07T15:00:00+08:00",
        include_holding_events=True,
        include_gap_event=False,
        include_metadata_events=False,
        include_gui_events=False,
        container_root=None,
        platform="mac",
        gui_screenshot_dir=None,
    )
    policy = build_ths_scope_policy(allow_symbols=["000001"])
    filtered_events, audit = filter_events_with_scope(events, policy)
    assert filtered_events == []
    assert audit["ths_scope_policy_filtered_all"] is True
    assert audit["ths_scope_policy"]["filter_reason_counts"] == {"allow_symbol_not_matched": 2}

    output = ths_tmp("ths_portfolio_scope_policy_filtered_all_test")
    manifest = write_collection_package(
        output,
        events=filtered_events,
        collected_at="2026-07-07T15:00:00+08:00",
        records=filter_records_with_scope(records, policy),
        holdings=filter_holdings_with_scope(holdings, policy),
        collection_audit=audit,
    )
    assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
    assert manifest["collection_readiness"]["can_enter_finclaw"] is False
    assert manifest["collection_readiness"]["scope_policy_filtered_all"] is True
    assert manifest["collection_readiness"]["gap_count"] == 1
    assert manifest["event_count"] == 1
    assert manifest["kind_counts"] == {"profile": 1}
    assert manifest["ths_portfolio_boundary_proof"]["authorization_scope_boundary"]["filtered_all"] is True
    assert json.loads((output / "trades.normalized.json").read_text(encoding="utf-8")) == []
    events_path = output / "lake" / "ths-portfolio" / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    assert events[0]["kind"] == "profile"
    assert events[0]["data"]["gap"] == "ths_scope_policy_filtered_all"
    assert events[0]["data"]["candidate_event_count"] == 2
    assert events[0]["data"]["filtered_event_count"] == 2
    assert events[0]["data"]["read_only"] is True
    assert "symbol" not in events[0]["data"]

    print("test_ths_scope_policy_filtered_all_package_status: PASSED")


if __name__ == "__main__":
    test_parse_csv()
    test_parse_empty_csv()
    test_records_to_events()
    test_parse_xcs_lscj_and_infer_holdings()
    test_windows_code_level_scan_fixture()
    test_parse_watchlist_value()
    test_local_file_label_masks_account_ids()
    test_personal_metadata_to_events()
    test_parse_axis_table_records()
    test_gui_snapshot_to_events()
    test_gui_collection_gap_event()
    test_write_collection_package_and_sync()
    test_ths_scope_policy_filters_trade_package()
    test_ths_scope_policy_filtered_all_package_status()
    print("\nAll tests passed!")
