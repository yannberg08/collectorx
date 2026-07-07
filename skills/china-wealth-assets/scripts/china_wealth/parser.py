"""Parse China fund and wealth-management exports."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "china-wealth-assets"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xlsx", ".xlsm", ".html", ".htm", ".txt", ".md", ".markdown", ".zip"}
ARCHIVE_MEMBER_EXTENSIONS = SUPPORTED_EXTENSIONS - {".zip"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session", "paypass")
EXPECTED_P0_PLATFORMS = ("alipay", "tiantian-fund", "danjuan", "qieman", "bank-wealth")
RECOMMENDED_FIELDS = (
    "platform",
    "product_code",
    "product_name",
    "product_type",
    "quantity",
    "nav",
    "market_value",
    "total_asset",
    "available_cash",
    "cost",
    "pnl",
    "pnl_rate",
    "transaction_amount",
    "fee",
    "side",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="china_wealth_authorized_input_missing")]
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
        return parse_table(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_excel(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".html", ".htm"}:
        return [parse_html(path)]
    if suffix == ".zip":
        return parse_zip(path)
    return [parse_text(path)]


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-china-wealth-") as tmp:
        tmp_root = Path(tmp)
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(member_name)
            suffix = Path(member_name).suffix.lower()
            if not is_safe_archive_member(member_path) or suffix not in ARCHIVE_MEMBER_EXTENSIONS:
                continue
            target = tmp_root.joinpath(*member_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            for member_row, record in enumerate(parse_path(target), start=1):
                if isinstance(record, dict):
                    record["_collectorx_raw_ref"] = {
                        "path": f"{path}::{member_name}",
                        "archive": str(path),
                        "archive_member": member_name,
                        "member_row": member_row,
                    }
                records.append(record)
    return records


def is_safe_archive_member(member_path: PurePosixPath) -> bool:
    return bool(member_path.parts) and not member_path.is_absolute() and ".." not in member_path.parts


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_excel(path: Path) -> List[Dict[str, Any]]:
    import openpyxl  # type: ignore

    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    records: List[Dict[str, Any]] = []
    try:
        for sheet in workbook.worksheets[:20]:
            header: Optional[List[str]] = None
            for raw_row in sheet.iter_rows(values_only=True):
                values = ["" if value is None else str(value).strip() for value in raw_row]
                if not any(values):
                    continue
                if header is None:
                    header = [value or f"column_{index + 1}" for index, value in enumerate(values)]
                    continue
                record = {header[index]: values[index] for index in range(min(len(header), len(values))) if header[index]}
                record["source_sheet"] = sheet.title
                records.append(record)
    finally:
        workbook.close()
    return records


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_records(json.loads(text))
    return [row if isinstance(row, dict) else {"value": row} for row in rows]


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    rows: List[Any] = []
    for key in ("assets", "assetSnapshots", "holdings", "positions", "funds", "products", "transactions", "trades", "records", "items", "list", "data"):
        value = loaded.get(key)
        if isinstance(value, list):
            rows.extend(value)
        if isinstance(value, dict):
            nested = extract_records(value)
            if not (len(nested) == 1 and nested[0] == value):
                rows.extend(nested)
    if rows:
        return rows
    for value in loaded.values():
        if isinstance(value, list):
            return value
    return [loaded]


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "record_type": "screen_snapshot",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(path, text),
        "content": text,
        "url": first_url(html),
        "path": str(path),
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "record_type": "screen_snapshot",
        "title": infer_title(path, text),
        "content": text,
        "url": first_url(text),
        "path": str(path),
    }


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    subtype = infer_subtype(record)
    platform = infer_platform(record, path)
    side = normalize_side(first(record, ["side", "action", "trade_type", "transaction_type", "交易类型", "操作", "业务类型", "类型"]))
    event_time = first(record, ["time", "date", "trade_date", "confirm_date", "updated_at", "交易日期", "确认日期", "更新时间", "日期"])
    data = {
        "subtype": subtype,
        "platform": platform,
        "account": first(record, ["account", "account_id", "账户", "账号", "户名"]),
        "product_code": first(record, ["product_code", "fund_code", "code", "基金代码", "产品代码", "代码"]),
        "product_name": first(record, ["product_name", "fund_name", "name", "title", "基金名称", "产品名称", "名称", "标题"]),
        "product_type": infer_product_type(record),
        "currency": first(record, ["currency", "币种"]) or "CNY",
        "quantity": number(first(record, ["quantity", "shares", "份额", "持有份额", "持仓份额"])),
        "nav": number(first(record, ["nav", "net_value", "unit_nav", "净值", "单位净值"])),
        "market_value": number(first(record, ["market_value", "holding_amount", "position_value", "市值", "资产", "持仓金额", "持有金额", "当前市值"])),
        "total_asset": number(first(record, ["total_asset", "asset_total", "资产总额", "总资产", "总金额"])),
        "available_cash": number(first(record, ["available_cash", "cash", "可用余额", "现金", "余额"])),
        "cost": number(first(record, ["cost", "cost_amount", "成本", "持仓成本"])),
        "pnl": number(first(record, ["pnl", "profit", "收益", "持有收益", "累计收益", "浮动盈亏"])),
        "pnl_rate": percent(first(record, ["pnl_rate", "profit_rate", "收益率", "持有收益率"])),
        "transaction_amount": number(first(record, ["trade_amount", "transaction_amount", "amount", "确认金额", "交易金额", "申购金额", "赎回金额"])),
        "fee": number(first(record, ["fee", "手续费", "费用"])),
        "side": side,
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}
    raw_ref = {
        "path": str(path),
        "row": row,
        "sheet": first(record, ["source_sheet"]),
        "subtype": subtype,
        "platform": platform,
    }
    if isinstance(record.get("_collectorx_raw_ref"), dict):
        raw_ref.update(record["_collectorx_raw_ref"])
        raw_ref["row"] = row
        raw_ref["sheet"] = first(record, ["source_sheet"])
        raw_ref["subtype"] = subtype
        raw_ref["platform"] = platform
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, json.dumps(sanitized(record), ensure_ascii=False, sort_keys=True)),
        "collector": COLLECTOR,
        "source": "中国基金理财用户授权资产数据",
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
    text = json.dumps(sanitized(record), ensure_ascii=False).lower()
    explicit = first(record, ["subtype", "record_type", "type", "类型", "业务类型", "交易类型"])
    if explicit:
        low = explicit.lower()
        if any(token in low for token in ["asset", "snapshot", "资产", "总资产", "screen_snapshot"]):
            if has_product_identity(record):
                return "fund_holding"
            return "asset_snapshot"
        if any(token in low for token in ["dividend", "分红"]):
            return "fund_transaction"
        if any(token in low for token in ["buy", "sell", "subscribe", "redeem", "申购", "赎回", "定投", "转换", "买入", "卖出"]):
            return "fund_transaction"
        if any(token in low for token in ["wealth", "理财", "存款", "银行"]):
            return "wealth_holding"
        if any(token in low for token in ["cash", "货币", "余额宝", "现金"]):
            return "cash_management"
        if any(token in low for token in ["holding", "position", "持仓", "基金"]):
            return "fund_holding"
    if any(token in text for token in ["申购", "赎回", "定投", "转换", "分红", "buy", "sell", "redeem", "subscribe"]):
        return "fund_transaction"
    if any(token in text for token in ["银行理财", "理财产品", "封闭式", "开放式理财"]):
        return "wealth_holding"
    if any(token in text for token in ["余额宝", "零钱通", "现金管理", "货币基金"]):
        return "cash_management"
    if any(key in record for key in ["总资产", "asset_total", "total_asset", "资产总额"]) and not has_product_identity(record):
        return "asset_snapshot"
    return "fund_holding"


def has_product_identity(record: Dict[str, Any]) -> bool:
    return first(record, ["product_code", "fund_code", "code", "基金代码", "产品代码", "代码", "product_name", "fund_name", "name", "基金名称", "产品名称", "名称"]) is not None


def kind_for_subtype(subtype: str) -> str:
    if subtype == "fund_transaction":
        return "trade"
    if subtype in {"fund_holding", "wealth_holding", "cash_management"}:
        return "holding"
    return "other"


def wiki_targets_for_subtype(subtype: str) -> List[str]:
    if subtype == "fund_transaction":
        return ["investor.record_review.decision_log", "investor.execution.orders", "external.capital.cashflows"]
    if subtype in {"fund_holding", "wealth_holding", "cash_management"}:
        return ["investor.risk_portfolio.current_positions", "investor.risk_portfolio.portfolio_constraints", "external.capital.assets"]
    if subtype == "asset_snapshot":
        return ["investor.risk_portfolio.current_assets", "external.capital.assets"]
    return ["investor.data_quality.collection_gaps"]


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in events)
    gap_only = bool(events) and set(subtype_counts) == {"collector_gap"}
    value_events = [
        event for event in events
        if any((event.get("data") or {}).get(key) is not None for key in ("market_value", "total_asset", "transaction_amount", "pnl"))
    ]
    return {
        "schema": "china_wealth.assets.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "source_file_count": len({(event.get("raw_ref") or {}).get("path") for event in events if (event.get("raw_ref") or {}).get("path")}),
        "kind_counts": dict(sorted(kind_counts.items())),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "numeric_coverage": {
            "events_with_value_fields": len(value_events),
            "events_without_value_fields": max(len(events) - len(value_events), 0),
        },
        "field_coverage": field_coverage(events),
        "asset_value_summary": asset_value_summary(events),
        "platform_coverage": platform_coverage(platform_counts),
        "evidence_policy": {
            "complete_asset_boundary_claimed": False,
            "real_account_validation": False,
            "payment_or_bank_credentials_collected": False,
            "requires_corroboration_with": ["brokerage_accounts", "bank_statements", "fund_platform_exports", "investment_notes"],
        },
        "collection_readiness": {
            "status": "needs_china_wealth_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events),
            "can_claim_complete_asset_boundary": False,
            "asset_boundary_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "提供支付宝/基金/理财授权导出后重跑。" if gap_only else "可进入投资分身蒸馏；后续按平台做只读真机验证后，才能声明完整资产边界。",
        },
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in events)
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
            "subtype_counts": dict(sorted(subtype_counts.items())),
            "platform_counts": dict(sorted(platform_counts.items())),
            "platform_coverage": platform_coverage(platform_counts),
            "field_coverage": field_coverage(events),
            "asset_value_summary": asset_value_summary(events),
            "asset_boundary_source": True,
            "complete_asset_boundary_claimed": False,
        },
    }


def platform_coverage(platform_counts: Counter) -> Dict[str, Any]:
    observed = sorted(platform for platform in platform_counts if platform not in {"unknown", ""} and platform_counts[platform] > 0)
    missing = [platform for platform in EXPECTED_P0_PLATFORMS if platform not in observed]
    return {
        "expected_p0_platforms": list(EXPECTED_P0_PLATFORMS),
        "observed_platforms": observed,
        "missing_expected_platforms": missing,
        "unknown_event_count": platform_counts.get("unknown", 0),
        "complete_expected_platforms_observed": not missing,
        "real_account_validation": False,
    }


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if (event.get("data") or {}).get("subtype") != "collector_gap"]
    field_counts = {
        field: sum(1 for event in usable_events if (event.get("data") or {}).get(field) is not None)
        for field in RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_product_identity": sum(
            1
            for event in usable_events
            if (event.get("data") or {}).get("product_code") or (event.get("data") or {}).get("product_name")
        ),
    }


def asset_value_summary(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = defaultdict(lambda: {"market_value": 0.0, "total_asset": 0.0, "transaction_amount": 0.0})
    for event in events:
        data = event.get("data") or {}
        if data.get("subtype") == "collector_gap":
            continue
        platform = str(data.get("platform") or "unknown")
        for key in ("market_value", "total_asset", "transaction_amount"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                summary[platform][key] += float(value)
    return {
        platform: {key: round(value, 6) for key, value in values.items() if value}
        for platform, values in sorted(summary.items())
        if any(values.values())
    }


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def infer_platform(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["platform", "app", "source", "来源", "平台", "渠道"])
    text = ((explicit or "") + " " + json.dumps(sanitized(record), ensure_ascii=False) + " " + str(path)).lower()
    if "alipay" in text or "支付宝" in text or "蚂蚁" in text:
        return "alipay"
    if "tiantian" in text or "eastmoney fund" in text or "天天基金" in text:
        return "tiantian-fund"
    if "danjuan" in text or "蛋卷" in text:
        return "danjuan"
    if "qieman" in text or "且慢" in text:
        return "qieman"
    if "bank" in text or "银行" in text or "招行" in text or "工行" in text or "建行" in text or "农行" in text:
        return "bank-wealth"
    return "unknown"


def infer_product_type(record: Dict[str, Any]) -> Optional[str]:
    explicit = first(record, ["product_type", "fund_type", "type", "产品类型", "基金类型", "类型"])
    name = first(record, ["product_name", "fund_name", "name", "基金名称", "产品名称", "名称"]) or ""
    probe = f"{explicit or ''} {name}"
    if any(token in probe for token in ["银行理财", "理财产品", "固收", "封闭式", "开放式理财"]):
        return "wealth_product"
    if any(token in probe for token in ["货币", "余额宝", "现金管理"]):
        return "money_market"
    if any(token in probe for token in ["指数", "ETF", "etf"]):
        return "index_fund"
    if any(token in probe for token in ["债券", "债基"]):
        return "bond_fund"
    if explicit:
        return explicit
    if first(record, ["fund_code", "基金代码"]):
        return "fund"
    return None


def number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("￥", "").replace("¥", "").replace("%", "").replace("元", "").strip()
    if text in {"--", "-", ""}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def percent(value: Optional[str]) -> Optional[float]:
    parsed = number(value)
    if parsed is None:
        return None
    return parsed / 100 if value and "%" in str(value) else parsed


def normalize_side(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.lower()
    if any(token in text for token in ["buy", "subscribe", "申购", "买入", "定投"]):
        return "buy"
    if any(token in text for token in ["sell", "redeem", "赎回", "卖出"]):
        return "sell"
    if "分红" in text or "dividend" in text:
        return "dividend"
    if "转换" in text or "convert" in text:
        return "convert"
    return value


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).startswith("_collectorx_"):
                continue
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            cleaned[str(key)] = sanitized(item)
        return cleaned
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:2000]
    return value


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def meta_content(html: str, name: str) -> Optional[str]:
    pattern = rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, flags=re.IGNORECASE)
    return unescape(match.group(1)).strip() if match else None


def title_tag(html: str) -> Optional[str]:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return html_to_text(match.group(1))[:200] if match else None


def first_url(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return match.group(0) if match else None


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return path.stem


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
