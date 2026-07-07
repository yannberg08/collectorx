"""Parse China fund and wealth-management exports."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "china-wealth-assets"
CN_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="china_wealth_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for record in parse_path(path):
            events.append(record_to_event(record, path=path, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in {".csv", ".tsv", ".json", ".jsonl", ".ndjson"}:
                    yield child
        elif path.is_file():
            yield path


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        text = path.read_text(encoding="utf-8-sig")
        return [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        if isinstance(loaded, list):
            rows = loaded
        elif isinstance(loaded, dict):
            for key in ("assets", "holdings", "transactions", "records", "items", "data"):
                if isinstance(loaded.get(key), list):
                    rows = loaded[key]
                    break
            else:
                rows = [loaded]
        else:
            rows = [{"value": loaded}]
    return [row if isinstance(row, dict) else {"value": row} for row in rows]


def record_to_event(record: Dict[str, Any], *, path: Path, collected_at: Optional[str]) -> Dict[str, Any]:
    subtype = infer_subtype(record)
    data = {
        "subtype": subtype,
        "platform": first(record, ["platform", "平台", "来源"]),
        "account": first(record, ["account", "账户", "账号"]),
        "product_code": first(record, ["product_code", "fund_code", "code", "基金代码", "产品代码"]),
        "product_name": first(record, ["product_name", "fund_name", "name", "基金名称", "产品名称", "名称"]),
        "product_type": first(record, ["product_type", "type", "产品类型", "类型"]),
        "currency": first(record, ["currency", "币种"]),
        "quantity": number(first(record, ["quantity", "shares", "份额", "持有份额"])),
        "nav": number(first(record, ["nav", "net_value", "净值", "单位净值"])),
        "market_value": number(first(record, ["market_value", "amount", "市值", "资产", "持仓金额", "总资产"])),
        "cost": number(first(record, ["cost", "成本", "持仓成本"])),
        "pnl": number(first(record, ["pnl", "profit", "收益", "持有收益", "累计收益"])),
        "pnl_rate": first(record, ["pnl_rate", "收益率", "持有收益率"]),
        "side": normalize_side(first(record, ["side", "action", "交易类型", "操作", "业务类型"])),
        "raw": record,
    }
    data = {key: value for key, value in data.items() if value not in (None, "")}
    event_time = first(record, ["time", "date", "交易日期", "确认日期", "更新时间", "日期"])
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, json.dumps(record, ensure_ascii=False, sort_keys=True)),
        "collector": COLLECTOR,
        "source": "中国基金理财用户授权资产数据",
        "owner_scope": "personal",
        "kind": kind_for_subtype(subtype),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {"path": str(path), "subtype": subtype},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["money", "portfolio", "trade"]},
        "wiki_targets": wiki_targets_for_subtype(subtype),
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "中国基金理财授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "subtype": "collector_gap",
            "gap": reason,
            "message": "No user-authorized fund or wealth-management export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["money", "portfolio"]},
        "wiki_targets": ["investor.data_quality.collection_gaps"],
    }


def infer_subtype(record: Dict[str, Any]) -> str:
    text = " ".join(str(value).lower() for value in record.values() if value is not None)
    explicit = first(record, ["subtype", "record_type", "type", "类型", "业务类型", "交易类型"])
    if explicit:
        low = explicit.lower()
        if any(token in low for token in ["asset", "snapshot", "资产", "总资产"]):
            return "asset_snapshot"
        if any(token in low for token in ["buy", "sell", "subscribe", "redeem", "申购", "赎回", "定投", "转换", "分红"]):
            return "fund_transaction"
        if any(token in low for token in ["holding", "position", "持仓", "基金"]):
            return "fund_holding"
    if any(token in text for token in ["申购", "赎回", "定投", "转换", "分红", "buy", "sell", "redeem"]):
        return "fund_transaction"
    if any(key in record for key in ["总资产", "asset_total", "total_asset"]):
        return "asset_snapshot"
    return "fund_holding"


def kind_for_subtype(subtype: str) -> str:
    if subtype == "fund_transaction":
        return "trade"
    if subtype == "fund_holding":
        return "holding"
    return "other"


def wiki_targets_for_subtype(subtype: str) -> List[str]:
    if subtype == "fund_transaction":
        return ["investor.record_review.decision_log", "investor.execution.orders", "external.capital.cashflows"]
    if subtype == "fund_holding":
        return ["investor.risk_portfolio.current_positions", "investor.risk_portfolio.portfolio_constraints", "external.capital.assets"]
    if subtype == "asset_snapshot":
        return ["investor.risk_portfolio.current_assets", "external.capital.assets"]
    return ["investor.data_quality.collection_gaps"]


def build_manifest(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in events)
    gap_only = bool(events) and set(subtype_counts) == {"collector_gap"}
    return {
        "schema": "china_wealth.assets.manifest.v1",
        "collector": COLLECTOR,
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "collection_readiness": {
            "status": "needs_china_wealth_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events),
            "can_claim_complete_asset_boundary": not gap_only,
            "next_action": "提供支付宝/基金/理财授权导出后重跑。" if gap_only else "可进入投资分身蒸馏；后续按平台做只读真机验证。",
        },
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        for target in event.get("wiki_targets", []):
            by_target[target].append(event)
    return {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": len(events),
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
        },
        "coverage_summary": {
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
            "asset_boundary_source": True,
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
    text = str(value).replace(",", "").replace("￥", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def normalize_side(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.lower()
    if any(token in text for token in ["buy", "申购", "买入", "定投"]):
        return "buy"
    if any(token in text for token in ["sell", "redeem", "赎回", "卖出"]):
        return "sell"
    if "分红" in text:
        return "dividend"
    if "转换" in text:
        return "convert"
    return value


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
