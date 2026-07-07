"""
Read-only EastMoney trading-window collection.

This module automates the already-open EastMoney Mac application only through
normal UI actions: activate app, open the trade page, inspect accessibility
labels, and copy visible table text. It never reads credentials, cookies,
sessions, signatures, raw protocol payloads, or submits trading actions.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from eastmoney.trade_export import ParsedTradeRow, parse_number, parse_trade_export_text


APP_NAME = "东方财富经典版"
TRADE_KEY_CODE = 111  # F12 in the classic Mac client.

TAB_SPECS = [
    {
        "tab": "positions",
        "label": "持仓",
        "kind": "broker_position_detail",
        "relative_click": (445, 630),
    },
    {
        "tab": "executions",
        "label": "成交",
        "kind": "broker_trade_execution",
        "relative_click": (500, 630),
    },
    {
        "tab": "entrusts",
        "label": "委托",
        "kind": "broker_entrust_order",
        "relative_click": (555, 630),
    },
    {
        "tab": "funds",
        "label": "资金",
        "kind": "broker_fund_flow",
        "relative_click": (655, 630),
    },
]

TABLE_RELATIVE_CLICK = (720, 735)

TRADE_LABELS = [
    "证券账户",
    "登录状态",
    "账户类型",
    "总资产",
    "总市值",
    "持仓盈亏",
    "当日参考盈亏",
    "可用资金",
    "可取资金",
    "冻结资金",
    "资金余额",
    "货币单位",
]

ACCOUNT_FIELD_LABELS = {
    "总资产": "total_asset",
    "总市值": "market_value",
    "持仓盈亏": "profit_loss",
    "当日参考盈亏": "day_profit_loss",
    "可用资金": "available_cash",
    "可取资金": "withdrawable_cash",
    "冻结资金": "frozen_cash",
    "资金余额": "cash_balance",
    "货币单位": "currency",
    "账户类型": "account_type",
    "登录状态": "login_status",
}


@dataclass
class CopiedTable:
    tab: str
    label: str
    kind: str
    status: str
    rows: List[ParsedTradeRow] = field(default_factory=list)
    copied_text_chars: int = 0
    note: str = ""


@dataclass
class TradeUISnapshot:
    attempted: bool
    platform_supported: bool
    app_running: bool = False
    window_found: bool = False
    trade_page_requested: bool = False
    account: Dict[str, Any] = field(default_factory=dict)
    tables: List[CopiedTable] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    ax_line_count: int = 0
    ocr_line_count: int = 0


def collect_trade_ui_snapshot(copy_tables: bool = True) -> TradeUISnapshot:
    if sys.platform != "darwin":
        return TradeUISnapshot(
            attempted=False,
            platform_supported=False,
            gaps=[
                {
                    "gap": "trade_ui_automation_unsupported_platform",
                    "status": "not_supported",
                    "note": "东方财富交易页自动采集目前只支持 macOS 客户端。",
                }
            ],
        )

    snapshot = TradeUISnapshot(attempted=True, platform_supported=True)
    snapshot.app_running = _process_exists()
    if not snapshot.app_running:
        snapshot.gaps.append(
            {
                "gap": "trade_ui_app_not_running",
                "status": "not_found",
                "note": "未发现东方财富经典版正在运行，无法读取交易页。",
            }
        )
        return snapshot

    _open_or_activate_app()
    snapshot.trade_page_requested = _send_trade_shortcut()
    window_rect = _front_window_rect()
    if not window_rect:
        snapshot.gaps.append(
            {
                "gap": "trade_ui_window_missing",
                "status": "not_found",
                "note": "东方财富进程存在，但没有可读取的主窗口。",
            }
        )
        return snapshot

    snapshot.window_found = True
    ax_records = _dump_accessibility_records()
    if ax_records:
        snapshot.ax_line_count = len(ax_records)
        snapshot.account = parse_ax_trade_records(ax_records)
    else:
        ax_lines = _dump_accessibility_lines()
        snapshot.ax_line_count = len(ax_lines)
        snapshot.account = parse_ax_trade_state(ax_lines)

    if snapshot.ax_line_count == 0:
        ocr_text = _ocr_window_text(window_rect)
        snapshot.ocr_line_count = len([line for line in ocr_text.splitlines() if line.strip()])
        snapshot.account = _merge_account_state(
            snapshot.account,
            parse_screen_trade_state(ocr_text),
        )
        snapshot.gaps.append(
            {
                "gap": "trade_ui_accessibility_tree_empty",
                "status": "blocked_by_accessibility",
                "note": "System Events 能看到东方财富窗口，但没有返回可读取的控件文本；已尝试只读截图文字识别作为账户状态兜底。",
            }
        )

    if snapshot.account.get("account_status") == "locked":
        snapshot.gaps.append(
            {
                "gap": "broker_account_locked",
                "status": "blocked_by_account_lock",
                "note": "东方财富交易页显示证券账户已锁定；采集器不会读取或请求交易密码。",
            }
        )
        return snapshot

    if copy_tables:
        snapshot.tables = copy_trade_tables(window_rect)
        for table in snapshot.tables:
            if table.status not in {"captured", "confirmed_empty"}:
                snapshot.gaps.append(
                    {
                        "gap": f"trade_ui_{table.tab}_copy_unavailable",
                        "status": table.status,
                        "note": table.note or f"未能从交易页自动复制{table.label}表格。",
                    }
                )

    return snapshot


def parse_ax_trade_state(lines: Iterable[str]) -> Dict[str, Any]:
    texts = [_extract_ax_text(line) for line in lines]
    texts = [text for text in texts if text]
    joined = "\n".join(texts)

    account_label = ""
    for text in texts:
        if re.search(r"\(\d{2,}\)", text):
            account_label = text
            break

    status = "unknown"
    if "已锁定" in joined or "解锁证券账户" in joined:
        status = "locked"
    elif "未登录" in joined:
        status = "logged_out"
    elif "已登录" in joined or "保持在线" in joined:
        status = "unlocked_or_online"

    observed_fields = _extract_labeled_values(texts)
    asset_fields = _normalize_asset_fields(observed_fields)

    return {
        "account_status": status,
        "account_label": account_label,
        "needs_unlock": status == "locked",
        "visible_trade_labels": sorted(
            label
            for label in TRADE_LABELS
            if label in joined
        ),
        "observed_fields": observed_fields,
        "asset_fields": asset_fields,
    }


def parse_ax_trade_records(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    usable = [
        record
        for record in records
        if _clean_ax_value(record.get("text"))
        and record.get("pos")
    ]
    texts = [_clean_ax_value(record.get("text")) for record in usable]
    joined = "\n".join(texts)

    account_label = ""
    for text in texts:
        if re.search(r"\(\d{2,}\)", text):
            account_label = text
            break

    status = "unknown"
    if "已锁定" in joined or "解锁证券账户" in joined:
        status = "locked"
    elif "未登录" in joined:
        status = "logged_out"
    elif "已登录" in joined or "保持在线" in joined:
        status = "unlocked_or_online"

    observed_fields: Dict[str, str] = {}
    label_set = set(TRADE_LABELS)
    for label_record in usable:
        label = _clean_ax_value(label_record.get("text"))
        if label not in label_set:
            continue
        label_x, _ = label_record["pos"]
        if label_x > 220:
            continue
        value = _nearest_value_to_right(label_record, usable, label_set)
        if value:
            observed_fields[label] = value

    asset_fields = _normalize_asset_fields(observed_fields)
    return {
        "account_status": status,
        "account_label": account_label,
        "needs_unlock": status == "locked",
        "visible_trade_labels": sorted(label for label in TRADE_LABELS if label in joined),
        "observed_fields": observed_fields,
        "asset_fields": asset_fields,
        "status_evidence": "mac_accessibility",
    }


def _nearest_value_to_right(
    label_record: Dict[str, Any],
    records: List[Dict[str, Any]],
    label_set: set[str],
) -> str:
    label_x, label_y = label_record["pos"]
    candidates = []
    for record in records:
        if record is label_record or not record.get("pos"):
            continue
        text = _clean_ax_value(record.get("text"))
        if not text or text in label_set or text in {"--", "-", "—", "missing value"}:
            continue
        x, y = record["pos"]
        if x <= label_x + 10:
            continue
        if abs(y - label_y) > 5:
            continue
        if x - label_x > 190:
            continue
        candidates.append((x - label_x, text))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def parse_screen_trade_state(text: str) -> Dict[str, Any]:
    cleaned = _clean_ax_value(text)
    status = "unknown"
    if "已锁定" in cleaned or "解锁证券账户" in cleaned:
        status = "locked"
    elif "未登录" in cleaned:
        status = "logged_out"
    elif "已登录" in cleaned or "保持在线" in cleaned:
        status = "unlocked_or_online"

    return {
        "account_status": status,
        "account_label": "",
        "needs_unlock": status == "locked",
        "visible_trade_labels": sorted(
            label
            for label in TRADE_LABELS
            if label in cleaned
        ),
        "observed_fields": {},
        "asset_fields": {},
        "status_evidence": "screen_ocr" if cleaned else "",
    }


def _merge_account_state(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(primary or {})
    if (merged.get("account_status") in {None, "", "unknown"}) and fallback.get("account_status") != "unknown":
        merged["account_status"] = fallback.get("account_status")
        merged["needs_unlock"] = fallback.get("needs_unlock", False)
        merged["status_evidence"] = fallback.get("status_evidence")
    if not merged.get("visible_trade_labels") and fallback.get("visible_trade_labels"):
        merged["visible_trade_labels"] = fallback.get("visible_trade_labels")
    merged.setdefault("observed_fields", {})
    merged.setdefault("asset_fields", {})
    merged.setdefault("account_label", "")
    merged.setdefault("account_status", "unknown")
    merged.setdefault("needs_unlock", False)
    return merged


def copy_trade_tables(window_rect: Dict[str, int]) -> List[CopiedTable]:
    tables: List[CopiedTable] = []
    with ClipboardSnapshot() as clipboard:
        for spec in TAB_SPECS:
            _click_relative(window_rect, spec["relative_click"])
            time.sleep(0.35)

            ax_table_text = _extract_visible_table_text(window_rect)
            if ax_table_text:
                rows = parse_trade_export_text(
                    ax_table_text,
                    source_name=f"eastmoney-ax-{spec['label']}.tsv",
                    forced_kind=spec["kind"],
                )
                for row in rows:
                    row.data["snapshot_type"] = "broker_ui_accessibility_confirmed"
                tables.append(
                    CopiedTable(
                        tab=spec["tab"],
                        label=spec["label"],
                        kind=spec["kind"],
                        status="captured" if rows else "confirmed_empty",
                        rows=rows,
                        copied_text_chars=len(ax_table_text),
                        note="" if rows else f"{spec['label']}表格可读取但当前没有数据行。",
                    )
                )
                continue

            old_text = clipboard.current_text()
            _click_relative(window_rect, TABLE_RELATIVE_CLICK)
            _copy_focused_table()
            new_text = clipboard.current_text()
            clipboard.restore()

            if not new_text or new_text == old_text:
                tables.append(
                    CopiedTable(
                        tab=spec["tab"],
                        label=spec["label"],
                        kind=spec["kind"],
                        status="empty_or_copy_unavailable",
                        note=f"{spec['label']}表格未返回可解析文本，可能为空、未聚焦或账户未解锁。",
                    )
                )
                continue

            rows = parse_trade_export_text(
                new_text,
                source_name=f"eastmoney-ui-{spec['label']}.tsv",
                forced_kind=spec["kind"],
            )
            for row in rows:
                row.data["snapshot_type"] = "broker_ui_clipboard_confirmed"
            tables.append(
                CopiedTable(
                    tab=spec["tab"],
                    label=spec["label"],
                    kind=spec["kind"],
                    status="captured" if rows else "copied_but_unparsed",
                    rows=rows,
                    copied_text_chars=len(new_text),
                    note="" if rows else f"{spec['label']}表格复制成功，但字段未能识别。",
                )
            )
    return tables


def _extract_labeled_values(texts: List[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    label_set = set(TRADE_LABELS)
    for index, text in enumerate(texts):
        normalized_text = _clean_ax_value(text)
        if normalized_text not in label_set:
            combined = _extract_combined_label_value(normalized_text)
            if combined:
                label, value = combined
                values[label] = value
            continue

        for candidate in texts[index + 1 : index + 5]:
            candidate = _clean_ax_value(candidate)
            if not candidate or candidate in label_set:
                continue
            if candidate in {"--", "-", "—", "missing value"}:
                continue
            values[normalized_text] = candidate
            break
    return values


def _extract_combined_label_value(text: str) -> Optional[tuple[str, str]]:
    for label in TRADE_LABELS:
        if not text.startswith(label):
            continue
        value = text[len(label) :].strip(" :：\t")
        if value:
            return label, value
    return None


def _normalize_asset_fields(observed_fields: Dict[str, str]) -> Dict[str, Any]:
    asset: Dict[str, Any] = {}
    for label, key in ACCOUNT_FIELD_LABELS.items():
        if label not in observed_fields:
            continue
        value = observed_fields[label]
        if key in {"currency", "account_type", "login_status"}:
            asset[key] = value
        else:
            parsed = parse_number(value)
            if parsed is not None:
                asset[key] = parsed
    return asset


def _clean_ax_value(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


class ClipboardSnapshot:
    def __init__(self) -> None:
        self.pb = None
        self.items: List[Any] = []

    def __enter__(self) -> "ClipboardSnapshot":
        from AppKit import NSPasteboard

        self.pb = NSPasteboard.generalPasteboard()
        self.capture()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.restore()

    def capture(self) -> None:
        if self.pb is None:
            return
        self.items = []
        for type_name in self.pb.types() or []:
            data = self.pb.dataForType_(type_name)
            if data is not None:
                self.items.append((type_name, data))

    def current_text(self) -> str:
        if self.pb is None:
            return ""
        from AppKit import NSPasteboardTypeString

        return self.pb.stringForType_(NSPasteboardTypeString) or ""

    def restore(self) -> None:
        if self.pb is None:
            return
        self.pb.clearContents()
        for type_name, data in self.items:
            self.pb.setData_forType_(data, type_name)


def _extract_ax_text(line: str) -> str:
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 3:
        return ""
    name = "" if parts[1] in {"missing value", ""} else parts[1]
    value = "" if parts[2] in {"missing value", ""} else parts[2]
    return name or value


def _process_exists() -> bool:
    script = f'tell application "System Events" to exists process "{APP_NAME}"'
    return _osascript(script, check=False).strip().lower() == "true"


def _open_or_activate_app() -> None:
    subprocess.run(["open", "-a", APP_NAME], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    _osascript(f'tell application "{APP_NAME}" to activate', check=False)
    time.sleep(0.4)


def _send_trade_shortcut() -> bool:
    script = f"""
