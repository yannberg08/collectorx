"""
ths.local — Parse local Tonghuashun data files.

This module only handles user-owned local evidence. It does not call broker
APIs, scrape credentials, or treat inferred holdings as confirmed positions.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


LOCAL_XCS_SOURCE = "同花顺本机历史成交 XcsLscj"
LOCAL_XCS_SOURCE_BY_PLATFORM = {
    "mac": "同花顺Mac本机历史成交 XcsLscj",
    "windows": "同花顺Windows本机历史成交 XcsLscj",
    "generic": "同花顺本机历史成交 XcsLscj",
}
SUPPORTED_LOCAL_PLATFORMS = {"auto", "mac", "windows", "generic"}
DEFAULT_CONTAINER_DATA = (
    Path.home() / "Library" / "Containers" / "cn.com.10jqka.macstockPro" / "Data"
)

BUY_DIRECTIONS = {"买入", "配售中签"}
SELL_DIRECTIONS = {"卖出"}
BONUS_SHARE_DIRECTIONS = {"红股"}
CASH_ONLY_DIRECTIONS = {"红股派息"}
IGNORED_DIRECTIONS = {"指定交易"}


def resolve_platform(platform: str = "auto") -> str:
    """Resolve a requested local platform to the adapter name we should use."""
    if platform not in SUPPORTED_LOCAL_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    if platform != "auto":
        return platform
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    return "generic"


def local_source_label(platform: str = "auto") -> str:
    return LOCAL_XCS_SOURCE_BY_PLATFORM.get(resolve_platform(platform), LOCAL_XCS_SOURCE)


def find_xcs_lscj_files(
    container_root: Optional[str] = None,
    *,
    platform: str = "auto",
) -> List[Path]:
    """Find local XcsLscj historical trade files for the requested platform.

    Windows paths are code-level candidates. They are useful for simulation and
    future adapters, but must be verified on a real Windows Tonghuashun install.
    """
    resolved_platform = resolve_platform(platform)
    roots = _scan_roots(container_root, resolved_platform)
    found: List[Path] = []

    for root in roots:
        if not root.exists():
            continue
        for pattern in _xcs_patterns_for_platform(resolved_platform):
            for path in root.glob(pattern):
                if path.is_file() and path.name.startswith("XcsLscjDataFile_"):
                    found.append(path)

    return _dedupe_paths(found)


def build_local_probe_report(
    *,
    platform: str = "auto",
    container_root: Optional[str] = None,
    files: Optional[Iterable[Path]] = None,
) -> Dict[str, Any]:
    """Build a safe local capability report for code-level and real probes."""
    resolved_platform = resolve_platform(platform)
    file_list = _dedupe_paths(files or find_xcs_lscj_files(container_root, platform=platform))
    roots = _scan_roots(container_root, resolved_platform)

    return {
        "probe_type": "ths_local_xcs_lscj",
        "platform": {
            "requested": platform,
            "resolved": resolved_platform,
            "structure_status": (
                "verified_on_current_mac"
                if resolved_platform == "mac" and sys.platform == "darwin"
                else "candidate_rules_need_real_machine_verification"
            ),
        },
        "scan_roots": [_safe_path_label(root) for root in roots],
        "xcs_lscj": {
            "file_count": len(file_list),
            "files": [local_file_label(path) for path in file_list],
            "historical_trades": "available" if file_list else "not_found",
        },
        "unsupported_without_confirmed_snapshot": [
            "current_holding_snapshot",
            "asset_snapshot",
            "cash_balance_snapshot",
            "entrust_or_cancel_snapshot",
        ],
        "privacy_policy": {
            "full_account_ids": "masked",
            "raw_order_or_execution_ids": "hashed_after_parse",
            "credentials": "not_read",
        },
    }


def parse_xcs_lscj(file_path: str, account: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse a local XcsLscj JSON file into the same normalized record shape as CSV."""
    path = Path(file_path).expanduser()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"XcsLscj file must contain a JSON object: {path}")

    account_hint = account or extract_masked_account_hint(path) or "ths-local"
    file_label = local_file_label(path)
    source_start_date = _format_date(data.get("startdate"))
    source_end_date = _format_date(data.get("enddate"))

    records: List[Dict[str, Any]] = []
    for source_symbol, by_date in data.items():
        if source_symbol in {"startdate", "enddate"} or not isinstance(by_date, dict):
            continue
        for source_date, rows in by_date.items():
            if not isinstance(rows, list):
                continue
            for source_index, row in enumerate(rows, start=1):
                record = _parse_xcs_row(
                    row,
                    account=account_hint,
                    file_label=file_label,
                    source_symbol=source_symbol,
                    source_date=source_date,
                    source_index=source_index,
                    source_start_date=source_start_date,
                    source_end_date=source_end_date,
                )
                if record:
                    records.append(record)

    records.sort(
        key=lambda item: (
            item.get("date") or "",
            item.get("time") or "",
            item.get("code") or "",
            item.get("source_index") or 0,
        )
    )
    return records


