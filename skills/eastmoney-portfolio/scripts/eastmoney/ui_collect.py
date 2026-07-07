"""
Read-only EastMoney trading-window collection.

This module automates the already-open EastMoney Mac application only through
normal UI actions: activate app, open the trade page, inspect accessibility
labels, and copy visible table text. It never reads credentials, cookies,
sessions, signatures, raw protocol payloads, or submits trading actions.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from eastmoney.trade_export import ParsedTradeRow, parse_number, parse_trade_export_text


APP_NAME = "东方财富经典版"
TRADE_KEY_CODE = 111  # F12 in the classic Mac client.

TAB_SPECS = [
    {
        "tab": "assets",
        "label": "资产",
        "kind": "broker_asset_snapshot",
        "relative_click": (250, 455),
    },
    {
        "tab": "positions",
        "label": "持仓",
        "kind": "broker_position_detail",
        "relative_click": (300, 455),
    },
    {
        "tab": "executions",
        "label": "成交",
        "kind": "broker_trade_execution",
        "relative_click": (355, 455),
    },
    {
        "tab": "entrusts",
        "label": "委托",
        "kind": "broker_entrust_order",
        "relative_click": (410, 455),
    },
    {
        "tab": "funds",
        "label": "资金",
        "kind": "broker_fund_flow",
        "relative_click": (465, 455),
    },
]

TABLE_RELATIVE_CLICK = (700, 520)

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
    ax_lines = _dump_accessibility_lines()
    snapshot.ax_line_count = len(ax_lines)
    snapshot.account = parse_ax_trade_state(ax_lines)

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
            if table.status != "captured":
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


def copy_trade_tables(window_rect: Dict[str, int]) -> List[CopiedTable]:
    tables: List[CopiedTable] = []
    with ClipboardSnapshot() as clipboard:
        for spec in TAB_SPECS:
            _click_relative(window_rect, spec["relative_click"])
            time.sleep(0.35)
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
