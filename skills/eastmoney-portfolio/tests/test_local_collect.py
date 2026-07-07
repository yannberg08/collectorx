#!/usr/bin/env python3
"""
东方财富本机采集基础解析测试
"""
import sys
import shutil
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from eastmoney.local_collect import (
    build_local_probe_report,
    build_collection_readiness,
    collect_local,
    find_eastmoney_homes,
    gap_event,
    mask_identifier,
    parse_stock_list,
    parse_stock_token,
    resolve_platform,
    scrub_value,
)
from eastmoney.trade_export import parse_trade_export_file, parse_trade_export_text
from eastmoney.ui_collect import parse_ax_trade_records, parse_ax_trade_state, parse_screen_trade_state


def test_parse_stock_token():
    item = parse_stock_token("1:600519")
    assert item["market"] == "SH"
    assert item["symbol"] == "600519"

    item = parse_stock_token("0$002738")
    assert item["market"] == "SZ"
    assert item["symbol"] == "002738"


def test_parse_stock_list():
    items = parse_stock_list("1:600519;0:002738;bad;")
    assert len(items) == 2
    assert [item["symbol"] for item in items] == ["600519", "002738"]


def test_mask_identifier():
    assert mask_identifier("yannberg") == "yan***rg"
    assert mask_identifier("540123403") == "540****03"


def test_scrub_value_keeps_authorized_business_numbers():
    value = scrub_value(
        {
            "account_id": "188888888",
            "order_id": "O18888888802",
            "note": "token=abc123",
        }
    )
    assert value["account_id"] == "188888888"
    assert value["order_id"] == "O18888888802"
    assert value["note"] == "token=<redacted>"


def test_windows_code_level_probe_fixture():
    """Windows 代码层模拟，不代表真实 Windows 东方财富结构已验证。"""
    fixture_root = find_fixture_root("eastmoney-windows-simulated")

    assert resolve_platform("windows") == "windows"
    homes = find_eastmoney_homes(str(fixture_root), platform="windows")
    assert len(homes) == 1
    assert homes[0].name == "EastMoney"

    report = build_local_probe_report(
        platform="windows",
        container_root=str(fixture_root),
        homes=homes,
    )
    assert report["platform"]["resolved"] == "windows"
    assert report["platform"]["structure_status"] == "candidate_rules_need_real_machine_verification"
    assert report["eastmoney_homes"]["home_count"] == 1
    assert report["capabilities"]["watchlist_files"] == 1
    assert report["capabilities"]["recent_stock_files"] == 1
    assert report["capabilities"]["trade_interface_logs"] == 1

    output = Path("/tmp/eastmoney_windows_sim_collect")
    shutil.rmtree(output, ignore_errors=True)
    manifest = collect_local(
        output_dir=output,
        eastmoney_home=homes[0],
        user="alice",
        platform="windows",
    )
    assert manifest["local_platform"]["resolved"] == "windows"
    assert manifest["source_counts"]["watchlist"] == 2
    assert manifest["source_counts"]["recent_stock"] == 1
    assert manifest["source_counts"]["broker_position_status"] == 1
    assert manifest["source_counts"]["broker_asset_status"] == 1
    assert manifest["validation"]["ok"] is True

    events_path = output / "lake" / "eastmoney-investor-v2" / "events.jsonl"
    allowed_kinds = {"message", "file", "note", "email", "calendar", "task", "trade", "holding", "watchlist", "a2a", "profile", "other"}
    with events_path.open(encoding="utf-8") as f:
        lake_events = [json.loads(line) for line in f]
    assert lake_events
    assert {event["kind"] for event in lake_events} <= allowed_kinds
    assert all(not target.startswith("vertical/investor/") for event in lake_events for target in event.get("wiki_targets", []))
    assert any(event["data"].get("source_kind") == "watchlist" for event in lake_events)
    assert (output / "wiki" / "external" / "investor" / "risk-portfolio" / "东方财富资产持仓边界.md").exists()


