"""Parse user-authorized HK/US brokerage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency for runtime installs
    openpyxl = None

try:
    from collectorx.investor_wiki import augment_evidence_with_dimensions
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution outside repo cwd
    for parent in Path(__file__).resolve().parents:
        if (parent / "collectorx").exists():
            sys.path.insert(0, str(parent))
            break
    from collectorx.investor_wiki import augment_evidence_with_dimensions


COLLECTOR = "hk-us-brokerage"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_RECORD_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xlsx", ".xlsm"}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SUPPORTED_ZIP_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
EXPECTED_HK_US_BROKERS = ("futu", "tiger", "ibkr")
EXPECTED_STRONG_TRADE_SUBTYPES = ("asset_snapshot", "position", "execution", "order", "cashflow", "dividend", "fx")
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
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
INVESTOR_WIKI_SUBDIMENSION_RULES = {
    "inv-risk-view": {
        "support_level": "strong",
        "route_targets": [
            "investor.risk_portfolio.current_assets",
            "investor.risk_portfolio.current_positions",
            "investor.risk_portfolio.portfolio_constraints",
            "external.capital.assets",
            "external.capital.cashflows",
        ],
        "signals": ["资产、持仓、现金、保证金、费用和税费字段可支撑真实风险暴露画像。"],
        "gaps": ["完整账户边界仍需真实券商账号验证，资产暴露不等于风险信念。"],
    },
    "inv-value-preference": {
        "support_level": "medium",
        "route_targets": ["investor.risk_portfolio.current_positions", "external.capital.assets"],
        "signals": ["港美股持仓、币种和市场分布可作为价值偏好侧影。"],
        "gaps": ["偏好原因需要研究文档、笔记或对话解释。"],
    },
    "inv-style-profile": {
        "support_level": "strong",
        "route_targets": [
            "investor.risk_portfolio.current_assets",
            "investor.risk_portfolio.current_positions",
            "investor.record_review.decision_log",
            "investor.execution.orders",
        ],
        "signals": ["持仓、成交、委托和资金流水可分析频率、集中度、换手和跨市场风格。"],
        "gaps": ["交易行为不能直接说明策略意图。"],
    },
    "inv-buy-framework": {
        "support_level": "medium",
        "route_targets": ["investor.record_review.decision_log", "investor.execution.orders"],
        "data_matches": {"side": ["buy", "BUY", "买入"]},
        "signals": ["买入成交与委托可形成买入框架回测入口。"],
        "gaps": ["缺少买入触发条件、估值假设和备选方案。"],
    },
    "inv-sell-framework": {
        "support_level": "medium",
        "route_targets": ["investor.record_review.decision_log", "investor.execution.orders"],
        "data_matches": {"side": ["sell", "SELL", "卖出"]},
        "signals": ["卖出成交与委托可形成卖出纪律回测入口。"],
        "gaps": ["缺少止盈、止损、换仓或风险释放理由。"],
    },
    "inv-cognitive-bias": {
        "support_level": "weak",
        "route_targets": ["investor.record_review.decision_log"],
        "signals": ["交易序列可后验观察追涨杀跌、频繁交易等偏差候选。"],
        "gaps": ["不能仅凭交易记录定性偏差，需要行情背景和用户解释。"],
    },
    "inv-decision-adaptation-style": {
        "support_level": "medium",
        "route_targets": ["investor.record_review.decision_log", "investor.execution.orders", "external.capital.cashflows"],
        "signals": ["跨币种、跨市场、调仓和资金变化可观察决策适应方式。"],
        "gaps": ["缺少用户如何调整假设的文本过程。"],
    },
    "inv-decision-log": {
        "support_level": "strong",
        "route_targets": ["investor.record_review.decision_log", "investor.execution.orders", "external.capital.cashflows"],
        "signals": ["成交、委托、分红、资金流水和换汇可形成强决策时间线。"],
        "gaps": ["时间线仍需交易理由和复盘补充。"],
    },
    "inv-portfolio-preference": {
        "support_level": "strong",
        "route_targets": [
            "investor.risk_portfolio.current_assets",
            "investor.risk_portfolio.current_positions",
            "investor.risk_portfolio.portfolio_constraints",
            "external.capital.assets",
        ],
        "signals": ["账户、市场、币种、持仓和资产价值可支撑组合偏好画像。"],
        "gaps": ["完整组合边界需纳入 A 股、基金、现金和银行理财等其他账户。"],
    },
    "inv-execution-discipline": {
        "support_level": "strong",
        "route_targets": [
            "investor.execution.orders",
            "investor.behavior.execution_discipline",
            "investor.record_review.decision_log",
            "external.capital.cashflows",
        ],
        "signals": ["委托、成交、撤单状态、费用和结算字段可分析执行纪律。"],
        "gaps": ["缺少计划单和目标价，不能单独评估是否遵守计划。"],
    },
    "inv-time-preference": {
        "support_level": "medium",
        "route_targets": ["investor.record_review.decision_log", "investor.execution.orders", "external.capital.cashflows"],
        "signals": ["交易日期、结算日期、分红和持仓变化能提供期限偏好线索。"],
        "gaps": ["需结合持仓周期和交易意图区分主动偏好与被动持有。"],
    },
}
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


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_brokers: Optional[Iterable[str]] = None,
    deny_brokers: Optional[Iterable[str]] = None,
    allow_accounts: Optional[Iterable[str]] = None,
    deny_accounts: Optional[Iterable[str]] = None,
    allow_subtypes: Optional[Iterable[str]] = None,
    deny_subtypes: Optional[Iterable[str]] = None,
    allow_symbols: Optional[Iterable[str]] = None,
    deny_symbols: Optional[Iterable[str]] = None,
    allow_markets: Optional[Iterable[str]] = None,
    deny_markets: Optional[Iterable[str]] = None,
    allow_currencies: Optional[Iterable[str]] = None,
    deny_currencies: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(
        inputs,
        collected_at=collected_at,
        limit=limit,
        allow_brokers=allow_brokers,
        deny_brokers=deny_brokers,
        allow_accounts=allow_accounts,
        deny_accounts=deny_accounts,
        allow_subtypes=allow_subtypes,
        deny_subtypes=deny_subtypes,
        allow_symbols=allow_symbols,
        deny_symbols=deny_symbols,
        allow_markets=allow_markets,
        deny_markets=deny_markets,
        allow_currencies=allow_currencies,
        deny_currencies=deny_currencies,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_brokers: Optional[Iterable[str]] = None,
    deny_brokers: Optional[Iterable[str]] = None,
    allow_accounts: Optional[Iterable[str]] = None,
    deny_accounts: Optional[Iterable[str]] = None,
    allow_subtypes: Optional[Iterable[str]] = None,
    deny_subtypes: Optional[Iterable[str]] = None,
    allow_symbols: Optional[Iterable[str]] = None,
    deny_symbols: Optional[Iterable[str]] = None,
    allow_markets: Optional[Iterable[str]] = None,
    deny_markets: Optional[Iterable[str]] = None,
    allow_currencies: Optional[Iterable[str]] = None,
    deny_currencies: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    events: List[Dict[str, Any]] = []
    extension_counts: Counter[str] = Counter()
    skipped_extension_counts: Counter[str] = Counter()
    skipped_reason_counts: Counter[str] = Counter()
    skipped_archive_member_reason_counts: Counter[str] = Counter()
    scope_policy_filter_reason_counts: Counter[str] = Counter()
    candidate_record_count = 0
    scope_policy_filtered_record_count = 0
    policy = build_brokerage_scope_policy(
        allow_brokers=allow_brokers,
        deny_brokers=deny_brokers,
        allow_accounts=allow_accounts,
        deny_accounts=deny_accounts,
        allow_subtypes=allow_subtypes,
        deny_subtypes=deny_subtypes,
        allow_symbols=allow_symbols,
        deny_symbols=deny_symbols,
        allow_markets=allow_markets,
        deny_markets=deny_markets,
        allow_currencies=allow_currencies,
        deny_currencies=deny_currencies,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    audit: Dict[str, Any] = {
        "source_type": "authorized_hk_us_brokerage_export",
        "input_count": len(input_list),
        "requested_inputs": [str(Path(raw).expanduser()) for raw in input_list],
        "resolved_input_file_count": 0,
        "input_missing_count": 0,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "limit": limit,
        "limit_reached": False,
        "extension_counts": {},
        "skipped_extension_counts": {},
        "skipped_reason_counts": {},
        "skipped_file_count": 0,
        "archive_count": 0,
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
        "candidate_record_count": 0,
        "scope_policy_filtered_record_count": 0,
        "scope_policy_filter_reason_counts": {},
        "brokerage_scope_policy": policy,
        "brokerage_scope_policy_filtered_all": False,
        "parsed_record_count": 0,
        "emitted_event_count": 0,
        "path_results": [],
    }

    for raw in input_list:
        if limit is not None and len(events) >= limit:
            audit["limit_reached"] = True
            break
        input_path = Path(raw).expanduser()
        if not input_path.exists():
            audit["input_missing_count"] += 1
            skipped_reason_counts["input_missing"] += 1
            audit["path_results"].append(path_result(input_path, status="missing", reason="input_missing"))
            continue
        if input_path.is_dir():
            files = sorted(child for child in input_path.rglob("*") if child.is_file())
        elif input_path.is_file():
            files = [input_path]
        else:
            skipped_reason_counts["unsupported_input_kind"] += 1
            audit["path_results"].append(path_result(input_path, status="skipped", reason="unsupported_input_kind"))
            continue

        for path in files:
            if limit is not None and len(events) >= limit:
                audit["limit_reached"] = True
                break
            ext = extension_label(path)
            extension_counts[ext] += 1
            if not is_supported_path(path):
                audit["skipped_file_count"] += 1
                skipped_extension_counts[ext] += 1
                skipped_reason_counts["unsupported_extension"] += 1
                audit["path_results"].append(path_result(path, status="skipped", reason="unsupported_extension"))
                continue
            audit["resolved_input_file_count"] += 1
            result = path_result(path, status="pending")
            try:
                if path.suffix.lower() == ".zip":
                    zip_limit = None if policy["enabled"] else remaining_limit(limit, events)
                    parsed, archive_audit = parse_zip_with_audit(path, limit=zip_limit)
                    merge_archive_audit(audit, archive_audit, skipped_archive_member_reason_counts)
                    result.update(
                        {
                            "status": "parsed" if parsed else "no_records_parsed",
                            "parser": "zip",
                            "parsed_record_count": len(parsed),
                            "archive_member_count": archive_audit["archive_member_count"],
                            "skipped_archive_member_count": archive_audit["skipped_archive_member_count"],
                        }
                    )
                else:
                    parsed = parse_path(path)
                    result.update(
                        {
                            "status": "parsed" if parsed else "no_records_parsed",
                            "parser": parser_name_for_path(path),
                            "parsed_record_count": len(parsed),
                        }
                    )
            except Exception:
                parsed = []
                audit["skipped_file_count"] += 1
                skipped_extension_counts[ext] += 1
                skipped_reason_counts["parse_error"] += 1
                result.update({"status": "parse_error", "reason": "parse_error", "parsed_record_count": 0})
            audit["path_results"].append(result)
            row = 0
            path_candidate_count = 0
            path_filtered_count = 0
            path_emitted_count = 0
            for record in parsed:
                if not isinstance(record, dict):
                    continue
                row += 1
                candidate_record_count += 1
                path_candidate_count += 1
                event = record_to_event(record, path=path, row=row, collected_at=collected_at)
                filter_reason = brokerage_scope_policy_filter_reason(event, policy)
                if filter_reason:
                    scope_policy_filtered_record_count += 1
                    path_filtered_count += 1
                    scope_policy_filter_reason_counts[filter_reason] += 1
                    continue
                events.append(event)
                path_emitted_count += 1
                if limit is not None and len(events) >= limit:
                    audit["limit_reached"] = True
                    break
            if path_candidate_count:
                result["candidate_record_count"] = path_candidate_count
                result["scope_policy_filtered_record_count"] = path_filtered_count
                result["emitted_record_count"] = path_emitted_count
                if policy["enabled"] and path_filtered_count == path_candidate_count and path_emitted_count == 0:
                    result["status"] = "filtered_by_scope_policy"
                    result["reason"] = "scope_policy_excluded_all_records"
                elif path_filtered_count:
                    result["scope_policy_filter_status"] = "partially_filtered"
        if limit is not None and len(events) >= limit:
            break

    scope_policy_filtered_all = (
        policy["enabled"]
        and candidate_record_count > 0
        and scope_policy_filtered_record_count == candidate_record_count
        and not events
    )
    if not events and not scope_policy_filtered_all:
        reason = (
            "hk_us_brokerage_authorized_input_missing"
            if not input_list or (audit["input_missing_count"] and audit["resolved_input_file_count"] == 0)
            else "hk_us_brokerage_records_empty"
        )
        events = [gap_event(collected_at=collected_at, reason=reason)]
    audit["candidate_record_count"] = candidate_record_count
    audit["scope_policy_filtered_record_count"] = scope_policy_filtered_record_count
    audit["scope_policy_filter_reason_counts"] = dict(sorted(scope_policy_filter_reason_counts.items()))
    audit["brokerage_scope_policy_filtered_all"] = scope_policy_filtered_all
    audit["parsed_record_count"] = candidate_record_count
    audit["emitted_event_count"] = len(events)
    audit["extension_counts"] = dict(sorted(extension_counts.items()))
    audit["skipped_extension_counts"] = dict(sorted(skipped_extension_counts.items()))
    audit["skipped_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_archive_member_reason_counts.items()))
    audit["archive_member_event_count"] = sum(1 for event in usable_brokerage_events(events) if (event.get("raw_ref") or {}).get("archive_member"))
    return events, audit


def build_brokerage_scope_policy(
    *,
    allow_brokers: Optional[Iterable[str]] = None,
    deny_brokers: Optional[Iterable[str]] = None,
    allow_accounts: Optional[Iterable[str]] = None,
    deny_accounts: Optional[Iterable[str]] = None,
    allow_subtypes: Optional[Iterable[str]] = None,
    deny_subtypes: Optional[Iterable[str]] = None,
    allow_symbols: Optional[Iterable[str]] = None,
    deny_symbols: Optional[Iterable[str]] = None,
    allow_markets: Optional[Iterable[str]] = None,
    deny_markets: Optional[Iterable[str]] = None,
    allow_currencies: Optional[Iterable[str]] = None,
    deny_currencies: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "allow_brokers": normalize_scope_terms(allow_brokers, normalizer=normalize_broker_scope_term),
        "deny_brokers": normalize_scope_terms(deny_brokers, normalizer=normalize_broker_scope_term),
        "allow_accounts": normalize_scope_terms(allow_accounts),
        "deny_accounts": normalize_scope_terms(deny_accounts),
        "allow_subtypes": normalize_scope_terms(allow_subtypes, normalizer=normalize_subtype_scope_term),
        "deny_subtypes": normalize_scope_terms(deny_subtypes, normalizer=normalize_subtype_scope_term),
        "allow_symbols": normalize_scope_terms(allow_symbols, normalizer=normalize_symbol_scope_term),
        "deny_symbols": normalize_scope_terms(deny_symbols, normalizer=normalize_symbol_scope_term),
        "allow_markets": normalize_scope_terms(allow_markets, normalizer=normalize_market_scope_term),
        "deny_markets": normalize_scope_terms(deny_markets, normalizer=normalize_market_scope_term),
        "allow_currencies": normalize_scope_terms(allow_currencies, normalizer=normalize_currency_scope_term),
        "deny_currencies": normalize_scope_terms(deny_currencies, normalizer=normalize_currency_scope_term),
        "allow_keywords": normalize_scope_terms(allow_keywords, keep_case=True),
        "deny_keywords": normalize_scope_terms(deny_keywords, keep_case=True),
    }
    policy["enabled"] = any(bool(values) for values in policy.values())
    return policy


def normalize_scope_terms(
    values: Optional[Iterable[str]],
    *,
    normalizer: Optional[Any] = None,
    keep_case: bool = False,
) -> List[str]:
    cleaned: List[str] = []
    for term in split_policy_terms(values):
        normalized = normalizer(term) if normalizer else term.strip()
        if not normalized:
            continue
        cleaned.append(normalized if keep_case else normalized.lower())
    return sorted(dict.fromkeys(cleaned))


def split_policy_terms(values: Optional[Iterable[str]]) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    terms: List[str] = []
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, (list, tuple, set)):
            terms.extend(split_policy_terms(value))
            continue
        terms.extend(item.strip() for item in re.split(r"[,，、;；|\n]+", str(value)) if item.strip())
    return terms


def normalize_broker_scope_term(term: str) -> str:
    return infer_broker({"broker": term}, term)


def normalize_subtype_scope_term(term: str) -> str:
    return infer_subtype({"record_type": term}, term)


def normalize_symbol_scope_term(term: str) -> str:
    return re.sub(r"\s+", "", term.strip()).lower()


def normalize_market_scope_term(term: str) -> str:
    return (normalize_market(term) or term.strip()).lower()


def normalize_currency_scope_term(term: str) -> str:
    return term.strip().lower()


def brokerage_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy.get("enabled"):
        return None
    data = event.get("data") or {}
    broker = normalize_broker_scope_term(str(data.get("broker") or ""))
    account = str(data.get("account_id") or "").strip().lower()
    subtype = normalize_subtype_scope_term(str(data.get("subtype") or ""))
    symbol = normalize_symbol_scope_term(str(data.get("symbol") or ""))
    market = normalize_market_scope_term(str(data.get("market") or data.get("exchange") or ""))
    currencies = brokerage_event_currencies(data)
    if broker and broker in policy.get("deny_brokers", []):
        return "broker_denied"
    if account and account in policy.get("deny_accounts", []):
        return "account_denied"
    if subtype and subtype in policy.get("deny_subtypes", []):
        return "subtype_denied"
    if symbol and symbol in policy.get("deny_symbols", []):
        return "symbol_denied"
    if market and market in policy.get("deny_markets", []):
        return "market_denied"
    if currencies and set(currencies).intersection(policy.get("deny_currencies", [])):
        return "currency_denied"
    if policy_hit(policy.get("deny_keywords", []), flatten_brokerage_policy_surface(data)):
        return "keyword_denied"
    if policy.get("allow_brokers") and broker not in policy["allow_brokers"]:
        return "broker_not_allowed"
    if policy.get("allow_accounts") and account not in policy["allow_accounts"]:
        return "account_not_allowed"
    if policy.get("allow_subtypes") and subtype not in policy["allow_subtypes"]:
        return "subtype_not_allowed"
    if policy.get("allow_symbols") and symbol not in policy["allow_symbols"]:
        return "symbol_not_allowed"
    if policy.get("allow_markets") and market not in policy["allow_markets"]:
        return "market_not_allowed"
    if policy.get("allow_currencies") and not set(currencies).intersection(policy["allow_currencies"]):
        return "currency_not_allowed"
    if policy.get("allow_keywords") and not policy_hit(policy["allow_keywords"], flatten_brokerage_policy_surface(data)):
        return "keyword_not_allowed"
    return None


def brokerage_event_currencies(data: Dict[str, Any]) -> List[str]:
    return [normalize_currency_scope_term(value) for value in currency_values(data)]


def policy_hit(needles: Sequence[str], values: Iterable[Any]) -> bool:
    if not needles:
        return False
    haystack = "\n".join(str(value) for value in values if value not in (None, "", [], {})).lower()
    return any(str(needle).lower() in haystack for needle in needles if str(needle).strip())


def flatten_brokerage_policy_surface(data: Dict[str, Any]) -> List[Any]:
    values: List[Any] = []
    for key in (
        "broker",
        "account_id",
        "subtype",
        "symbol",
        "isin",
        "cusip",
        "name",
        "market",
        "exchange",
        "currency",
        "base_currency",
        "from_currency",
        "to_currency",
        "side",
        "status",
        "order_type",
        "flow_type",
        "order_id",
        "trade_id",
        "source_section",
    ):
        values.append(data.get(key))
    return values


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


def extension_label(path: Path) -> str:
    return path.suffix.lower() or "<none>"


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
    records, _audit = parse_zip_with_audit(path)
    return records


def parse_zip_with_audit(path: Path, *, limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    skipped_reason_counts: Counter[str] = Counter()
    audit: Dict[str, Any] = {
        "archive": str(path),
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "limit_reached": False,
        "member_results": [],
    }
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.infolist(), key=lambda item: normalize_zip_member_name(item.filename))
        for member in members:
            audit["archive_member_count"] += 1
            member_name = normalize_zip_member_name(member.filename)
            skip_reason = zip_member_skip_reason(member)
            if skip_reason:
                audit["skipped_archive_member_count"] += 1
                skipped_reason_counts[skip_reason] += 1
                audit["member_results"].append({"member": member_name, "status": "skipped", "reason": skip_reason})
                continue
            suffix = Path(member_name).suffix.lower()
            path_label = f"{path}::{member_name}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                else:
                    parsed = parse_workbook(io.BytesIO(archive.read(member)), path_label=path_label)
            except Exception:
                parsed = []
                audit["skipped_archive_member_count"] += 1
                skipped_reason_counts["parse_error"] += 1
                audit["member_results"].append({"member": member_name, "status": "parse_error", "reason": "parse_error"})
                continue
            remaining = None if limit is None else max(limit - len(records), 0)
            emittable = parsed if remaining is None else parsed[:remaining]
            audit["member_results"].append(
                {
                    "member": member_name,
                    "status": "parsed" if parsed else "no_records_parsed",
                    "parsed_record_count": len(parsed),
                    "emitted_record_count": len(emittable),
                }
            )
            for record in emittable:
                if isinstance(record, dict):
                    record[SOURCE_ARCHIVE_KEY] = str(path)
                    record[SOURCE_MEMBER_KEY] = member_name
                    audit["archive_member_event_count"] += 1
            records.extend(emittable)
            if limit is not None and len(records) >= limit:
                audit["limit_reached"] = True
                audit["unvisited_archive_member_count_due_limit"] = max(0, len(members) - audit["archive_member_count"])
                audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
                return records, audit
    audit["unvisited_archive_member_count_due_limit"] = 0
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    return records, audit


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    return zip_member_skip_reason(member) is not None


def zip_member_skip_reason(member: zipfile.ZipInfo) -> Optional[str]:
    member_name = normalize_zip_member_name(member.filename)
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(member.filename)
    if member.is_dir():
        return "directory"
    if member_path.is_absolute() or windows_path.drive or ".." in member_path.parts:
        return "unsafe_path"
    if Path(member_name).suffix.lower() not in SUPPORTED_ZIP_EXTENSIONS:
        return "unsupported_extension"
    return None


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


def remaining_limit(limit: Optional[int], events: List[Dict[str, Any]]) -> Optional[int]:
    if limit is None:
        return None
    return max(limit - len(events), 0)


def parser_name_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix in {".xlsx", ".xlsm"}:
        return "workbook"
    if suffix in {".csv", ".tsv"}:
        return "table"
    return "json"


def path_result(path: Path, *, status: str, reason: Optional[str] = None) -> Dict[str, Any]:
    result = {
        "path": str(path),
        "extension": extension_label(path),
        "status": status,
    }
    if reason:
        result["reason"] = reason
    return result


def merge_archive_audit(audit: Dict[str, Any], archive_audit: Dict[str, Any], skipped_reason_counts: Counter[str]) -> None:
    audit["archive_count"] += 1
    audit["archive_member_count"] += int(archive_audit.get("archive_member_count") or 0)
    audit["archive_member_event_count"] += int(archive_audit.get("archive_member_event_count") or 0)
    audit["skipped_archive_member_count"] += int(archive_audit.get("skipped_archive_member_count") or 0)
    if archive_audit.get("limit_reached"):
        audit["limit_reached"] = True
    for reason, count in (archive_audit.get("skipped_archive_member_reason_counts") or {}).items():
        skipped_reason_counts[str(reason)] += int(count)


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
    if data.get("order_quantity") not in (None, 0) and data.get("filled_quantity") is not None:
        data["fill_ratio"] = round(float(data["filled_quantity"]) / float(data["order_quantity"]), 6)
    data = {key: value for key, value in data.items() if value not in (None, "")}
    event_time = first(record, ["time", "date", "trade_time", "order_time", "settled_at", "交易时间", "成交时间", "委托时间", "日期"])
    raw_ref = {
        "path": path_label,
        "row": row,
        "broker": broker,
        "subtype": subtype,
        "source_section": data.get("source_section"),
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
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
        "raw_ref": raw_ref,
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


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in events)
    broker_counts = Counter((event.get("data") or {}).get("broker", "unknown") for event in events)
    collection_audit = collection_audit or {}
    gap_only = bool(events) and set(subtype_counts) == {"collector_gap"}
    scope_policy_filtered_all = bool(collection_audit.get("brokerage_scope_policy_filtered_all"))
    no_events = not events
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
        "strong_trade_surface_summary": strong_trade_surface_summary(events),
        "account_boundary_summary": account_boundary_summary(events),
        "currency_market_summary": currency_market_summary(events),
        "fee_tax_margin_summary": fee_tax_margin_summary(events),
        "asset_value_summary": asset_value_summary(events),
        "cashflow_activity_summary": cashflow_activity_summary(events),
        "income_return_summary": income_return_summary(events),
        "order_execution_summary": order_execution_summary(events),
        "brokerage_boundary_proof": brokerage_boundary_proof(events, collection_audit=collection_audit),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "evidence_policy": {
            "vertical_collector": True,
            "strong_trade_source": True,
            "collector_writes_investor_wiki_directly": False,
            "read_only_collection": True,
            "order_side_effects_allowed": False,
            "complete_trade_boundary_claimed": False,
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": collection_readiness_status(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "can_enter_finclaw": bool(events) and not gap_only and not scope_policy_filtered_all,
            "can_claim_complete_hk_us_trade_boundary": False,
            "brokerage_boundary_scope": brokerage_boundary_scope_for_readiness(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "broker_coverage_status": coverage_status(events, missing_expected_brokers, "broker"),
            "trade_surface_coverage_status": coverage_status(events, missing_expected_subtypes, "trade_surface"),
            "field_coverage_status": coverage_status(events, missing_recommended_fields, "field"),
            "next_action": collection_next_action(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
        },
    }


def collection_readiness_status(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_filtered_all"
    if gap_only or no_events:
        return "needs_hk_us_brokerage_authorized_input"
    return "events_collected"


def brokerage_boundary_scope_for_readiness(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_excluded_all"
    if gap_only or no_events:
        return "none"
    return "partial_authorized_input"


def collection_next_action(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "Broaden the user authorization scope or provide brokerage records that match the current policy."
    if gap_only or no_events:
        return "Provide authorized Futu/Tiger/IBKR read-only export."
    return "Use as strong trade evidence; continue per-broker real account validation."


def coverage_status(events: List[Dict[str, Any]], missing_expected: List[str], noun: str) -> str:
    if not events or all((event.get("data") or {}).get("subtype") == "collector_gap" for event in events):
        return f"no_{noun}_observed"
    if not missing_expected:
        return f"all_expected_{noun}s_observed"
    return f"partial_expected_{noun}s_observed"


def usable_brokerage_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [event for event in events if (event.get("data") or {}).get("subtype") != "collector_gap"]


def strong_trade_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, int]:
    usable_events = usable_brokerage_events(events)
    return {
        "strong_trade_event_count": len(usable_events),
        "asset_snapshot_count": subtype_event_count(usable_events, "asset_snapshot"),
        "position_count": subtype_event_count(usable_events, "position"),
        "execution_count": subtype_event_count(usable_events, "execution"),
        "order_count": subtype_event_count(usable_events, "order"),
        "cashflow_count": subtype_event_count(usable_events, "cashflow"),
        "dividend_count": subtype_event_count(usable_events, "dividend"),
        "fx_count": subtype_event_count(usable_events, "fx"),
        "events_with_account_id": sum(1 for event in usable_events if (event.get("data") or {}).get("account_id")),
        "events_with_currency": sum(1 for event in usable_events if (event.get("data") or {}).get("currency")),
        "events_with_symbol": sum(1 for event in usable_events if (event.get("data") or {}).get("symbol")),
        "events_with_amount": sum(1 for event in usable_events if (event.get("data") or {}).get("amount")),
        "events_with_fees": sum(1 for event in usable_events if (event.get("data") or {}).get("fees") is not None),
        "events_with_tax": sum(1 for event in usable_events if (event.get("data") or {}).get("tax") is not None),
        "events_with_margin": sum(
            1
            for event in usable_events
            if (event.get("data") or {}).get("margin_requirement") is not None
            or (event.get("data") or {}).get("maintenance_margin") is not None
        ),
        "events_with_pnl": sum(
            1
            for event in usable_events
            if (event.get("data") or {}).get("pnl") is not None
            or (event.get("data") or {}).get("realized_pnl") is not None
            or (event.get("data") or {}).get("unrealized_pnl") is not None
        ),
    }


def subtype_event_count(events: List[Dict[str, Any]], subtype: str) -> int:
    return sum(1 for event in events if (event.get("data") or {}).get("subtype") == subtype)


def account_boundary_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    accounts_by_broker: Dict[str, set[str]] = defaultdict(set)
    subtypes_by_account: Dict[str, set[str]] = defaultdict(set)
    currencies_by_account: Dict[str, set[str]] = defaultdict(set)
    markets_by_account: Dict[str, set[str]] = defaultdict(set)
    event_counts_by_account: Counter[str] = Counter()
    accounts_with_asset_snapshot = set()
    accounts_with_position = set()
    accounts_with_execution = set()
    accounts_with_order = set()
    accounts_with_cashflow = set()
    accounts_with_dividend = set()
    accounts_with_fx = set()
    known_account_keys = set()
    for event in usable_events:
        data = event.get("data") or {}
        broker = str(data.get("broker") or "unknown_broker")
        account_id = str(data.get("account_id") or "unknown_account")
        account_key = f"{broker}:{account_id}"
        if account_id != "unknown_account":
            accounts_by_broker[broker].add(account_id)
            known_account_keys.add(account_key)
        subtype = str(data.get("subtype") or "unknown")
        subtypes_by_account[account_key].add(subtype)
        event_counts_by_account[account_key] += 1
        for currency in currency_values(data):
            currencies_by_account[account_key].add(currency)
        market = data.get("market")
        if market:
            markets_by_account[account_key].add(str(market))
        target = {
            "asset_snapshot": accounts_with_asset_snapshot,
            "position": accounts_with_position,
            "execution": accounts_with_execution,
            "order": accounts_with_order,
            "cashflow": accounts_with_cashflow,
            "dividend": accounts_with_dividend,
            "fx": accounts_with_fx,
        }.get(subtype)
        if target is not None:
            target.add(account_key)
    missing_by_account = {
        account_key: [subtype for subtype in EXPECTED_STRONG_TRADE_SUBTYPES if subtype not in subtypes_by_account.get(account_key, set())]
        for account_key in sorted(known_account_keys)
    }
    full_surface_accounts = [
        account_key
        for account_key, missing in missing_by_account.items()
        if not missing
    ]
    return {
        "account_id_count": sum(len(accounts) for accounts in accounts_by_broker.values()),
        "accounts_by_broker": sorted_dict_of_lists(accounts_by_broker),
        "event_counts_by_account": dict(sorted(event_counts_by_account.items())),
        "subtypes_by_account": sorted_dict_of_lists(subtypes_by_account),
        "currencies_by_account": sorted_dict_of_lists(currencies_by_account),
        "markets_by_account": sorted_dict_of_lists(markets_by_account),
        "accounts_with_asset_snapshot": sorted(accounts_with_asset_snapshot),
        "accounts_with_position": sorted(accounts_with_position),
        "accounts_with_execution": sorted(accounts_with_execution),
        "accounts_with_order": sorted(accounts_with_order),
        "accounts_with_cashflow": sorted(accounts_with_cashflow),
        "accounts_with_dividend": sorted(accounts_with_dividend),
        "accounts_with_fx": sorted(accounts_with_fx),
        "missing_expected_subtypes_by_account": missing_by_account,
        "full_surface_account_candidates": full_surface_accounts,
        "complete_account_boundary_claimed": False,
    }


def currency_market_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    currency_counts: Counter[str] = Counter()
    market_counts: Counter[str] = Counter()
    broker_currency_counts: Counter[str] = Counter()
    broker_market_counts: Counter[str] = Counter()
    fx_pair_counts: Counter[str] = Counter()
    for event in usable_events:
        data = event.get("data") or {}
        broker = str(data.get("broker") or "unknown_broker")
        currencies = currency_values(data)
        for currency in currencies:
            currency_counts[currency] += 1
            broker_currency_counts[f"{broker}:{currency}"] += 1
        market = data.get("market")
        if market:
            market_value = str(market)
            market_counts[market_value] += 1
            broker_market_counts[f"{broker}:{market_value}"] += 1
        if data.get("from_currency") and data.get("to_currency"):
            fx_pair_counts[f"{data['from_currency']}->{data['to_currency']}"] += 1
    return {
        "currency_counts": dict(sorted(currency_counts.items())),
        "market_counts": dict(sorted(market_counts.items())),
        "broker_currency_counts": dict(sorted(broker_currency_counts.items())),
        "broker_market_counts": dict(sorted(broker_market_counts.items())),
        "fx_pair_counts": dict(sorted(fx_pair_counts.items())),
        "currency_count": len(currency_counts),
        "market_count": len(market_counts),
        "multi_currency_observed": len(currency_counts) > 1,
        "hk_market_event_count": market_counts.get("HK", 0),
        "us_market_event_count": market_counts.get("US", 0),
    }


def fee_tax_margin_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    fee_events = [event for event in usable_events if (event.get("data") or {}).get("fees") is not None]
    tax_events = [event for event in usable_events if (event.get("data") or {}).get("tax") is not None]
    margin_events = [
        event
        for event in usable_events
        if (event.get("data") or {}).get("margin_requirement") is not None
        or (event.get("data") or {}).get("maintenance_margin") is not None
    ]
    total_fees_by_currency: Dict[str, float] = defaultdict(float)
    total_tax_by_currency: Dict[str, float] = defaultdict(float)
    margin_requirement_by_currency: Dict[str, float] = defaultdict(float)
    maintenance_margin_by_currency: Dict[str, float] = defaultdict(float)
    for event in fee_events:
        data = event.get("data") or {}
        currency = primary_currency(data)
        total_fees_by_currency[currency] += float(data.get("fees") or 0)
    for event in tax_events:
        data = event.get("data") or {}
        currency = primary_currency(data)
        total_tax_by_currency[currency] += float(data.get("tax") or 0)
    for event in margin_events:
        data = event.get("data") or {}
        currency = primary_currency(data)
        margin_requirement_by_currency[currency] += float(data.get("margin_requirement") or 0)
        maintenance_margin_by_currency[currency] += float(data.get("maintenance_margin") or 0)
    return {
        "events_with_fees": len(fee_events),
        "events_with_tax": len(tax_events),
        "events_with_margin": len(margin_events),
        "total_fees_by_currency": dict(sorted(total_fees_by_currency.items())),
        "total_tax_by_currency": dict(sorted(total_tax_by_currency.items())),
        "margin_requirement_by_currency": dict(sorted(margin_requirement_by_currency.items())),
        "maintenance_margin_by_currency": dict(sorted(maintenance_margin_by_currency.items())),
    }


def asset_value_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    asset_events = [event for event in usable_events if (event.get("data") or {}).get("subtype") == "asset_snapshot"]
    totals_by_currency: Dict[str, float] = defaultdict(float)
    cash_by_currency: Dict[str, float] = defaultdict(float)
    buying_power_by_currency: Dict[str, float] = defaultdict(float)
    brokers = set()
    currencies = set()
    for event in asset_events:
        data = event.get("data") or {}
        broker = data.get("broker")
        currency = str(data.get("currency") or data.get("base_currency") or "unknown")
        if broker:
            brokers.add(str(broker))
        currencies.add(currency)
        total_assets = data.get("total_assets")
        if total_assets is None:
            total_assets = data.get("net_liquidation")
        if isinstance(total_assets, (int, float)):
            totals_by_currency[currency] += float(total_assets)
        if isinstance(data.get("cash"), (int, float)):
            cash_by_currency[currency] += float(data["cash"])
        if isinstance(data.get("buying_power"), (int, float)):
            buying_power_by_currency[currency] += float(data["buying_power"])
    return {
        "asset_snapshot_count": len(asset_events),
        "brokers_with_asset_snapshots": sorted(brokers),
        "currencies_observed": sorted(currencies),
        "reported_total_assets_by_currency": dict(sorted(totals_by_currency.items())),
        "reported_cash_by_currency": dict(sorted(cash_by_currency.items())),
        "reported_buying_power_by_currency": dict(sorted(buying_power_by_currency.items())),
        "multi_currency_observed": len(currencies) > 1,
    }


def cashflow_activity_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    flow_counts: Counter[str] = Counter()
    net_cashflow_by_currency: Dict[str, float] = defaultdict(float)
    deposits_by_currency: Dict[str, float] = defaultdict(float)
    withdrawals_by_currency: Dict[str, float] = defaultdict(float)
    dividend_gross_by_currency: Dict[str, float] = defaultdict(float)
    dividend_net_by_currency: Dict[str, float] = defaultdict(float)
    dividend_tax_by_currency: Dict[str, float] = defaultdict(float)
    fx_from_amount_by_currency: Dict[str, float] = defaultdict(float)
    fx_to_amount_by_currency: Dict[str, float] = defaultdict(float)
    fx_pair_counts: Counter[str] = Counter()
    for event in usable_events:
        data = event.get("data") or {}
        subtype = str(data.get("subtype") or "unknown")
        flow_type = str(data.get("flow_type") or subtype)
        if subtype in {"cashflow", "dividend", "fx"}:
            flow_counts[flow_type] += 1
        currency = primary_currency(data)
        if subtype == "cashflow":
            amount = money_value(data, "net_amount", "amount", "gross_amount")
            if amount is not None:
                net_cashflow_by_currency[currency] += amount
                if flow_type == "deposit" or amount > 0:
                    deposits_by_currency[currency] += abs(amount)
                elif flow_type == "withdraw" or amount < 0:
                    withdrawals_by_currency[currency] += abs(amount)
        elif subtype == "dividend":
            gross = money_value(data, "gross_amount", "amount")
            net = money_value(data, "net_amount")
            tax = money_value(data, "tax")
            if gross is not None:
                dividend_gross_by_currency[currency] += gross
            if net is not None:
                dividend_net_by_currency[currency] += net
                net_cashflow_by_currency[currency] += net
            if tax is not None:
                dividend_tax_by_currency[currency] += abs(tax)
        elif subtype == "fx":
            from_currency = str(data.get("from_currency") or "unknown")
            to_currency = str(data.get("to_currency") or "unknown")
            if data.get("from_currency") and data.get("to_currency"):
                fx_pair_counts[f"{from_currency}->{to_currency}"] += 1
            if isinstance(data.get("from_amount"), (int, float)):
                fx_from_amount_by_currency[from_currency] += float(data["from_amount"])
            if isinstance(data.get("to_amount"), (int, float)):
                fx_to_amount_by_currency[to_currency] += float(data["to_amount"])
    return {
        "cashflow_event_count": subtype_event_count(usable_events, "cashflow"),
        "dividend_event_count": subtype_event_count(usable_events, "dividend"),
        "fx_event_count": subtype_event_count(usable_events, "fx"),
        "flow_type_counts": dict(sorted(flow_counts.items())),
        "deposits_by_currency": dict(sorted(deposits_by_currency.items())),
        "withdrawals_by_currency": dict(sorted(withdrawals_by_currency.items())),
        "net_cashflow_by_currency": dict(sorted(net_cashflow_by_currency.items())),
        "dividend_gross_by_currency": dict(sorted(dividend_gross_by_currency.items())),
        "dividend_net_by_currency": dict(sorted(dividend_net_by_currency.items())),
        "dividend_tax_by_currency": dict(sorted(dividend_tax_by_currency.items())),
        "fx_from_amount_by_currency": dict(sorted(fx_from_amount_by_currency.items())),
        "fx_to_amount_by_currency": dict(sorted(fx_to_amount_by_currency.items())),
        "fx_pair_counts": dict(sorted(fx_pair_counts.items())),
        "events_with_settlement_date": sum(1 for event in usable_events if (event.get("data") or {}).get("settlement_date")),
        "events_with_ex_date": sum(1 for event in usable_events if (event.get("data") or {}).get("ex_date")),
        "events_with_pay_date": sum(1 for event in usable_events if (event.get("data") or {}).get("pay_date")),
    }


def income_return_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    dividend_net_by_symbol: Dict[str, float] = defaultdict(float)
    dividend_tax_by_symbol: Dict[str, float] = defaultdict(float)
    realized_pnl_by_currency: Dict[str, float] = defaultdict(float)
    unrealized_pnl_by_currency: Dict[str, float] = defaultdict(float)
    total_pnl_by_currency: Dict[str, float] = defaultdict(float)
    fee_drag_by_currency: Dict[str, float] = defaultdict(float)
    tax_drag_by_currency: Dict[str, float] = defaultdict(float)
    for event in usable_events:
        data = event.get("data") or {}
        currency = primary_currency(data)
        symbol = str(data.get("symbol") or "unknown_symbol")
        if data.get("subtype") == "dividend":
            net = money_value(data, "net_amount")
            tax = money_value(data, "tax")
            if net is not None:
                dividend_net_by_symbol[symbol] += net
            if tax is not None:
                dividend_tax_by_symbol[symbol] += abs(tax)
        if isinstance(data.get("realized_pnl"), (int, float)):
            realized_pnl_by_currency[currency] += float(data["realized_pnl"])
        if isinstance(data.get("unrealized_pnl"), (int, float)):
            unrealized_pnl_by_currency[currency] += float(data["unrealized_pnl"])
        if isinstance(data.get("pnl"), (int, float)):
            total_pnl_by_currency[currency] += float(data["pnl"])
        if isinstance(data.get("fees"), (int, float)):
            fee_drag_by_currency[currency] += abs(float(data["fees"]))
        if isinstance(data.get("tax"), (int, float)):
            tax_drag_by_currency[currency] += abs(float(data["tax"]))
    return {
        "dividend_symbol_count": len(dividend_net_by_symbol),
        "dividend_net_by_symbol": dict(sorted(dividend_net_by_symbol.items())),
        "dividend_tax_by_symbol": dict(sorted(dividend_tax_by_symbol.items())),
        "realized_pnl_by_currency": dict(sorted(realized_pnl_by_currency.items())),
        "unrealized_pnl_by_currency": dict(sorted(unrealized_pnl_by_currency.items())),
        "total_pnl_by_currency": dict(sorted(total_pnl_by_currency.items())),
        "fee_drag_by_currency": dict(sorted(fee_drag_by_currency.items())),
        "tax_drag_by_currency": dict(sorted(tax_drag_by_currency.items())),
    }


def order_execution_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    order_events = [event for event in usable_events if (event.get("data") or {}).get("subtype") == "order"]
    execution_events = [event for event in usable_events if (event.get("data") or {}).get("subtype") == "execution"]
    status_counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    order_type_counts: Counter[str] = Counter()
    time_in_force_counts: Counter[str] = Counter()
    fill_ratios: List[float] = []
    for event in [*order_events, *execution_events]:
        data = event.get("data") or {}
        if data.get("status"):
            status_counts[str(data["status"])] += 1
        if data.get("side"):
            side_counts[str(data["side"])] += 1
        if data.get("order_type"):
            order_type_counts[str(data["order_type"])] += 1
        if data.get("time_in_force"):
            time_in_force_counts[str(data["time_in_force"])] += 1
        if isinstance(data.get("fill_ratio"), (int, float)):
            fill_ratios.append(float(data["fill_ratio"]))
    return {
        "order_event_count": len(order_events),
        "execution_event_count": len(execution_events),
        "status_counts": dict(sorted(status_counts.items())),
        "side_counts": dict(sorted(side_counts.items())),
        "order_type_counts": dict(sorted(order_type_counts.items())),
        "time_in_force_counts": dict(sorted(time_in_force_counts.items())),
        "events_with_order_id": sum(1 for event in [*order_events, *execution_events] if (event.get("data") or {}).get("order_id")),
        "events_with_trade_id": sum(1 for event in execution_events if (event.get("data") or {}).get("trade_id")),
        "events_with_settlement_date": sum(1 for event in execution_events if (event.get("data") or {}).get("settlement_date")),
        "events_with_fill_ratio": len(fill_ratios),
        "average_fill_ratio": round(sum(fill_ratios) / len(fill_ratios), 6) if fill_ratios else None,
    }


def brokerage_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in usable_events)
    broker_counts = Counter((event.get("data") or {}).get("broker", "unknown") for event in usable_events)
    field_counts = Counter(
        field
        for event in usable_events
        for field in RECOMMENDED_STRONG_FIELDS
        if (event.get("data") or {}).get(field) not in (None, "", [])
    )
    observed_expected_brokers = [broker for broker in EXPECTED_HK_US_BROKERS if broker_counts.get(broker)]
    missing_expected_brokers = [broker for broker in EXPECTED_HK_US_BROKERS if not broker_counts.get(broker)]
    observed_expected_subtypes = [subtype for subtype in EXPECTED_STRONG_TRADE_SUBTYPES if subtype_counts.get(subtype)]
    missing_expected_subtypes = [subtype for subtype in EXPECTED_STRONG_TRADE_SUBTYPES if not subtype_counts.get(subtype)]
    observed_recommended_fields = [field for field in RECOMMENDED_STRONG_FIELDS if field_counts.get(field)]
    missing_recommended_fields = [field for field in RECOMMENDED_STRONG_FIELDS if not field_counts.get(field)]
    strong_summary = strong_trade_surface_summary(events)
    account_summary = account_boundary_summary(events)
    currency_summary = currency_market_summary(events)
    fee_summary = fee_tax_margin_summary(events)
    asset_summary = asset_value_summary(events)
    cashflow_summary = cashflow_activity_summary(events)
    income_summary = income_return_summary(events)
    order_summary = order_execution_summary(events)
    audit = source_audit(events, collection_audit=collection_audit)
    has_account_ids = account_summary["account_id_count"] > 0
    has_asset_values = bool(
        asset_summary["reported_total_assets_by_currency"]
        or asset_summary["reported_cash_by_currency"]
        or asset_summary["reported_buying_power_by_currency"]
    )
    has_numeric_trade_values = any(
        strong_summary[key] > 0
        for key in (
            "events_with_amount",
            "events_with_fees",
            "events_with_tax",
            "events_with_margin",
            "events_with_pnl",
        )
    )
    all_expected_brokers = bool(observed_expected_brokers) and not missing_expected_brokers
    all_expected_surfaces = bool(observed_expected_subtypes) and not missing_expected_subtypes
    all_recommended_fields = bool(observed_recommended_fields) and not missing_recommended_fields
    if audit.get("brokerage_scope_policy_filtered_all"):
        proof_level = "scope_policy_filtered_all"
    elif not usable_events:
        gap_reason = None
        if events:
            gap_reason = (events[0].get("data") or {}).get("gap")
        proof_level = "no_authorized_brokerage_input" if gap_reason == "hk_us_brokerage_authorized_input_missing" else "no_usable_brokerage_records"
    elif all_expected_brokers and all_expected_surfaces and all_recommended_fields and has_account_ids and has_asset_values:
        proof_level = "strong_partial_brokerage_boundary"
    elif all_expected_surfaces and has_account_ids and (has_asset_values or has_numeric_trade_values):
        proof_level = "medium_partial_brokerage_boundary"
    elif has_account_ids or has_numeric_trade_values:
        proof_level = "weak_partial_brokerage_boundary"
    else:
        proof_level = "weak_brokerage_evidence"
    blockers = []
    if not usable_events:
        blockers.append("authorized_readonly_brokerage_export_or_screen_missing")
    if missing_expected_brokers:
        blockers.append("missing_expected_brokers:" + ",".join(missing_expected_brokers))
    if missing_expected_subtypes:
        blockers.append("missing_strong_trade_surfaces:" + ",".join(missing_expected_subtypes))
    if missing_recommended_fields:
        blockers.append("missing_recommended_strong_fields:" + ",".join(missing_recommended_fields))
    if not has_account_ids:
        blockers.append("account_id_boundary_missing")
    if not has_asset_values:
        blockers.append("reported_asset_value_boundary_missing")
    if not currency_summary["multi_currency_observed"]:
        blockers.append("multi_currency_boundary_not_observed")
    if not any(fee_summary[key] > 0 for key in ("events_with_fees", "events_with_tax", "events_with_margin")):
        blockers.append("fee_tax_margin_boundary_not_observed")
    blockers.extend(
        [
            "real_futu_tiger_ibkr_account_validation_missing",
            "complete_account_boundary_not_proven",
            "complete_brokerage_history_not_proven",
        ]
    )
    return {
        "proof_level": proof_level,
        "authorized_input_observed": bool(usable_events),
        "strong_trade_source": bool(usable_events),
        "can_enter_finclaw_lake": bool(usable_events),
        "can_feed_investor_wiki_evidence": bool(usable_events),
        "business_numbers_preserved": True,
        "observed_event_count": len(usable_events),
        "observed_brokers": observed_expected_brokers,
        "missing_expected_brokers": missing_expected_brokers,
        "observed_trade_surfaces": observed_expected_subtypes,
        "missing_trade_surfaces": missing_expected_subtypes,
        "observed_recommended_fields": observed_recommended_fields,
        "missing_recommended_fields": missing_recommended_fields,
        "account_boundary": {
            "account_id_count": account_summary["account_id_count"],
            "accounts_by_broker": account_summary["accounts_by_broker"],
            "full_surface_account_candidates": account_summary["full_surface_account_candidates"],
            "complete_account_boundary_claimed": False,
        },
        "asset_value_boundary": {
            "asset_snapshot_count": asset_summary["asset_snapshot_count"],
            "currencies_observed": asset_summary["currencies_observed"],
            "reported_total_assets_by_currency": asset_summary["reported_total_assets_by_currency"],
            "reported_cash_by_currency": asset_summary["reported_cash_by_currency"],
            "reported_buying_power_by_currency": asset_summary["reported_buying_power_by_currency"],
            "multi_currency_observed": asset_summary["multi_currency_observed"],
        },
        "currency_market_boundary": {
            "currency_count": currency_summary["currency_count"],
            "market_count": currency_summary["market_count"],
            "fx_pair_counts": currency_summary["fx_pair_counts"],
            "multi_currency_observed": currency_summary["multi_currency_observed"],
        },
        "fee_tax_margin_boundary": {
            "events_with_fees": fee_summary["events_with_fees"],
            "events_with_tax": fee_summary["events_with_tax"],
            "events_with_margin": fee_summary["events_with_margin"],
            "total_fees_by_currency": fee_summary["total_fees_by_currency"],
            "total_tax_by_currency": fee_summary["total_tax_by_currency"],
            "margin_requirement_by_currency": fee_summary["margin_requirement_by_currency"],
            "maintenance_margin_by_currency": fee_summary["maintenance_margin_by_currency"],
        },
        "cashflow_activity_boundary": cashflow_summary,
        "income_return_boundary": income_summary,
        "order_execution_boundary": order_summary,
        "source_boundary": {
            "requested_input_count": int(audit.get("input_count") or 0),
            "resolved_input_file_count": int(audit.get("resolved_input_file_count") or 0),
            "input_missing_count": int(audit.get("input_missing_count") or 0),
            "skipped_file_count": int(audit.get("skipped_file_count") or 0),
            "archive_count": int(audit.get("archive_count") or 0),
            "archive_member_count": int(audit.get("archive_member_count") or 0),
            "archive_member_event_count": int(audit.get("archive_member_event_count") or 0),
            "skipped_archive_member_count": int(audit.get("skipped_archive_member_count") or 0),
            "limit_reached": bool(audit.get("limit_reached")),
            "path_level_audit_available": bool(audit.get("path_results")),
            "archive_path_traversal_members_collected": False,
            "windows_drive_archive_members_collected": False,
        },
        "authorization_scope_boundary": {
            "policy": audit.get("brokerage_scope_policy", {}),
            "candidate_record_count": audit.get("candidate_record_count", audit.get("parsed_record_count", len(usable_events))),
            "scope_policy_filtered_record_count": audit.get("scope_policy_filtered_record_count", 0),
            "scope_policy_filter_reason_counts": audit.get("scope_policy_filter_reason_counts", {}),
            "brokerage_scope_policy_filtered_all": audit.get("brokerage_scope_policy_filtered_all", False),
        },
        "wiki_boundary": {
            "event_schema": "collectorx.event.v1",
            "evidence_schema": "finclaw.investor_wiki_evidence.v1",
            "collector_writes_wiki_directly": False,
            "required_flow": [
                "hk-us-brokerage collector",
                "collectorx.event.v1",
                "finclaw.investor_wiki_evidence.v1",
                "SoulMirror investor-portrait distill/organize",
            ],
        },
        "false_claims": {
            "complete_account_boundary_claimed": False,
            "complete_brokerage_history_claimed": False,
            "complete_hk_us_trade_boundary_claimed": False,
            "real_account_validation_claimed": False,
            "broker_native_api_validation_claimed": False,
            "trading_password_collected": False,
            "order_mutation_supported": False,
            "direct_broker_reconnect": False,
            "public_community_discussions_collected": False,
            "collector_writes_wiki_directly": False,
        },
        "completion_blockers": blockers,
    }


def currency_values(data: Dict[str, Any]) -> List[str]:
    values = []
    for key in ("currency", "base_currency", "from_currency", "to_currency"):
        value = data.get(key)
        if value not in (None, ""):
            values.append(str(value))
    return sorted(set(values))


def primary_currency(data: Dict[str, Any]) -> str:
    for key in ("currency", "base_currency", "from_currency", "to_currency"):
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return "unknown"


def money_value(data: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def sorted_dict_of_lists(mapping: Dict[str, set[str]]) -> Dict[str, List[str]]:
    return {key: sorted(values) for key, values in sorted(mapping.items())}


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    usable_events = usable_brokerage_events(events)
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in usable_events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    audit = {
        "source_ref_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("path")),
        "archive_member_event_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "source_section_event_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("source_section")),
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
    }
    if collection_audit:
        audit.update(collection_audit)
        audit["source_ref_count"] = max(
            int(audit.get("source_ref_count") or 0),
            sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("path")),
        )
        audit["archive_member_event_count"] = max(
            int(audit.get("archive_member_event_count") or 0),
            sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("archive_member")),
        )
        audit["archive_count"] = max(int(audit.get("archive_count") or 0), len(set(archives)))
        audit["source_section_event_count"] = max(
            int(audit.get("source_section_event_count") or 0),
            sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("source_section")),
        )
        audit["archive_path_traversal_members_collected"] = False
        audit["windows_drive_archive_members_collected"] = False
    return audit


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    usable_events = 0
    for event in events:
        if (event.get("data") or {}).get("subtype") == "collector_gap":
            continue
        usable_events += 1
        for target in event.get("wiki_targets", []):
            by_target[target].append(event)
    evidence = {
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
            "read_only_collection": True,
            "order_side_effects_allowed": False,
            "account_boundary_summary": account_boundary_summary(events),
            "currency_market_summary": currency_market_summary(events),
            "fee_tax_margin_summary": fee_tax_margin_summary(events),
            "asset_value_summary": asset_value_summary(events),
            "cashflow_activity_summary": cashflow_activity_summary(events),
            "income_return_summary": income_return_summary(events),
            "order_execution_summary": order_execution_summary(events),
            "brokerage_boundary_proof": brokerage_boundary_proof(events),
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }
    return augment_evidence_with_dimensions(evidence, events, INVESTOR_WIKI_SUBDIMENSION_RULES)


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
