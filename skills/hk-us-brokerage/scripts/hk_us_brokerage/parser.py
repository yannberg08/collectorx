"""Parse user-authorized HK/US brokerage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "hk-us-brokerage"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="hk_us_brokerage_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield child
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(path)
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return [{str(key): value for key, value in row.items() if key is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_records(json.loads(text))
    return [row if isinstance(row, dict) else {"value": row} for row in rows]


def sniff_delimiter(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    try:
        return csv.Sniffer().sniff(text, delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    for key in ("assets", "positions", "holdings", "executions", "trades", "orders", "cashflows", "dividends", "fx", "records", "items", "data"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
    return [loaded]


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    subtype = infer_subtype(record, path)
    broker = infer_broker(record, path)
    data = {
        "subtype": subtype,
        "broker": broker,
        "account_id": first(record, ["account_id", "account", "账户", "账号", "账户号"]),
        "currency": first(record, ["currency", "ccy", "币种"]),
        "market": normalize_market(first(record, ["market", "exchange", "市场", "交易所"])),
        "symbol": first(record, ["symbol", "code", "ticker", "证券代码", "代码"]),
        "name": first(record, ["name", "security_name", "stock_name", "证券名称", "名称"]),
        "side": normalize_side(first(record, ["side", "action", "direction", "买卖", "方向", "操作"])),
        "status": first(record, ["status", "order_status", "委托状态", "状态"]),
        "quantity": number(first(record, ["quantity", "qty", "shares", "filled_qty", "成交数量", "数量", "持仓数量"])),
        "order_quantity": number(first(record, ["order_quantity", "order_qty", "委托数量"])),
        "filled_quantity": number(first(record, ["filled_quantity", "filled_qty", "成交数量"])),
        "price": number(first(record, ["price", "avg_price", "成交价格", "成交均价", "价格"])),
        "limit_price": number(first(record, ["limit_price", "委托价格", "限价"])),
        "avg_cost": number(first(record, ["avg_cost", "cost_price", "成本价", "平均成本"])),
        "market_price": number(first(record, ["market_price", "last_price", "现价", "最新价"])),
        "amount": number(first(record, ["amount", "成交金额", "发生金额", "金额"])),
        "market_value": number(first(record, ["market_value", "市值", "持仓市值"])),
        "cash": number(first(record, ["cash", "cash_balance", "现金", "现金余额"])),
        "total_assets": number(first(record, ["total_assets", "net_liquidation", "assets", "总资产", "净资产"])),
        "buying_power": number(first(record, ["buying_power", "购买力"])),
        "fees": number(first(record, ["fees", "commission", "fee", "费用", "佣金"])),
        "pnl": number(first(record, ["pnl", "unrealized_pnl", "realized_pnl", "盈亏", "浮动盈亏", "已实现盈亏"])),
        "pnl_rate": first(record, ["pnl_rate", "收益率", "盈亏比例"]),
        "order_id": first(record, ["order_id", "委托编号", "订单号"]),
        "trade_id": first(record, ["trade_id", "execution_id", "成交编号", "成交号"]),
        "flow_type": normalize_flow_type(first(record, ["flow_type", "cashflow_type", "type", "类型", "业务类型"])),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "")}
    event_time = first(record, ["time", "date", "trade_time", "order_time", "settled_at", "交易时间", "成交时间", "委托时间", "日期"])
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, broker, subtype, json.dumps(sanitized(record), ensure_ascii=False, sort_keys=True)),
        "collector": COLLECTOR,
        "source": "港美股券商用户授权只读数据",
        "owner_scope": "personal",
        "kind": kind_for_subtype(subtype),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "row": row,
            "broker": broker,
            "subtype": subtype,
        },
        "privacy": {"sensitive": True, "local_only": True, "contains": ["money", "portfolio", "trade"]},
        "wiki_targets": wiki_targets_for_subtype(subtype),
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "港美股券商授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "subtype": "collector_gap",
            "gap": reason,
            "message": "No user-authorized Futu/Tiger/IBKR export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["money", "portfolio", "trade"]},
        "wiki_targets": ["investor.data_quality.collection_gaps"],
    }


def infer_subtype(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["subtype", "record_type", "type", "类型", "业务类型", "sheet"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path).lower()
    probe = (explicit or text).lower()
    if any(token in probe for token in ("asset", "balance", "净资产", "总资产", "现金", "购买力")):
        return "asset_snapshot"
    if any(token in probe for token in ("position", "holding", "持仓", "库存")):
        return "position"
    if any(token in probe for token in ("execution", "trade", "fill", "成交", "成交记录")):
        return "execution"
    if any(token in probe for token in ("order", "委托", "订单")):
        return "order"
    if any(token in probe for token in ("cashflow", "资金流水", "入金", "出金", "利息", "费用")):
        return "cashflow"
    if any(token in probe for token in ("dividend", "分红", "派息")):
        return "dividend"
    if any(token in probe for token in ("forex", "fx", "currency exchange", "换汇")):
        return "fx"
    if any(key in record for key in ("symbol", "code", "证券代码", "持仓数量", "market_value")):
        return "position"
    return "execution"


def infer_broker(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["broker", "platform", "券商", "平台"])
    text = (explicit or "") + " " + json.dumps(record, ensure_ascii=False) + " " + str(path)
    lowered = text.lower()
    if "futu" in lowered or "富途" in text or "moomoo" in lowered:
        return "futu"
    if "tiger" in lowered or "老虎" in text:
        return "tiger"
    if "ibkr" in lowered or "interactive brokers" in lowered or "盈透" in text:
        return "ibkr"
    return "unknown"


def kind_for_subtype(subtype: str) -> str:
    if subtype == "position":
        return "holding"
    if subtype in {"execution", "order"}:
        return "trade"
    return "other"


def wiki_targets_for_subtype(subtype: str) -> List[str]:
    targets = {
        "asset_snapshot": ["investor.risk_portfolio.current_assets", "external.capital.assets"],
        "position": ["investor.risk_portfolio.current_positions", "investor.risk_portfolio.portfolio_constraints"],
        "execution": ["investor.record_review.decision_log", "investor.execution.orders"],
        "order": ["investor.execution.orders", "investor.behavior.execution_discipline"],
        "cashflow": ["external.capital.cashflows", "investor.risk_portfolio.portfolio_constraints"],
        "dividend": ["external.capital.cashflows", "investor.risk_portfolio.current_positions"],
        "fx": ["external.capital.cashflows", "investor.risk_portfolio.portfolio_constraints"],
    }
    return targets.get(subtype, ["investor.data_quality.collection_gaps"])


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in events)
    broker_counts = Counter((event.get("data") or {}).get("broker", "unknown") for event in events)
    gap_only = bool(events) and set(subtype_counts) == {"collector_gap"}
    return {
        "schema": "hk_us_brokerage.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "broker_counts": dict(sorted(broker_counts.items())),
        "collection_readiness": {
            "status": "needs_hk_us_brokerage_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_hk_us_trade_boundary": False,
            "brokerage_boundary_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized Futu/Tiger/IBKR read-only export." if gap_only else "Use as strong trade evidence; continue per-broker real account validation.",
        },
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    usable_events = 0
    for event in events:
        if (event.get("data") or {}).get("subtype") == "collector_gap":
            continue
        usable_events += 1
        for target in event.get("wiki_targets", []):
            by_target[target].append(event)
    return {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": usable_events,
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
        },
        "coverage_summary": {
            "strong_trade_source": True,
            "complete_trade_boundary_claimed": False,
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("HK$", "").replace("US$", "").replace("$", "").replace("￥", "").replace("%", "").strip()
    if text in {"--", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_side(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.lower()
    if any(token in text for token in ("buy", "bot", "bought", "买入", "买")):
        return "buy"
    if any(token in text for token in ("sell", "sld", "sold", "卖出", "卖")):
        return "sell"
    return value


def normalize_flow_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.lower()
    if any(token in text for token in ("deposit", "入金", "存入")):
        return "deposit"
    if any(token in text for token in ("withdraw", "出金", "取出")):
        return "withdraw"
    if any(token in text for token in ("dividend", "分红", "派息")):
        return "dividend"
    if any(token in text for token in ("interest", "利息")):
        return "interest"
    if any(token in text for token in ("fee", "费用", "佣金")):
        return "fee"
    if any(token in text for token in ("fx", "forex", "exchange", "换汇")):
        return "fx"
    return value


def normalize_market(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.upper()
    if "HK" in text or "港" in value:
        return "HK"
    if "US" in text or "NYSE" in text or "NASDAQ" in text or "美" in value:
        return "US"
    return value


def sanitized(record: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in record.items():
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
            continue
        clean[key] = value
    return clean


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