tell application "System Events"
  tell process "{APP_NAME}"
    key code {TRADE_KEY_CODE}
  end tell
end tell
"""
    return _osascript(script, check=False) is not None


def _front_window_rect() -> Optional[Dict[str, int]]:
    script = f"""
tell application "System Events"
  tell process "{APP_NAME}"
    if (count windows) is 0 then return ""
    set p to position of window 1
    set s to size of window 1
    return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
  end tell
end tell
"""
    output = _osascript(script, check=False).strip()
    values = [int(part) for part in output.split(",") if part.strip().lstrip("-").isdigit()]
    if len(values) != 4:
        return None
    return {"x": values[0], "y": values[1], "width": values[2], "height": values[3]}


def _dump_accessibility_lines() -> List[str]:
    records = _dump_accessibility_records()
    if records:
        return [
            f"{record.get('role') or ''} | {record.get('text') or ''} | {record.get('text') or ''}"
            for record in sorted(records, key=lambda item: (item.get("pos") or (0, 0))[1::-1])
        ]

    script = f"""
on dumpElem(e, depth)
  if depth > 7 then return ""
  tell application "System Events"
    set roleText to ""
    set nameText to ""
    set valueText to ""
    try
      set roleText to role of e as text
    end try
    try
      set nameText to name of e as text
    end try
    try
      set valueText to value of e as text
    end try
    set rowText to roleText & " | " & nameText & " | " & valueText & linefeed
    try
      set childrenList to UI elements of e
      repeat with child in childrenList
        set rowText to rowText & my dumpElem(child, depth + 1)
      end repeat
    end try
    return rowText
  end tell
