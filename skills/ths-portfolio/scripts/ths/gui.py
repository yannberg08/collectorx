"""
ths.gui — Read-only Tonghuashun trading-window snapshots on macOS.

This module uses macOS Accessibility to read the already-open Tonghuashun
window. It only presses read-only tabs and never presses buy/sell/cancel/submit
actions.
"""

from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


CN_TZ = timezone(timedelta(hours=8))
THS_BUNDLE_ID = "cn.com.10jqka.macstockPro"
THS_PROCESS_NAME = "同花顺"

READ_ONLY_TABS = {
    "holding": "持仓",
    "orders": "委托",
    "deals": "成交",
    "funds_detail": "资金明细",
}

ASSET_FIELD_MAP = {
    "总资产": "total_assets",
    "总市值": "market_value",
    "总盈亏": "total_pnl",
    "当日盈亏": "day_pnl",
    "资金余额": "cash_balance",
    "可取金额": "withdrawable_cash",
    "可用金额": "available_cash",
    "风险测评": "risk_assessment",
}

TABLE_FIELD_MAP = {
    "证券代码": "symbol",
    "证券名称": "name",
    "市价": "last_price",
    "盈亏": "pnl",
    "当日盈亏": "day_pnl",
    "浮动盈亏比(%)": "pnl_pct",
    "实际数量": "actual_quantity",
    "股票余额": "share_balance",
    "可用余额": "available_quantity",
    "冻结数量": "frozen_quantity",
    "成本价": "cost_price",
    "市值": "market_value",
    "仓位占比(%)": "position_pct",
    "交易市场": "market",
    "股东账户": "shareholder_account",
    "委托日期": "order_date",
    "委托时间": "order_time",
    "操作": "operation",
    "备注": "remark",
    "委托数量": "order_quantity",
    "撤销数量": "cancelled_quantity",
    "委托价格": "order_price",
    "成交价格": "deal_price",
    "合同编号": "contract_no",
    "申报编号": "report_no",
    "委托属性": "order_attr",
    "成交日期": "deal_date",
    "成交时间": "deal_time",
    "成交数量": "deal_quantity",
    "成交均价": "deal_avg_price",
    "成交金额": "deal_amount",
    "成交编号": "execution_no",
    "发生金额": "occurred_amount",
    "本次金额": "balance_after",
    "摘要": "summary",
    "货币单位": "currency",
}

NUMERIC_FIELDS = {
    "total_assets",
    "market_value",
    "total_pnl",
    "day_pnl",
    "cash_balance",
    "withdrawable_cash",
    "available_cash",
    "last_price",
    "pnl",
    "pnl_pct",
    "cost_price",
    "position_pct",
    "order_price",
    "deal_price",
    "deal_avg_price",
    "deal_amount",
    "occurred_amount",
    "balance_after",
}

INTEGER_FIELDS = {
    "actual_quantity",
    "share_balance",
    "available_quantity",
    "frozen_quantity",
    "order_quantity",
    "cancelled_quantity",
    "deal_quantity",
}


def collect_gui_snapshot(
    *,
    screenshot_dir: Optional[str] = None,
    tabs: Optional[Iterable[str]] = None,
    collected_at: Optional[str] = None,
    restore_tab: str = "holding",
) -> Dict[str, Any]:
    """Collect a confirmed read-only snapshot from the open trading window."""
    AS = _application_services()
    pid = _find_ths_pid()
    app = AS.AXUIElementCreateApplication(pid)
    window = _first_window(AS, app)
    collected = collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds")
    requested_tabs = list(tabs or READ_ONLY_TABS.keys())

    account = _collect_account_identity(AS, window)
    asset_snapshot = _collect_asset_snapshot(AS, window)
    window_id = _window_id()
    shot_dir = Path(screenshot_dir).expanduser() if screenshot_dir else None
    if shot_dir:
        shot_dir.mkdir(parents=True, exist_ok=True)

    tab_results: Dict[str, Any] = {}
    for tab_key in requested_tabs:
        tab_title = READ_ONLY_TABS.get(tab_key, tab_key)
        if tab_title not in READ_ONLY_TABS.values():
            raise ValueError(f"Unsupported read-only tab: {tab_key}")
        _press_button(AS, window, tab_title)
        time.sleep(0.5)
        screenshot_path = None
        if shot_dir:
            screenshot_path = str(shot_dir / f"{tab_key}.png")
            _capture_window(window_id, screenshot_path)
        table = _extract_trade_table(AS, window)
        table["tab"] = tab_title
        table["tab_key"] = tab_key
        table["screenshot"] = screenshot_path
        table["evidence_level"] = "confirmed_gui"
        tab_results[tab_key] = table

    if restore_tab in READ_ONLY_TABS:
        _press_button(AS, window, READ_ONLY_TABS[restore_tab])

    return {
        "schema": "ths.gui_snapshot.v1",
        "platform": "mac",
        "collector": "ths-portfolio",
        "collection_method": "mac_accessibility_read_only",
        "collected_at": collected,
        "account": account,
        "asset_snapshot": asset_snapshot,
        "tabs": tab_results,
        "safety": {
            "read_only_tabs_pressed": [READ_ONLY_TABS.get(key, key) for key in requested_tabs],
            "trade_actions_pressed": False,
            "credentials_read": False,
            "order_cancel_actions_pressed": False,
        },
    }