def test_trade_export_detail_fixture():
    """测试交易界面导出的明细表能进入强证据事件。"""
    home_root = find_fixture_root("eastmoney-windows-simulated")
    trade_export_root = find_fixture_root("eastmoney-trade-export-simulated")
    homes = find_eastmoney_homes(str(home_root), platform="windows")
    assert len(homes) == 1

    asset_rows = parse_trade_export_file(trade_export_root / "assets.csv")
    position_rows = parse_trade_export_file(trade_export_root / "positions.csv")
    trade_rows = parse_trade_export_file(trade_export_root / "trades.csv")
    entrust_rows = parse_trade_export_file(trade_export_root / "entrusts.csv")
    fund_flow_rows = parse_trade_export_file(trade_export_root / "fund_flow.csv")
    assert len(asset_rows) == 1
    assert asset_rows[0].kind == "broker_asset_snapshot"
    assert len(position_rows) == 2
    assert position_rows[0].kind == "broker_position_detail"
    assert len(trade_rows) == 2
    assert trade_rows[0].kind == "broker_trade_execution"
    assert len(entrust_rows) == 2
    assert entrust_rows[0].kind == "broker_entrust_order"
    assert len(fund_flow_rows) == 1
    assert fund_flow_rows[0].kind == "broker_fund_flow"
    assert asset_rows[0].data["account_id"] == "188888888"
    assert position_rows[0].data["shareholder_account"] == "A188888888"
    assert trade_rows[0].data["execution_id"] == "E18888888801"
    assert trade_rows[0].data["order_id"] == "O18888888801"

    output = Path("/tmp/eastmoney_trade_export_sim_collect")
    shutil.rmtree(output, ignore_errors=True)
    manifest = collect_local(
        output_dir=output,
        eastmoney_home=homes[0],
        user="alice",
        platform="windows",
        trade_export_files=[trade_export_root],
    )
    counts = manifest["source_counts"]
    assert counts["broker_asset_snapshot"] == 1
    assert counts["broker_position_detail"] == 2
    assert counts["broker_trade_execution"] == 2
    assert counts["broker_entrust_order"] == 2
    assert counts["broker_fund_flow"] == 1
    assert counts["data_gap"] == 3
    assert manifest["collection_readiness"]["status"] == "ready_for_investor_avatar"
    assert manifest["collection_readiness"]["can_claim_complete_trade_collection"] is True
    assert (output / "investor_wiki_evidence.v1.json").exists()
    assert manifest["validation"]["ok"] is True


def test_trade_ui_locked_state_parser():
    lines = [
        "AXStaticText | 证券账户 | 证券账户",
        "AXButton | 彭应安 (3303) | missing value",
        "AXStaticText | 登录状态 | 登录状态",
        "AXStaticText | 已锁定 | 已锁定",
        "AXButton | 解锁证券账户 | missing value",
        "AXStaticText | 总资产 | 总资产",
        "AXStaticText | 可用资金 | 可用资金",
    ]
    state = parse_ax_trade_state(lines)
    assert state["account_status"] == "locked"
    assert state["needs_unlock"] is True
    assert state["account_label"] == "彭应安 (3303)"
    assert "总资产" in state["visible_trade_labels"]
    assert "total_asset" not in state["asset_fields"]
    assert "available_cash" not in state["asset_fields"]


def test_trade_ui_ax_record_parser_uses_same_row_value():
    records = [
        {"role": "AXStaticText", "text": "证券账户", "pos": (80.0, 137.0)},
        {"role": "AXButton", "text": "彭应安 (3303)", "pos": (172.0, 137.0)},
        {"role": "AXStaticText", "text": "登录状态", "pos": (80.0, 160.0)},
        {"role": "AXStaticText", "text": "已锁定", "pos": (174.0, 160.0)},
        {"role": "AXStaticText", "text": "总资产", "pos": (80.0, 206.0)},
        {"role": "AXStaticText", "text": "证券代码", "pos": (390.0, 206.0)},
        {"role": "AXStaticText", "text": "东方财富", "pos": (390.0, 229.0)},
    ]
    state = parse_ax_trade_records(records)
    assert state["account_status"] == "locked"
    assert state["account_label"] == "彭应安 (3303)"
    assert state["observed_fields"]["证券账户"] == "彭应安 (3303)"
    assert state["observed_fields"]["登录状态"] == "已锁定"
    assert "total_asset" not in state["asset_fields"]