end dumpElem

tell application "System Events"
  tell process "{APP_NAME}"
    if (count windows) is 0 then return ""
    return my dumpElem(window 1, 0)
  end tell
end tell
"""
    output = _osascript(script, check=False, timeout=12)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _dump_accessibility_records(root: Any = None, max_depth: int = 14) -> List[Dict[str, Any]]:
    AS = _application_services()
    if AS is None:
        return []
    if root is None:
        try:
            pid = _find_app_pid()
            app = AS.AXUIElementCreateApplication(pid)
            err, windows = AS.AXUIElementCopyAttributeValue(app, "AXWindows", None)
            if err != 0 or not windows:
                return []
            root = list(windows)[0]
        except Exception:
            return []

    records: List[Dict[str, Any]] = []
    queue: List[Tuple[Any, int]] = [(root, 0)]
    while queue:
        element, depth = queue.pop(0)
        role = _ax_get(AS, element, "AXRole")
        text = _ax_text(AS, element, role)
        pos = _ax_position(AS, element)
        size = _ax_size(AS, element)
        if text not in (None, "") and pos:
            records.append(
                {
                    "role": role,
                    "text": str(text),
                    "pos": pos,
                    "size": size,
                    "depth": depth,
                }
            )
        if depth >= max_depth:
            continue
        children = _ax_get(AS, element, "AXChildren")
        if children:
            queue.extend((child, depth + 1) for child in list(children))
    return records


def _extract_visible_table_text(window_rect: Dict[str, int]) -> str:
    records = _dump_accessibility_records()
    if not records:
        return ""

    x_min = window_rect["x"] + 275
    x_max = window_rect["x"] + min(window_rect["width"] - 150, 1265)
    y_min = window_rect["y"] + 455
    y_max = window_rect["y"] + window_rect["height"] - 25
    table_records = [
        record
        for record in records
        if record.get("pos")
        and x_min <= record["pos"][0] <= x_max
        and y_min <= record["pos"][1] <= y_max
        and _clean_ax_value(record.get("text")) not in {"持仓", "成交", "委托", "资金", "查询"}
    ]
    if not table_records:
        return ""

    groups = _group_records_by_y(table_records)
    header_index = _find_table_header_group(groups)
    if header_index is None:
        return ""

    headers = _dedupe_preserve_order(
        _clean_ax_value(record.get("text"))
        for record in sorted(groups[header_index], key=lambda item: item["pos"][0])
    )
    headers = [header for header in headers if header]
    if len(headers) < 2:
        return ""

    rows: List[List[str]] = []
    for group in groups[header_index + 1 :]:
        ordered = sorted(group, key=lambda item: item["pos"][0])
        values = [_clean_ax_value(record.get("text")) for record in ordered]
        values = [value for value in values if value]
        if len(values) < 2:
            continue
        if values == headers:
            continue
        rows.append(_fit_row_to_headers(values, headers))

    if not rows:
        return "\t".join(headers) + "\n"
    return "\t".join(headers) + "\n" + "\n".join("\t".join(row) for row in rows) + "\n"


def _find_table_header_group(groups: List[List[Dict[str, Any]]]) -> Optional[int]:
    best_index: Optional[int] = None
    best_score = 0
    for index, group in enumerate(groups):
        texts = [_clean_ax_value(record.get("text")) for record in group]
        score = sum(1 for text in texts if _looks_like_table_header(text))
        if score > best_score and len(texts) >= 2:
            best_index = index
            best_score = score
    return best_index if best_score >= 2 else None


def _looks_like_table_header(text: str) -> bool:
    return text in {
        "发生日期",
        "发生时间",
        "日期",
        "时间",
        "证券代码",
        "证券名称",
        "股票代码",
        "股票名称",
        "操作",
        "买卖方向",
        "委托价格",
        "委托数量",
        "成交价格",
        "成交数量",
        "成交金额",
        "资金余额",
        "股票余额",
        "可用数量",
        "成本价",
        "最新价",
        "参考市值",
        "浮动盈亏",
        "盈亏比例",
        "摘要",
        "备注",
        "币种",
        "货币单位",
    }


def _fit_row_to_headers(values: List[str], headers: List[str]) -> List[str]:
    if len(values) >= len(headers):
        return values[: len(headers)]
    return values + [""] * (len(headers) - len(values))


def _group_records_by_y(records: List[Dict[str, Any]], tolerance: float = 7.0) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    for record in sorted(records, key=lambda item: (item["pos"][1], item["pos"][0])):
        y = record["pos"][1]
        if not groups or abs(groups[-1][0]["pos"][1] - y) > tolerance:
            groups.append([record])
        else:
            groups[-1].append(record)
    return groups


def _dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _application_services() -> Any:
    try:
        import ApplicationServices as AS  # type: ignore
    except Exception:
        return None
    return AS


def _find_app_pid() -> int:
    for command in (["pgrep", "-x", APP_NAME], ["pgrep", "-f", APP_NAME]):
        try:
            output = subprocess.check_output(command, text=True, timeout=4)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        for line in output.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
    raise RuntimeError("东方财富经典版 is not running")


def _ax_text(AS: Any, element: Any, role: Any) -> Optional[str]:
    title = _ax_get(AS, element, "AXTitle")
    value = _ax_get(AS, element, "AXValue")
    description = _ax_get(AS, element, "AXDescription")
    if role == "AXStaticText" and value not in (None, ""):
        return str(value)
    if title not in (None, ""):
        return str(title)
    if value not in (None, "") and str(value) != "None":
        return str(value)
    if description not in (None, ""):
        return str(description)
    return None


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


def _ocr_window_text(window_rect: Dict[str, int]) -> str:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return ""
    if window_rect["width"] <= 0 or window_rect["height"] <= 0:
        return ""
    with tempfile.TemporaryDirectory(prefix="eastmoney-ui-ocr-") as tmpdir:
        screenshot = Path(tmpdir) / "window.png"
        region = (
            f"{window_rect['x']},{window_rect['y']},"
            f"{window_rect['width']},{window_rect['height']}"
        )
        try:
            capture = subprocess.run(
                ["screencapture", "-x", "-R", region, str(screenshot)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
        except subprocess.TimeoutExpired:
            return ""
        if capture.returncode != 0 or not screenshot.exists():
            return ""
        try:
            completed = subprocess.run(
                [tesseract, str(screenshot), "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=12,
            )
        except subprocess.TimeoutExpired:
            return ""
        if completed.returncode != 0:
            return ""
        return completed.stdout


def _click_relative(window_rect: Dict[str, int], relative_xy: Any) -> None:
    x = window_rect["x"] + int(relative_xy[0])
    y = window_rect["y"] + int(relative_xy[1])
    script = f"""
tell application "System Events"
  tell process "{APP_NAME}"
    click at {{{x}, {y}}}
  end tell
end tell
"""
    _osascript(script, check=False)


def _copy_focused_table() -> None:
    script = f"""
tell application "System Events"
  tell process "{APP_NAME}"
    keystroke "a" using command down
    delay 0.15
    keystroke "c" using command down
    delay 0.25
  end tell
end tell
"""
    _osascript(script, check=False)


def _osascript(script: str, check: bool = True, timeout: int = 8) -> str:
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        if check:
            raise
        return ""
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    if completed.returncode != 0:
        return ""
    return completed.stdout