def parse_axis_table_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build headers and row dictionaries from AX text records with positions."""
    headers = [
        record
        for record in records
        if record.get("role") == "AXButton" and record.get("text")
    ]
    cells = [
        record
        for record in records
        if record.get("role") == "AXStaticText" and record.get("text") not in (None, "")
    ]
    headers = sorted(headers, key=lambda item: (item["pos"][1], item["pos"][0]))
    header_texts = [str(item["text"]) for item in headers]

    row_groups = _group_by_y(cells)
    rows: List[Dict[str, Any]] = []
    for group in row_groups:
        ordered = sorted(group, key=lambda item: item["pos"][0])
        if not ordered:
            continue
        raw = {}
        for index, cell in enumerate(ordered):
            if index >= len(header_texts):
                raw[f"extra_{index - len(header_texts) + 1}"] = cell.get("text")
                continue
            raw[header_texts[index]] = cell.get("text")
        if raw:
            rows.append(_normalize_table_row(raw))

    return {
        "headers": header_texts,
        "rows": rows,
        "row_count": len(rows),
        "raw_text_count": len(records),
    }


def _application_services():
    try:
        import ApplicationServices as AS  # type: ignore
    except Exception as exc:  # pragma: no cover - macOS integration
        raise RuntimeError("macOS Accessibility APIs are unavailable") from exc
    return AS


def _find_ths_pid() -> int:
    try:
        output = subprocess.check_output(["pgrep", "-x", THS_PROCESS_NAME], text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("同花顺 is not running") from exc
    return int(output.splitlines()[0])


def _first_window(AS: Any, app: Any) -> Any:
    err, windows = AS.AXUIElementCopyAttributeValue(app, "AXWindows", None)
    if err != 0 or not windows:
        raise RuntimeError("No Tonghuashun window is available through Accessibility")
    return list(windows)[0]


def _window_id() -> str:
    code = """
import Quartz
for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID):
    if w.get('kCGWindowOwnerName') == '同花顺' and w.get('kCGWindowLayer') == 0:
        print(w.get('kCGWindowNumber'))
        break