def infer_holdings(
    records: Iterable[Dict[str, Any]],
    *,
    include_zero_quantity: bool = False,
) -> List[Dict[str, Any]]:
    """Infer estimated current holdings from historical trades.

    The result is useful for an investor avatar, but it is not a broker-confirmed
    current position snapshot. Market value and unrealized PnL stay empty.
    """
    states: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for record in sorted(
        records,
        key=lambda item: (
            item.get("date") or "",
            item.get("time") or "",
            item.get("code") or "",
            item.get("source_index") or 0,
        ),
    ):
        code = str(record.get("code") or "").strip()
        if not code:
            continue
        account = str(record.get("account") or "default")
        key = (account, code)
        state = states.setdefault(
            key,
            {
                "account": account,
                "symbol": code,
                "name": record.get("name") or "",
                "quantity": 0,
                "cost": 0.0,
                "buy_quantity": 0,
                "sell_quantity": 0,
                "bonus_quantity": 0,
                "buy_amount": 0.0,
                "sell_amount": 0.0,
                "source_trade_count": 0,
                "dividend_event_count": 0,
                "ignored_event_count": 0,
                "unmatched_sell_quantity": 0,
                "first_trade_time": None,
                "last_trade_time": None,
            },
        )

        if record.get("name"):
            state["name"] = record.get("name")

        state["source_trade_count"] += 1
        trade_time = _record_time(record)
        if trade_time and not state["first_trade_time"]:
            state["first_trade_time"] = trade_time
        if trade_time:
            state["last_trade_time"] = trade_time

        direction = str(record.get("direction") or "").strip()
        quantity = max(_to_int(record.get("quantity")), 0)
        amount = max(_to_float(record.get("amount")), 0.0)

        if direction in BUY_DIRECTIONS:
            state["quantity"] += quantity
            state["cost"] += amount
            state["buy_quantity"] += quantity
            state["buy_amount"] += amount
        elif direction in SELL_DIRECTIONS:
            previous_quantity = state["quantity"]
            state["sell_quantity"] += quantity
            state["sell_amount"] += amount
            if previous_quantity <= 0:
                state["unmatched_sell_quantity"] += quantity
                state["quantity"] = 0
                state["cost"] = 0.0
                continue

            reduce_quantity = min(quantity, previous_quantity)
            average_cost = state["cost"] / previous_quantity if previous_quantity else 0.0
            state["quantity"] = max(previous_quantity - quantity, 0)
            state["cost"] = max(state["cost"] - average_cost * reduce_quantity, 0.0)
            if quantity > previous_quantity:
                state["unmatched_sell_quantity"] += quantity - previous_quantity
                state["cost"] = 0.0
        elif direction in BONUS_SHARE_DIRECTIONS:
            state["quantity"] += quantity
            state["bonus_quantity"] += quantity
        elif direction in CASH_ONLY_DIRECTIONS:
            state["dividend_event_count"] += 1
        elif direction in IGNORED_DIRECTIONS:
            state["ignored_event_count"] += 1

    holdings: List[Dict[str, Any]] = []
    for state in states.values():
        quantity = int(state["quantity"])
        if quantity <= 0 and not include_zero_quantity:
            continue
        cost = round(float(state["cost"]), 4)
        limitations = [
            "estimated_from_historical_trades",
            "not_broker_confirmed_current_snapshot",
            "market_value_and_unrealized_pnl_not_collected",
        ]
        confidence = "medium"
        if state["unmatched_sell_quantity"] > 0:
            confidence = "low"
            limitations.append("history_may_not_include_opening_position")

        holdings.append(
            {
                "account": state["account"],
                "symbol": state["symbol"],
                "name": state["name"],
                "quantity": quantity,
                "cost": cost,
                "avg_cost": round(cost / quantity, 6) if quantity else 0.0,
                "market_value": None,
                "unrealized_pnl": None,
                "evidence_level": "estimated",
                "confidence": confidence,
                "snapshot_type": "estimated_from_historical_trades",
                "is_confirmed": False,
                "source_trade_count": state["source_trade_count"],
                "buy_quantity": state["buy_quantity"],
                "sell_quantity": state["sell_quantity"],
                "bonus_quantity": state["bonus_quantity"],
                "buy_amount": round(float(state["buy_amount"]), 4),
                "sell_amount": round(float(state["sell_amount"]), 4),
                "dividend_event_count": state["dividend_event_count"],
                "unmatched_sell_quantity": state["unmatched_sell_quantity"],
                "first_trade_time": state["first_trade_time"],
                "last_trade_time": state["last_trade_time"],
                "limitations": limitations,
            }
        )

    return sorted(holdings, key=lambda item: (-abs(item["cost"]), item["symbol"]))