def test_trade_ui_unlocked_asset_field_parser():
    lines = [
        "AXStaticText | 证券账户 | 证券账户",
        "AXButton | 彭应安 (3303) | missing value",
        "AXStaticText | 登录状态 | 登录状态",
        "AXStaticText | 已登录 | 已登录",
        "AXStaticText | 总资产 | 总资产",
        "AXStaticText | 123,456.78 | 123,456.78",
        "AXStaticText | 总市值 | 总市值",
        "AXStaticText | 100000.00 | 100000.00",
        "AXStaticText | 可用资金 | 可用资金",
        "AXStaticText | 23456.78 | 23456.78",
        "AXStaticText | 货币单位 | 货币单位",
        "AXStaticText | 人民币 | 人民币",
    ]
    state = parse_ax_trade_state(lines)
    assert state["account_status"] == "unlocked_or_online"
    assert state["needs_unlock"] is False
    assert state["asset_fields"]["total_asset"] == 123456.78
    assert state["asset_fields"]["market_value"] == 100000.0
    assert state["asset_fields"]["available_cash"] == 23456.78
    assert state["asset_fields"]["currency"] == "人民币"


def test_trade_ui_screen_ocr_locked_state_parser():
    text = """
    账户信息
    证券账户 彭应安 (3303)
    登录状态 已锁定
    解锁证券账户
    总资产 --
    可用资金 --
    """
    state = parse_screen_trade_state(text)
    assert state["account_status"] == "locked"
    assert state["needs_unlock"] is True
    assert state["status_evidence"] == "screen_ocr"
    assert "登录状态" in state["visible_trade_labels"]
    assert state["asset_fields"] == {}


def test_trade_ui_collect_failed_readiness():
    events = [
        gap_event(
            "2026-07-07T19:30:00+08:00",
            gap="trade_ui_collect_failed",
            status="error",
            note="东方财富交易页自动采集失败：TimeoutExpired",
        )
    ]
    readiness = build_collection_readiness(events)
    assert readiness["status"] == "trade_ui_collect_failed"
    assert readiness["can_claim_complete_trade_collection"] is False
    assert readiness["needs_manual_export"] is False


def test_trade_ui_accessibility_blocked_readiness():
    events = [
        gap_event(
            "2026-07-07T19:30:00+08:00",
            gap="trade_ui_accessibility_tree_empty",
            status="blocked_by_accessibility",
            note="窗口存在但辅助功能树为空。",
        )
    ]
    readiness = build_collection_readiness(events)
    assert readiness["status"] == "trade_ui_accessibility_blocked"
    assert readiness["can_claim_complete_trade_collection"] is False
    assert readiness["needs_manual_export"] is False


def test_trade_ui_copied_position_table_text():
    text = "\t".join(
        [
            "证券代码",
            "证券名称",
            "持仓数量",
            "可用数量",
            "成本价",
            "最新价",
            "盈亏比",
            "盈亏",
            "最新市值",
            "币种",
            "交易市场",
        ]
    )
    text += "\n600519\t贵州茅台\t100\t80\t1500.00\t1600.00\t6.67%\t10000.00\t160000.00\t人民币\t上海A股\n"
    rows = parse_trade_export_text(text, source_name="eastmoney-ui-持仓.tsv", forced_kind="broker_position_detail")
    assert len(rows) == 1
    assert rows[0].kind == "broker_position_detail"
    assert rows[0].data["symbol"] == "600519"
    assert rows[0].data["quantity"] == 100.0
    assert rows[0].data["market_value"] == 160000.0
    assert rows[0].data["profit_loss_ratio"] == 6.67
    assert rows[0].data["currency"] == "人民币"


def find_fixture_root(name: str) -> Path:
    current = Path(__file__).resolve()
    candidates = [
        parent / "examples" / "fixtures" / name
        for parent in current.parents
    ]
    candidates.append(Path("/Users/pengyingan/Desktop/collectorx/examples/fixtures") / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise AssertionError(f"fixture not found: {name}")


if __name__ == "__main__":
    test_parse_stock_token()
    test_parse_stock_list()
    test_mask_identifier()
    test_scrub_value_keeps_authorized_business_numbers()
    test_windows_code_level_probe_fixture()
    test_trade_export_detail_fixture()
    test_trade_ui_locked_state_parser()
    test_trade_ui_ax_record_parser_uses_same_row_value()
    test_trade_ui_unlocked_asset_field_parser()
    test_trade_ui_screen_ocr_locked_state_parser()
    test_trade_ui_collect_failed_readiness()
    test_trade_ui_accessibility_blocked_readiness()
    test_trade_ui_copied_position_table_text()
    print("All local collect tests passed!")
