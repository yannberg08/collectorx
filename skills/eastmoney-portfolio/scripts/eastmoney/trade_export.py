"""
Parse EastMoney trade-interface tables into normalized strong evidence rows.

The parser accepts table text copied from the trading interface and compatible
user-owned files saved from the trading interface. It does not read login
material or raw transport payloads.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SUPPORTED_EXPORT_SUFFIXES = {".csv", ".tsv", ".txt", ".json"}


@dataclass
class ParsedTradeRow:
    kind: str
    data: Dict[str, Any]
    row_number: int
    time: Optional[str] = None


ALIASES = {
    "symbol": ["证券代码", "股票代码", "代码", "证券编号"],
    "name": ["证券名称", "股票名称", "名称"],
    "market": ["交易市场", "市场", "市场名称", "市场代码"],
    "side": ["买卖方向", "买卖标志", "操作", "委托方向", "业务名称"],
    "date": ["日期", "发生日期", "成交日期", "委托日期", "交易日期"],
    "time": ["时间", "发生时间", "成交时间", "委托时间", "交易时间"],
    "price": ["成交价格", "成交价", "价格"],
    "entrust_price": ["委托价格", "委托价"],
    "quantity": ["成交数量", "成交股数", "数量", "发生数量"],
    "entrust_quantity": ["委托数量", "委托股数"],
    "filled_quantity": ["成交数量", "已成交数量", "成交股数"],
    "cancel_quantity": ["撤单数量", "撤销数量"],
    "amount": ["成交金额", "发生金额", "金额"],
    "fee": ["手续费", "交易费用"],
    "tax": ["印花税"],
    "transfer_fee": ["过户费"],
    "order_id": ["委托编号", "委托号", "合同编号", "合同号", "申报编号"],
    "execution_id": ["成交编号", "成交号"],
    "order_status": ["委托状态", "状态", "成交状态"],
    "account_id": ["资金账号", "客户号", "客户代码", "账户", "账号"],
    "shareholder_account": ["股东账号", "股东代码", "证券账号"],
    "position_quantity": ["持仓数量", "证券数量", "股票余额", "当前持仓", "股份余额"],
    "available_quantity": ["可用数量", "可卖数量", "股份可用", "可用余额"],
    "frozen_quantity": ["冻结数量", "冻结余额"],
    "cost_price": ["成本价", "成本价格", "持仓成本价"],
    "market_price": ["最新价", "当前价", "市价", "参考价格"],
    "market_value": ["市值", "参考市值", "证券市值", "股票市值", "总市值", "最新市值"],
    "profit_loss": ["盈亏", "浮动盈亏", "参考盈亏", "总盈亏", "持仓盈亏", "当日参考盈亏"],
    "profit_loss_ratio": ["盈亏比例", "盈亏率", "收益率", "盈亏比"],
    "total_asset": ["总资产", "资产总值", "资产总额"],
    "available_cash": ["可用资金", "可用金额"],
    "withdrawable_cash": ["可取资金", "可取金额"],
    "cash_balance": ["资金余额", "现金余额"],
    "frozen_cash": ["冻结资金", "冻结金额"],
    "fund_balance": ["资金余额", "余额"],
    "currency": ["币种", "货币单位"],
    "summary": ["摘要", "备注", "说明"],
}

KIND_LABELS = {
    "broker_asset_snapshot": "资产快照",
    "broker_position_detail": "持仓明细",
    "broker_trade_execution": "成交明细",
    "broker_entrust_order": "委托明细",
    "broker_fund_flow": "资金流水",
}


def discover_export_files(paths: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for path in paths:
        path = path.expanduser()
        if path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXPORT_SUFFIXES:
                    files.append(candidate)
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXPORT_SUFFIXES:
            files.append(path)
    return _dedupe_paths(files)


def parse_trade_export_file(path: Path, forced_kind: str = "auto") -> List[ParsedTradeRow]:
    path = path.expanduser()
    rows = _read_rows(path)
    return parse_normalized_rows(rows, source_name=path.name, forced_kind=forced_kind)


def parse_trade_export_text(
    text: str,
    source_name: str = "eastmoney-ui-table",
    forced_kind: str = "auto",
) -> List[ParsedTradeRow]:
    rows = _read_rows_from_text(text, source_name)
    return parse_normalized_rows(rows, source_name=source_name, forced_kind=forced_kind)


def parse_normalized_rows(
    rows: List[Tuple[int, Dict[str, str]]],
    source_name: str,
    forced_kind: str = "auto",
) -> List[ParsedTradeRow]:
    if not rows:
        return []
    normalized_headers = set(rows[0][1].keys())
    detected_kind = forced_kind if forced_kind != "auto" else infer_kind(source_name, normalized_headers)
    parsed: List[ParsedTradeRow] = []
    if detected_kind == "broker_asset_snapshot":
        asset = normalize_asset_rows(rows)
        if asset:
            parsed.append(ParsedTradeRow(kind=detected_kind, data=asset, row_number=rows[0][0]))
        return parsed
    for row_number, row in rows:
        data = normalize_row(detected_kind, row)
        if data:
            parsed.append(
                ParsedTradeRow(
                    kind=detected_kind,
                    data=data,
                    row_number=row_number,
                    time=combine_datetime(data.get("date"), data.get("time")),
                )
            )
    return parsed


def infer_kind(filename: str, headers: Iterable[str]) -> str:
    header_set = set(headers)
    lower_name = filename.lower()
    if any(word in filename for word in ("资产", "资金股份", "资金状况")) or any(
        key in header_set for key in normalized_aliases("total_asset", "available_cash", "withdrawable_cash")
    ):
        return "broker_asset_snapshot"
    if any(word in filename for word in ("委托", "撤单", "订单")) or any(
        key in header_set for key in normalized_aliases("entrust_price", "entrust_quantity", "order_status")
    ):
        return "broker_entrust_order"
    if (
        any(word in filename for word in ("资金流水", "银证", "转账"))
        or (
            any(key in header_set for key in normalized_aliases("fund_balance"))
            and any(key in header_set for key in normalized_aliases("summary", "side"))
        )
    ):
        return "broker_fund_flow"
    if any(word in filename for word in ("成交", "交割", "流水")) or any(
        key in header_set for key in normalized_aliases("execution_id", "amount", "price")
    ):
        return "broker_trade_execution"
    if any(word in filename for word in ("持仓", "股份", "position")) or "position" in lower_name or any(
        key in header_set for key in normalized_aliases("position_quantity", "available_quantity", "cost_price", "market_value")
    ):
        return "broker_position_detail"
    return "broker_trade_execution"


def normalize_asset_rows(rows: List[Tuple[int, Dict[str, str]]]) -> Dict[str, Any]:
    if len(rows) >= 1:
        first = rows[0][1]
        asset = {
            "snapshot_type": "broker_export_confirmed",
            "total_asset": parse_number(pick(first, "total_asset")),
            "available_cash": parse_number(pick(first, "available_cash")),
            "withdrawable_cash": parse_number(pick(first, "withdrawable_cash")),
            "cash_balance": parse_number(pick(first, "cash_balance")),
            "frozen_cash": parse_number(pick(first, "frozen_cash")),
            "market_value": parse_number(pick(first, "market_value")),
            "profit_loss": parse_number(pick(first, "profit_loss")),
            "currency": clean_text(pick(first, "currency")),
        }
        account_id = pick(first, "account_id")
        if account_id:
            asset["account_id"] = clean_text(account_id)
            asset["account_hash"] = stable_hash(account_id)
        if any(value is not None for key, value in asset.items() if key not in {"snapshot_type"}):
            return scrub_empty(asset)

    key_value_asset: Dict[str, Any] = {"snapshot_type": "broker_export_confirmed"}
    for _, row in rows:
        key = pick_by_names(row, ["项目", "名称", "字段", "科目"])
        value = pick_by_names(row, ["数值", "金额", "值", "余额"])
        if not key:
            continue
        normalized_key = normalize_header(key)
        for target in ("total_asset", "available_cash", "withdrawable_cash", "cash_balance", "frozen_cash", "market_value", "profit_loss"):
            if normalized_key in normalized_aliases(target):
                key_value_asset[target] = parse_number(value)
    return scrub_empty(key_value_asset)


def normalize_row(kind: str, row: Dict[str, str]) -> Dict[str, Any]:
    if kind == "broker_position_detail":
        data = {
            "snapshot_type": "broker_export_confirmed",
            "symbol": clean_text(pick(row, "symbol")),
            "market": clean_text(pick(row, "market")),
            "name": clean_text(pick(row, "name")),
            "quantity": parse_number(pick(row, "position_quantity")),
            "available_quantity": parse_number(pick(row, "available_quantity")),
            "frozen_quantity": parse_number(pick(row, "frozen_quantity")),
            "cost_price": parse_number(pick(row, "cost_price")),
            "market_price": parse_number(pick(row, "market_price")),
            "market_value": parse_number(pick(row, "market_value")),
            "profit_loss": parse_number(pick(row, "profit_loss")),
            "profit_loss_ratio": parse_number(pick(row, "profit_loss_ratio")),
            "currency": clean_text(pick(row, "currency")),
        }
        add_account_fields(data, row)
        return scrub_empty(data) if data.get("symbol") or data.get("name") else {}

    if kind == "broker_trade_execution":
        data = {
            "snapshot_type": "broker_export_confirmed",
            "date": normalize_date(pick(row, "date")),
            "time": normalize_clock(pick(row, "time")),
            "symbol": clean_text(pick(row, "symbol")),
            "market": clean_text(pick(row, "market")),
            "name": clean_text(pick(row, "name")),
            "side": normalize_side(pick(row, "side")),
            "price": parse_number(pick(row, "price")),
            "quantity": parse_number(pick(row, "quantity")),
            "amount": parse_number(pick(row, "amount")),
            "fee": parse_number(pick(row, "fee")),
            "tax": parse_number(pick(row, "tax")),
            "transfer_fee": parse_number(pick(row, "transfer_fee")),
        }
        add_account_fields(data, row)
        add_identifier_field(data, "execution_id", "execution_hash", pick(row, "execution_id"))
        add_identifier_field(data, "order_id", "order_hash", pick(row, "order_id"))
        return scrub_empty(data) if data.get("symbol") or data.get("amount") is not None else {}

    if kind == "broker_entrust_order":
        data = {
            "snapshot_type": "broker_export_confirmed",
            "date": normalize_date(pick(row, "date")),
            "time": normalize_clock(pick(row, "time")),
            "symbol": clean_text(pick(row, "symbol")),
            "market": clean_text(pick(row, "market")),
            "name": clean_text(pick(row, "name")),
            "side": normalize_side(pick(row, "side")),
            "entrust_price": parse_number(pick(row, "entrust_price")),
            "entrust_quantity": parse_number(pick(row, "entrust_quantity")),
            "filled_quantity": parse_number(pick(row, "filled_quantity")),
            "cancel_quantity": parse_number(pick(row, "cancel_quantity")),
            "order_status": clean_text(pick(row, "order_status")),
        }
        add_account_fields(data, row)
        add_identifier_field(data, "order_id", "order_hash", pick(row, "order_id"))
        return scrub_empty(data) if data.get("symbol") or data.get("order_status") else {}

    if kind == "broker_fund_flow":
        data = {
            "snapshot_type": "broker_export_confirmed",
            "date": normalize_date(pick(row, "date")),
            "time": normalize_clock(pick(row, "time")),
            "business": clean_text(pick(row, "side")),
            "amount": parse_number(pick(row, "amount")),
            "fund_balance": parse_number(pick(row, "fund_balance")),
            "summary": clean_text(pick(row, "summary")),
        }
        add_account_fields(data, row)
        return scrub_empty(data) if data.get("amount") is not None or data.get("business") else {}

    return {}


def _read_rows(path: Path) -> List[Tuple[int, Dict[str, str]]]:
    if path.suffix.lower() == ".json":
        data = json.loads(_read_text(path))
        if isinstance(data, dict):
            data = data.get("rows") or data.get("data") or []
        if not isinstance(data, list):
            return []
        result = []
        for index, row in enumerate(data, 1):
            if isinstance(row, dict):
                result.append((index, normalize_row_keys(row)))
        return result

    text = _read_text(path)
    return _read_rows_from_text(text, path.name)


def _read_rows_from_text(text: str, source_name: str = "") -> List[Tuple[int, Dict[str, str]]]:
    if source_name.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            data = data.get("rows") or data.get("data") or []
        if not isinstance(data, list):
            return []
        return [
            (index, normalize_row_keys(row))
            for index, row in enumerate(data, 1)
            if isinstance(row, dict)
        ]

    sample = text[:4096]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delimiter = dialect.delimiter
    except csv.Error:
        pass
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    rows: List[Tuple[int, Dict[str, str]]] = []
    for row_number, row in enumerate(reader, 2):
        normalized = normalize_row_keys(row)
        if any(value.strip() for value in normalized.values()):
            rows.append((row_number, normalized))
    return rows


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_row_keys(row: Dict[Any, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        result[normalize_header(str(key))] = "" if value is None else str(value).strip()
    return result


def normalized_aliases(*fields: str) -> List[str]:
    values: List[str] = []
    for field in fields:
        values.extend(normalize_header(alias) for alias in ALIASES[field])
    return values


def normalize_header(value: str) -> str:
    return re.sub(r"[\s　_（）()：:]+", "", str(value or "")).lower()


def pick(row: Dict[str, str], field: str) -> str:
    return pick_by_names(row, ALIASES[field])


def pick_by_names(row: Dict[str, str], names: Iterable[str]) -> str:
    for name in names:
        value = row.get(normalize_header(name))
        if value not in (None, ""):
            return value.strip()
    return ""


def clean_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def parse_number(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text or text in {"--", "-", "—"}:
        return None
    text = text.replace(",", "").replace("，", "").replace("元", "")
    text = text.replace("%", "")
    text = re.sub(r"[^\d.+-]", "", text)
    if not text or text in {"+", "-", ".", "+.", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_side(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if "买" in text or "申购" in text:
        return "buy"
    if "卖" in text or "赎回" in text:
        return "sell"
    if "撤" in text:
        return "cancel"
    if "转入" in text or "存入" in text:
        return "in"
    if "转出" in text or "取出" in text:
        return "out"
    return text


def normalize_date(value: Any) -> Optional[str]:
    text = re.sub(r"[^\d]", "", str(value or ""))
    if len(text) >= 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return clean_text(value)


def normalize_clock(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{6}", text):
        return f"{text[:2]}:{text[2:4]}:{text[4:6]}"
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
        return text if text.count(":") == 2 else f"{text}:00"
    return text


def combine_datetime(date: Any, clock: Any) -> Optional[str]:
    date_text = normalize_date(date)
    clock_text = normalize_clock(clock)
    if date_text and clock_text:
        return f"{date_text} {clock_text}"
    return date_text


def add_account_fields(data: Dict[str, Any], row: Dict[str, str]) -> None:
    account_id = pick(row, "account_id")
    shareholder = pick(row, "shareholder_account")
    if account_id:
        data["account_id"] = clean_text(account_id)
        data["account_hash"] = stable_hash(account_id)
    if shareholder:
        data["shareholder_account"] = clean_text(shareholder)
        data["shareholder_account_hash"] = stable_hash(shareholder)


def add_identifier_field(data: Dict[str, Any], raw_key: str, hash_key: str, value: Any) -> None:
    text = str(value or "").strip()
    if text:
        data[raw_key] = text
        data[hash_key] = stable_hash(text)


def stable_hash(value: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def mask_identifier(value: str) -> str:
    value = str(value or "")
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) <= 6:
        return value[0] + "*" * (len(value) - 2) + value[-1]
    return value[:3] + "*" * max(3, len(value) - 5) + value[-2:]


def scrub_empty(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if value not in (None, "")
    }


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    result: List[Path] = []
    seen = set()
    for path in paths:
        try:
            key = str(path.expanduser().resolve())
        except FileNotFoundError:
            key = str(path.expanduser().absolute())
        if key in seen:
            continue
        seen.add(key)
        result.append(path.expanduser())
    return result