def build_gap_status(records: List[Dict[str, Any]], holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Describe what the local collector did and did not find."""
    return {
        "profile_type": "ths_local_collection_gap_status",
        "historical_trade_records": len(records),
        "estimated_holding_candidates": len(holdings),
        "current_holding_snapshot": "not_found_in_local_plaintext",
        "asset_snapshot": "not_found_in_local_plaintext",
        "cash_balance_snapshot": "not_found_in_local_plaintext",
        "entrust_or_cancel_snapshot": "not_found_in_local_plaintext",
        "estimated_holdings_generated": bool(holdings),
        "evidence_policy": "confirmed_snapshots_required_for_current_assets",
        "next_best_collection": [
            "manual_broker_position_export",
            "controlled_gui_capture_after_user_review",
            "official_broker_or_tonghuashun_export_if_available",
        ],
    }


def extract_masked_account_hint(path: Path) -> Optional[str]:
    match = re.search(r"XcsLscjDataFile_\d+_(\d{6,})", path.name)
    if not match:
        return None
    return mask_numeric_identifier(match.group(1))


def local_file_label(path: Path) -> str:
    """Return a useful raw reference without exposing full local account ids."""
    name = re.sub(
        r"(XcsLscjDataFile_\d+_)(\d{6,})",
        lambda match: f"{match.group(1)}{mask_numeric_identifier(match.group(2))}",
        path.name,
    )
    name = re.sub(r"\d{6,}", lambda match: mask_numeric_identifier(match.group(0)), name)
    parent = re.sub(
        r"\d{6,}",
        lambda match: mask_numeric_identifier(match.group(0)),
        path.parent.name,
    )
    return str(Path(parent) / name)


def mask_numeric_identifier(identifier: str) -> str:
    text = str(identifier)
    if len(text) < 7:
        return text
    return f"{text[:3]}****{text[-3:]}"


def _scan_roots(container_root: Optional[str], platform: str) -> List[Path]:
    if container_root:
        return [Path(container_root).expanduser()]
    if platform == "mac":
        return [DEFAULT_CONTAINER_DATA]
    if platform == "windows":
        return [
            Path.home() / "AppData" / "Roaming" / "同花顺",
            Path.home() / "AppData" / "Local" / "同花顺",
            Path("C:/ProgramData/同花顺"),
        ]
    return [Path.home()]


def _xcs_patterns_for_platform(platform: str) -> List[str]:
    if platform == "mac":
        return [
            "Documents/XcsFold/XcsLscjDataFile_*",
            "XcsFold/XcsLscjDataFile_*",
            "**/XcsFold/XcsLscjDataFile_*",
        ]
    if platform == "windows":
        return [
            "XcsFold/XcsLscjDataFile_*",
            "AppData/Roaming/同花顺/XcsFold/XcsLscjDataFile_*",
            "AppData/Local/同花顺/XcsFold/XcsLscjDataFile_*",
            "Users/*/AppData/Roaming/同花顺/XcsFold/XcsLscjDataFile_*",
            "Users/*/AppData/Local/同花顺/XcsFold/XcsLscjDataFile_*",
            "ProgramData/同花顺/**/XcsLscjDataFile_*",
            "**/XcsFold/XcsLscjDataFile_*",
            "**/XcsLscjDataFile_*",
        ]
    return [
        "XcsFold/XcsLscjDataFile_*",
        "**/XcsFold/XcsLscjDataFile_*",
        "**/XcsLscjDataFile_*",
    ]


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    result: List[Path] = []
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append(Path(key))
    return sorted(result)


def _safe_path_label(path: Path) -> str:
    text = str(path.expanduser())
    home = str(Path.home())
    if text == home:
        text = "~"
    elif text.startswith(home + "/"):
        text = "~/" + text[len(home) + 1 :]
    return re.sub(r"\d{6,}", lambda match: mask_numeric_identifier(match.group(0)), text)


def _parse_xcs_row(
    row: Dict[str, Any],
    *,
    account: str,
    file_label: str,
    source_symbol: str,
    source_date: str,
    source_index: int,
    source_start_date: Optional[str],
    source_end_date: Optional[str],
) -> Optional[Dict[str, Any]]:
    code = str(row.get("zqdm") or source_symbol or "").strip()
    if not code:
        return None

    date = _format_date(row.get("cjrq") or source_date)
    time = str(row.get("cjsj") or "").strip()
    price = _to_float(row.get("cjjg"))
    quantity = _to_int(row.get("cjsl"))
    amount = round(price * quantity, 4) if price and quantity else 0.0
    direction = str(row.get("czmc") or "").strip()

    return {
        "date": date,
        "time": time,
        "code": code,
        "name": str(row.get("zqmc") or "").strip(),
        "direction": direction,
        "price": price,
        "quantity": quantity,
        "amount": amount,
        "fee": 0.0,
        "tax": 0.0,
        "account": account,
        "source_format": "ths_xcs_lscj",
        "source_file": file_label,
        "source_symbol": str(source_symbol),
        "source_date": str(source_date),
        "source_index": source_index,
        "source_start_date": source_start_date,
        "source_end_date": source_end_date,
        "raw_order_hash": _hash_optional(row.get("htbh")),
        "raw_execution_hash": _hash_optional(row.get("cjbh")),
    }


def _format_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text.replace("/", "-")


def _record_time(record: Dict[str, Any]) -> Optional[str]:
    date = record.get("date")
    time = record.get("time") or "00:00:00"
    if not date:
        return None
    return f"{date}T{time}+08:00"


def _to_float(value: Any) -> float:
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value)) if value not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def _hash_optional(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"