"""
    value = subprocess.check_output(["python3", "-c", code], text=True).strip()
    if not value:
        raise RuntimeError("Unable to resolve Tonghuashun window id")
    return value


def _capture_window(window_id: str, output_path: str) -> None:
    subprocess.run(["screencapture", "-x", "-l", str(window_id), output_path], check=True)


def _collect_account_identity(AS: Any, window: Any) -> Dict[str, Any]:
    records = _collect_axis_text_records(AS, window)
    broker = _first_text_near(records, x_range=(50, 125), y_range=(80, 120))
    display_name = _first_text_near(records, x_range=(125, 210), y_range=(80, 120))
    return {
        "broker": broker,
        "display_name": display_name,
        "evidence_level": "confirmed_gui",
    }


def _collect_asset_snapshot(AS: Any, window: Any) -> Dict[str, Any]:
    panel = _find_scroll_area(AS, window, x_range=(50, 70), y_range=(115, 130))
    records = _collect_axis_text_records(AS, panel)
    by_y = _group_by_y(records)
    raw: Dict[str, Any] = {}
    for row in by_y:
        ordered = sorted(row, key=lambda item: item["pos"][0])
        if len(ordered) < 2:
            continue
        label = str(ordered[0]["text"])
        value = str(ordered[1]["text"])
        if label in ASSET_FIELD_MAP:
            raw[label] = value

    normalized = {
        ASSET_FIELD_MAP[label]: _coerce_value(ASSET_FIELD_MAP[label], value)
        for label, value in raw.items()
    }
    normalized.update(
        {
            "raw": raw,
            "snapshot_type": "broker_gui_current_snapshot",
            "is_confirmed": True,
            "evidence_level": "confirmed_gui",
        }
    )
    return normalized


def _extract_trade_table(AS: Any, window: Any) -> Dict[str, Any]:
    table_area = _find_scroll_area(AS, window, x_range=(250, 285), y_range=(390, 450))
    records = _collect_axis_text_records(AS, table_area)
    return parse_axis_table_records(records)


def _collect_axis_text_records(AS: Any, root: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    queue = [root]
    while queue:
        element = queue.pop(0)
        role = _ax_get(AS, element, "AXRole")
        title = _ax_get(AS, element, "AXTitle")
        value = _ax_get(AS, element, "AXValue")
        text = None
        if role == "AXStaticText" and value not in (None, ""):
            text = str(value)
        elif role == "AXButton" and title not in (None, ""):
            text = str(title)
        if text is not None:
            pos = _ax_position(AS, element)
            size = _ax_size(AS, element)
            if pos:
                records.append(
                    {
                        "role": role,
                        "text": text,
                        "pos": pos,
                        "size": size,
                    }
                )
        children = _ax_get(AS, element, "AXChildren")
        if children:
            queue.extend(list(children))
    return records


def _find_scroll_area(
    AS: Any,
    window: Any,
    *,
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
) -> Any:
    for child in list(_ax_get(AS, window, "AXChildren") or []):
        if _ax_get(AS, child, "AXRole") != "AXScrollArea":
            continue
        pos = _ax_position(AS, child)
        if not pos:
            continue
        if x_range[0] <= pos[0] <= x_range[1] and y_range[0] <= pos[1] <= y_range[1]:
            return child
    raise RuntimeError(f"Unable to find target AXScrollArea x={x_range} y={y_range}")


def _press_button(AS: Any, root: Any, title: str) -> None:
    button = _find_button(AS, root, title)
    if button is None:
        raise RuntimeError(f"Read-only tab button not found: {title}")
    err = AS.AXUIElementPerformAction(button, "AXPress")
    if err != 0:
        raise RuntimeError(f"Unable to press read-only tab {title}: AX error {err}")


def _find_button(AS: Any, root: Any, title: str) -> Optional[Any]:
    queue = [root]
    while queue:
        element = queue.pop(0)
        if _ax_get(AS, element, "AXRole") == "AXButton" and _ax_get(AS, element, "AXTitle") == title:
            return element
        children = _ax_get(AS, element, "AXChildren")
        if children:
            queue.extend(list(children))
    return None


def _first_text_near(
    records: List[Dict[str, Any]],
    *,
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
) -> str:
    for record in sorted(records, key=lambda item: (item["pos"][1], item["pos"][0])):
        x, y = record["pos"]
        if x_range[0] <= x <= x_range[1] and y_range[0] <= y <= y_range[1]:
            return str(record["text"])
    return ""


def _group_by_y(records: List[Dict[str, Any]], *, tolerance: float = 6.0) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    for record in sorted(records, key=lambda item: (item["pos"][1], item["pos"][0])):
        y = record["pos"][1]
        if not groups or abs(groups[-1][0]["pos"][1] - y) > tolerance:
            groups.append([record])
        else:
            groups[-1].append(record)
    return groups


def _normalize_table_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {"raw": raw}
    for label, value in raw.items():
        key = TABLE_FIELD_MAP.get(label, label)
        row[key] = _coerce_value(key, value)
    return row


def _coerce_value(key: str, value: Any) -> Any:
    text = str(value).strip()
    if key in INTEGER_FIELDS:
        try:
            return int(float(text.replace(",", "")))
        except ValueError:
            return text
    if key in NUMERIC_FIELDS:
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return text
    return text


def _ax_get(AS: Any, element: Any, attr: str) -> Any:
    try:
        err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
        if err == 0:
            return value
    except Exception:
        return None
    return None


def _ax_position(AS: Any, element: Any) -> Optional[Tuple[float, float]]:
    return _parse_ax_pair(_ax_get(AS, element, "AXPosition"), "x", "y")


def _ax_size(AS: Any, element: Any) -> Optional[Tuple[float, float]]:
    return _parse_ax_pair(_ax_get(AS, element, "AXSize"), "w", "h")


def _parse_ax_pair(value: Any, first: str, second: str) -> Optional[Tuple[float, float]]:
    if value is None:
        return None
    match = re.search(rf"{first}:([\d.-]+) {second}:([\d.-]+)", str(value))
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))
