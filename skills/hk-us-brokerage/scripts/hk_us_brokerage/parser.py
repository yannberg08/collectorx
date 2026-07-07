"""Parse user-authorized HK/US brokerage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency for runtime installs
    openpyxl = None


COLLECTOR = "hk-us-brokerage"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_RECORD_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xlsx", ".xlsm"}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SUPPORTED_ZIP_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
EXPECTED_HK_US_BROKERS = ("futu", "tiger", "ibkr")
EXPECTED_STRONG_TRADE_SUBTYPES = ("asset_snapshot", "position", "execution", "order", "cashflow", "dividend", "fx")
RECOMMENDED_STRONG_FIELDS = (
    "total_assets",
    "cash",
    "buying_power",
    "net_liquidation",
    "margin_requirement",
    "maintenance_margin",
    "symbol",
    "quantity",
    "avg_cost",
    "market_value",
    "side",
    "price",
    "amount",
    "fees",
    "tax",
    "order_quantity",
    "status",
    "flow_type",
    "gross_amount",
    "net_amount",
    "from_amount",
    "to_amount",
    "exchange_rate",
    "settlement_date",
    "ex_date",
    "pay_date",
)
SECTION_SUBTYPES = {
    "assets": "asset_snapshot",
    "balances": "asset_snapshot",
    "summary": "asset_snapshot",
    "positions": "position",
    "holdings": "position",
    "executions": "execution",
    "trades": "execution",
    "fills": "execution",
    "orders": "order",
    "cashflows": "cashflow",
    "cash_flows": "cashflow",
    "funds": "cashflow",
    "dividends": "dividend",
    "fx": "fx",
    "forex": "fx",
}


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
    return events or [gap_event(collected_at=collected_at, reason="hk_us_brokerage_records_empty")]


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and is_supported_path(child):
                    yield child
        elif path.is_file() and is_supported_path(path):
            yield path


def is_supported_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return parse_zip(path)
    if suffix in {".csv", ".tsv"}:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return parse_table_text(text, suffix=suffix, path_label=str(path))
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path, path_label=str(path))
    text = path.read_text(encoding="utf-8-sig").strip()
    return parse_json_text(text, suffix=suffix, path_label=str(path))


def parse_json_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_records(json.loads(text))
    records = [row if isinstance(row, dict) else {"value": row} for row in rows]
    for record in records:
        record.setdefault("path", path_label)
    return records


def parse_table_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter_text(text)
    records = [{str(key): value for key, value in row.items() if key is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    for record in records:
        record.setdefault("path", path_label)
    return records


def sniff_delimiter(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    return sniff_delimiter_text(text)


def sniff_delimiter_text(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text, delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_workbook(path_or_stream: Any, *, path_label: str) -> List[Dict[str, Any]]:
    if openpyxl is None:
        return []
    workbook = openpyxl.load_workbook(path_or_stream, read_only=True, data_only=True)
    records: List[Dict[str, Any]] = []
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            header_index = next((idx for idx, row in enumerate(rows) if any(cell not in (None, "") for cell in row)), None)
            if header_index is None:
                continue
            headers = [str(cell).strip() if cell not in (None, "") else f"column_{idx + 1}" for idx, cell in enumerate(rows[header_index])]
            for row in rows[header_index + 1 :]:
                record = {
                    headers[idx]: value
                    for idx, value in enumerate(row)
                    if idx < len(headers) and value not in (None, "")
                }
                if record:
                    record["sheet"] = sheet.title
                    record.setdefault("path", path_label)
                    record.setdefault("source_section", sheet.title)
                    records.append(record)
    finally:
        workbook.close()
    return records


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            if should_skip_zip_member(member):
                continue
            suffix = Path(member.filename).suffix.lower()
            path_label = f"{path.name}::{member.filename}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                else:
                    parsed = parse_workbook(io.BytesIO(archive.read(member)), path_label=path_label)
            except Exception:
                parsed = []
            records.extend(parsed)
    return records


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    member_path = Path(member.filename)
    if member.is_dir():
        return True
    if member_path.is_absolute() or ".." in member_path.parts:
        return True
    return member_path.suffix.lower() not in SUPPORTED_ZIP_EXTENSIONS


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    context = {
        str(key): value
        for key, value in loaded.items()
        if not isinstance(value, (list, dict)) and value not in (None, "")
    }
    collected: List[Any] = []
    for key in (
        "assets",
        "balances",
        "summary",
        "positions",
        "holdings",
        "executions",
        "trades",
        "fills",
        "orders",
        "cashflows",
        "cash_flows",
        "funds",
        "dividends",
        "fx",
        "forex",
        "records",
        "items",
        "data",
    ):
        value = loaded.get(key)
        if isinstance(value, list):
            collected.extend(with_section_context(item, key, context) for item in value)
        elif isinstance(value, dict):
            collected.extend(with_section_context(item, key, context) for item in extract_records(value))
    if collected:
        return collected
    return [loaded]


def with_section_context(item: Any, section: str, context: Dict[str, Any]) -> Any:
    if not isinstance(item, dict):
        return {"value": item, "source_section": section, "subtype": SECTION_SUBTYPES.get(section)}
    record = {**context, **item}
    record.setdefault("source_section", section)
    if section in SECTION_SUBTYPES:
        record.setdefault("subtype", SECTION_SUBTYPES[section])
    return record


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    path_label = first(record, ["path", "file", "source_path"]) or str(path)
    subtype = infer_subtype(record, path_label)
    broker = infer_broker(record, path_label)
    flow_type = (
        normalize_flow_type(first(record, ["flow_type", "cashflow_type", "type", "类型", "业务类型"]))
        if subtype in {"cashflow", "dividend", "fx"}
        else None
    )
    data = {
        "subtype": subtype,
        "broker": broker,
        "account_id": first(record, ["account_id", "account", "账户", "账号", "账户号"]),
        "currency": first(record, ["currency", "ccy", "币种"]),
        "base_currency": first(record, ["base_currency", "base_ccy", "基础币种", "本位币"]),
        "from_currency": first(record, ["from_currency", "from_ccy", "卖出币种", "换出币种"]),
        "to_currency": first(record, ["to_currency", "to_ccy", "买入币种", "换入币种"]),
        "market": normalize_market(first(record, ["market", "exchange", "市场", "交易所"])),
        "exchange": first(record, ["exchange", "venue", "交易所", "成交市场"]),
        "symbol": first(record, ["symbol", "code", "ticker", "证券代码", "代码"]),
        "isin": first(record, ["isin", "ISIN"]),
        "cusip": first(record, ["cusip", "CUSIP"]),
        "name": first(record, ["name", "security_name", "stock_name", "证券名称", "名称"]),
        "side": normalize_side(first(record, ["side", "action", "direction", "买卖", "方向", "操作"])),
        "status": normalize_status(first(record, ["status", "order_status", "委托状态", "状态"])),
        "order_type": first(record, ["order_type", "type", "订单类型", "委托类型"]),
        "time_in_force": first(record, ["time_in_force", "tif", "有效期", "订单有效期"]),
        "quantity": number(first(record, ["quantity", "qty", "shares", "filled_qty", "成交数量", "数量", "持仓数量"])),
        "order_quantity": number(first(record, ["order_quantity", "order_qty", "委托数量"])),
        "filled_quantity": number(first(record, ["filled_quantity", "filled_qty", "成交数量"])),
        "price": number(first(record, ["price", "avg_price", "成交价格", "成交均价", "价格"])),
        "limit_price": number(first(record, ["limit_price", "委托价格", "限价"])),
        "avg_cost": number(first(record, ["avg_cost", "cost_price", "成本价", "平均成本"])),
        "market_price": number(first(record, ["market_price", "last_price", "现价", "最新价"])),
        "amount": number(first(record, ["amount", "成交金额", "发生金额", "金额"])),
        "gross_amount": number(first(record, ["gross_amount", "gross", "税前金额", "毛额"])),
        "net_amount": number(first(record, ["net_amount", "net", "净额", "税后金额"])),
        "from_amount": number(first(record, ["from_amount", "sell_amount", "换出金额", "卖出金额"])),
        "to_amount": number(first(record, ["to_amount", "buy_amount", "换入金额", "买入金额"])),
        "exchange_rate": number(first(record, ["exchange_rate", "fx_rate", "汇率", "成交汇率"])),
        "market_value": number(first(record, ["market_value", "市值", "持仓市值"])),
        "cash": number(first(record, ["cash", "cash_balance", "现金", "现金余额"])),
        "settled_cash": number(first(record, ["settled_cash", "已结算现金"])),
        "available_cash": number(first(record, ["available_cash", "可用现金", "可取现金"])),
        "total_assets": number(first(record, ["total_assets", "net_liquidation", "assets", "总资产", "净资产"])),
        "net_liquidation": number(first(record, ["net_liquidation", "net_liquidation_value", "净清算值"])),
        "buying_power": number(first(record, ["buying_power", "购买力"])),
        "margin_requirement": number(first(record, ["margin_requirement", "margin", "保证金", "初始保证金"])),
        "maintenance_margin": number(first(record, ["maintenance_margin", "维持保证金"])),
        "fees": number(first(record, ["fees", "commission", "fee", "费用", "佣金"])),
        "tax": number(first(record, ["tax", "withholding_tax", "预扣税", "税费", "税"])),
        "pnl": number(first(record, ["pnl", "unrealized_pnl", "realized_pnl", "盈亏", "浮动盈亏", "已实现盈亏"])),
        "realized_pnl": number(first(record, ["realized_pnl", "已实现盈亏"])),
        "unrealized_pnl": number(first(record, ["unrealized_pnl", "浮动盈亏", "未实现盈亏"])),
        "pnl_rate": number(first(record, ["pnl_rate", "收益率", "盈亏比例"])),
        "order_id": first(record, ["order_id", "委托编号", "订单号"]),
        "trade_id": first(record, ["trade_id", "execution_id", "成交编号", "成交号"]),
        "settlement_date": first(record, ["settlement_date", "settle_date", "交收日", "结算日"]),
        "ex_date": first(record, ["ex_date", "ex_dividend_date", "除权日", "除息日"]),
        "pay_date": first(record, ["pay_date", "payment_date", "派息日", "到账日"]),
        "flow_type": flow_type,
        "source_section": first(record, ["source_section", "sheet"]),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "")}
    event_time = first(record, ["time", "date", "trade_time", "order_time", "settled_at", "交易时间", "成交时间", "委托时间", "日期"])
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_label, row, broker, subtype, json.dumps(sanitized(record), ensure_ascii=False, sort_keys=True)),
        "collector": COLLECTOR,
        "source": "港美股券商用户授权只读数据",
        "owner_scope": "personal",
        "kind": kind_for_subtype(subtype),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": path_label,
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


def infer_subtype(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["subtype", "record_type", "type", "类型", "业务类型", "sheet"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path_label).lower()
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


def infer_broker(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["broker", "platform", "券商", "平台"])
    text = (explicit or "") + " " + json.dumps(record, ensure_ascii=False) + " " + str(path_label)
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
    observed_brokers = sorted(broker for broker, count in broker_counts.items() if count and broker != "unknown")
    observed_expected_brokers = [broker for broker in EXPECTED_HK_US_BROKERS if broker_counts.get(broker)]
    missing_expected_brokers = [broker for broker in EXPECTED_HK_US_BROKERS if not broker_counts.get(broker)]
    unknown_broker_count = sum(count for broker, count in broker_counts.items() if broker not in EXPECTED_HK_US_BROKERS)
    observed_subtypes = sorted(subtype for subtype, count in subtype_counts.items() if count and subtype not in {"collector_gap", "unknown"})
    observed_expected_subtypes = [subtype for subtype in EXPECTED_STRONG_TRADE_SUBTYPES if subtype_counts.get(subtype)]
    missing_expected_subtypes = [subtype for subtype in EXPECTED_STRONG_TRADE_SUBTYPES if not subtype_counts.get(subtype)]
    unknown_subtype_count = sum(count for subtype, count in subtype_counts.items() if subtype not in EXPECTED_STRONG_TRADE_SUBTYPES and subtype != "collector_gap")
    field_counts = Counter(
        field
        for event in events
        for field in RECOMMENDED_STRONG_FIELDS
        if (event.get("data") or {}).get(field) not in (None, "", [])
    )
    observed_recommended_fields = [field for field in RECOMMENDED_STRONG_FIELDS if field_counts.get(field)]
    missing_recommended_fields = [field for field in RECOMMENDED_STRONG_FIELDS if not field_counts.get(field)]
    return {
        "schema": "hk_us_brokerage.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "broker_counts": dict(sorted(broker_counts.items())),
        "broker_coverage": {
            "expected_p2_brokers": list(EXPECTED_HK_US_BROKERS),
            "observed_brokers": observed_brokers,
            "observed_expected_brokers": observed_expected_brokers,
            "missing_expected_brokers": missing_expected_brokers,
            "broker_counts": dict(sorted(broker_counts.items())),
            "unknown_broker_count": unknown_broker_count,
            "real_account_validation": False,
        },
        "trade_surface_coverage": {
            "expected_strong_trade_subtypes": list(EXPECTED_STRONG_TRADE_SUBTYPES),
            "observed_subtypes": observed_subtypes,
            "observed_expected_subtypes": observed_expected_subtypes,
            "missing_expected_subtypes": missing_expected_subtypes,
            "subtype_counts": dict(sorted(subtype_counts.items())),
            "unknown_subtype_count": unknown_subtype_count,
            "real_account_validation": False,
        },
        "field_coverage": {
            "recommended_strong_fields": list(RECOMMENDED_STRONG_FIELDS),
            "observed_recommended_fields": observed_recommended_fields,
            "missing_recommended_fields": missing_recommended_fields,
            "field_counts": dict(sorted(field_counts.items())),
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": "needs_hk_us_brokerage_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_hk_us_trade_boundary": False,
            "brokerage_boundary_scope": "none" if gap_only else "partial_authorized_input",
            "broker_coverage_status": coverage_status(events, missing_expected_brokers, "broker"),
            "trade_surface_coverage_status": coverage_status(events, missing_expected_subtypes, "trade_surface"),
            "field_coverage_status": coverage_status(events, missing_recommended_fields, "field"),
            "next_action": "Provide authorized Futu/Tiger/IBKR read-only export." if gap_only else "Use as strong trade evidence; continue per-broker real account validation.",
        },
    }


def coverage_status(events: List[Dict[str, Any]], missing_expected: List[str], noun: str) -> str:
    if not events or all((event.get("data") or {}).get("subtype") == "collector_gap" for event in events):
        return f"no_{noun}_observed"
    if not missing_expected:
        return f"all_expected_{noun}s_observed"
    return f"partial_expected_{noun}s_observed"


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
    normalized = {normalize_key(key): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(normalize_key(key))
        if value not in (None, ""):
            return str(value)
    return None


def normalize_key(value: Any) -> str:
    return re.sub(r"[\s_\-/%()（）]+", "", str(value).lower())


def number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    for token in ("HK$", "US$", "HKD", "USD", "CNH", "CNY", "港元", "美元", "$", "￥", "%"):
        text = text.replace(token, "")
    text = text.replace(",", "").strip()
    if text in {"--", "-"}:
        return None
    try:
        value_float = float(text)
    except ValueError:
        return None
    return -value_float if negative else value_float


def normalize_side(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.lower()
    if any(token in text for token in ("buy", "bot", "bought", "买入", "买")):
        return "buy"
    if any(token in text for token in ("sell", "sld", "sold", "卖出", "卖")):
        return "sell"
    return value


def normalize_status(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.lower()
    if any(token in text for token in ("filled", "executed", "成交", "全部成交", "已成交")):
        return "filled"
    if any(token in text for token in ("partial", "部分成交")):
        return "partial_filled"
    if any(token in text for token in ("cancel", "撤", "已取消")):
        return "cancelled"
    if any(token in text for token in ("submit", "open", "working", "submitted", "待成交", "已提交")):
        return "submitted"
    if any(token in text for token in ("reject", "拒绝", "失败")):
        return "rejected"
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


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            clean[str(key)] = sanitized(item)
        return clean
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:4000]
    return value


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
