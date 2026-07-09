"""Parse China fund and wealth-management exports."""

from __future__ import annotations

import base64
import binascii
import csv
import fnmatch
import hashlib
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlparse

try:
    from collectorx.investor_wiki import augment_evidence_with_dimensions
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution outside repo cwd
    for parent in Path(__file__).resolve().parents:
        if (parent / "collectorx").exists():
            sys.path.insert(0, str(parent))
            break
    from collectorx.investor_wiki import augment_evidence_with_dimensions


COLLECTOR = "china-wealth-assets"
CN_TZ = timezone(timedelta(hours=8))
DATA_QUALITY_TARGET = "collectorx.data_quality.collection_gaps"
SUPPORTED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".markdown",
    ".pdf",
    ".har",
    ".zip",
}
ARCHIVE_MEMBER_EXTENSIONS = SUPPORTED_EXTENSIONS - {".zip"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session", "paypass")
EXPECTED_P0_PLATFORMS = ("alipay", "tiantian-fund", "danjuan", "qieman", "bank-wealth")
HAR_PLATFORM_DOMAINS = {
    "alipay": ("alipay.com", "antfortune.com", "antfin.com", "mybank.cn"),
    "tiantian-fund": ("eastmoney.com", "1234567.com.cn"),
    "danjuan": ("danjuanapp.com", "danjuanfunds.com", "danjuan.com"),
    "qieman": ("qieman.com", "qieman.com.cn"),
    "bank-wealth": (
        "abchina.com",
        "bankcomm.com",
        "boc.cn",
        "ccb.com",
        "cebbank.com",
        "cgbchina.com.cn",
        "cib.com.cn",
        "citicbank.com",
        "cmbchina.com",
        "cmbc.com.cn",
        "hxb.com.cn",
        "icbc.com.cn",
        "pingan.com",
        "pingan.com.cn",
        "psbc.com",
        "spdb.com.cn",
    ),
}
RECOMMENDED_FIELDS = (
    "platform",
    "account",
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
ACCOUNT_FIELDS = (
    "account",
    "account_id",
    "account_name",
    "fund_account",
    "wealth_account",
    "portfolio_account",
    "账户",
    "账号",
    "账户名称",
    "交易账号",
    "基金账号",
    "理财账号",
    "组合账号",
    "户名",
)
VALUE_FIELDS = ("market_value", "total_asset", "transaction_amount", "available_cash", "cost", "pnl", "fee")
EXPECTED_ASSET_SURFACES = ("asset_snapshot", "fund_holding", "wealth_holding", "cash_management", "fund_transaction")
HOLDING_SUBTYPES = {"fund_holding", "wealth_holding", "cash_management"}
TRADE_SUBTYPES = {"fund_transaction"}
ACCOUNT_PROOF_LEVEL_ORDER = (
    "strong_partial_account_boundary",
    "medium_partial_account_boundary",
    "weak_partial_account_boundary",
    "no_account_evidence",
)
INVESTOR_WIKI_SUBDIMENSION_RULES = {
    "inv-risk-view": {
        "support_level": "strong",
        "route_targets": [
            "investor.risk_portfolio.current_assets",
            "investor.risk_portfolio.current_positions",
            "investor.risk_portfolio.portfolio_constraints",
            "external.capital.assets",
        ],
        "signals": ["基金、理财和现金类资产的金额、账户和持仓能支撑风险暴露画像。"],
        "gaps": ["资产暴露不是风险信念本身，仍需规则、笔记和复盘解释风险边界。"],
    },
    "inv-value-preference": {
        "support_level": "medium",
        "route_targets": ["investor.risk_portfolio.current_positions", "external.capital.assets"],
        "signals": ["基金、理财、现金管理产品结构可侧写收益/波动偏好。"],
        "gaps": ["产品选择原因仍需研究材料、笔记或对话补充。"],
    },
    "inv-style-profile": {
        "support_level": "medium",
        "route_targets": ["investor.risk_portfolio.current_positions", "investor.risk_portfolio.current_assets", "external.capital.assets"],
        "signals": ["持仓类型、金额和申赎行为能形成基金/理财风格画像。"],
        "gaps": ["无法单独区分主动风格与被动配置。"],
    },
    "inv-decision-log": {
        "support_level": "strong",
        "route_targets": ["investor.record_review.decision_log", "investor.execution.orders", "external.capital.cashflows"],
        "signals": ["申购、赎回和资金流水可形成资产配置决策时间线。"],
        "gaps": ["交易理由和事后评价需要其他解释性采集器补足。"],
    },
    "inv-portfolio-preference": {
        "support_level": "strong",
        "route_targets": [
            "investor.risk_portfolio.current_assets",
            "investor.risk_portfolio.current_positions",
            "investor.risk_portfolio.portfolio_constraints",
            "external.capital.assets",
        ],
        "signals": ["账户、产品、币种和金额能支撑组合管理偏好。"],
        "gaps": ["完整资产边界必须经过真实账户或多平台导出验证。"],
    },
    "inv-execution-discipline": {
        "support_level": "medium",
        "route_targets": ["investor.execution.orders", "external.capital.cashflows", "investor.record_review.decision_log"],
        "signals": ["申赎节奏、金额和费用可用于观察执行纪律。"],
        "gaps": ["缺计划单、目标仓位和计划 vs 实际对比。"],
    },
    "inv-time-preference": {
        "support_level": "medium",
        "route_targets": ["investor.record_review.decision_log", "investor.execution.orders", "external.capital.cashflows"],
        "signals": ["申赎日期和持有资产类型能提供期限偏好线索。"],
        "gaps": ["长期/短期偏好需要结合持有周期和用户目标确认。"],
    },
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    scope_policy: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(
        inputs,
        collected_at=collected_at,
        limit=limit,
        scope_policy=scope_policy,
    )
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    scope_policy: Optional[Dict[str, Any]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    paths = list(iter_paths(input_list))
    policy = normalize_china_wealth_scope_policy(scope_policy)
    audit = {
        "source_type": "authorized_local_china_wealth_export",
        "input_count": len(input_list),
        "resolved_input_file_count": len(paths),
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "parsed_record_count": 0,
        "emitted_event_count": 0,
        "browser_network_export_supported": True,
        "authorized_browser_network_export_used": False,
        "browser_network_export_file_count": 0,
        "har_entry_count": 0,
        "har_investment_entry_count": 0,
        "har_response_record_count": 0,
        "har_skipped_entry_count": 0,
        "har_skip_reason_counts": {},
        "har_endpoint_counts": {},
        "har_platform_entry_counts": {},
        "har_secret_material_stripped_count": 0,
        "har_query_string_stripped_count": 0,
        "har_secret_material_policy": "request_headers_cookies_authorization_query_strings_are_never_written_to_events_or_manifest",
        "pdf_import_supported": True,
        "pdf_parser": "pdfplumber",
        "pdf_parser_available": None,
        "pdf_text_ocr_used": False,
        "pdf_file_count": 0,
        "pdf_page_count": 0,
        "pdf_table_count": 0,
        "pdf_table_record_count": 0,
        "pdf_text_record_count": 0,
        "pdf_parse_error_count": 0,
        "limit": limit,
        "limit_reached": False,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "real_account_adapter_used": False,
        "complete_asset_boundary_claimed": False,
        "candidate_record_count": 0,
        "scope_policy_filtered_record_count": 0,
        "scope_policy_filter_reason_counts": {},
        "china_wealth_scope_policy": policy,
        "china_wealth_scope_policy_filtered_all": False,
        "path_results": [],
    }
    if not paths:
        events = [gap_event(collected_at=collected_at, reason="china_wealth_authorized_input_missing")]
        audit["emitted_event_count"] = len(events)
        finalize_audit(audit)
        return events, audit
    events: List[Dict[str, Any]] = []
    for path in paths:
        path_result = {
            "path": str(path),
            "extension": path.suffix.lower() or "<none>",
            "parsed_record_count": 0,
            "candidate_record_count": 0,
            "scope_policy_filtered_record_count": 0,
            "emitted_event_count": 0,
            "status": "parsed",
        }
        audit["path_results"].append(path_result)
        increment_counter(audit, "extension_counts", path_result["extension"])
        records = parse_path(path, audit=audit)
        path_result["parsed_record_count"] = len(records)
        audit["parsed_record_count"] += len(records)
        for row, record in enumerate(records, start=1):
            event = record_to_event(record, path=path, row=row, collected_at=collected_at)
            audit["candidate_record_count"] += 1
            path_result["candidate_record_count"] += 1
            filter_reason = china_wealth_scope_policy_filter_reason(event, policy)
            if filter_reason:
                audit["scope_policy_filtered_record_count"] += 1
                path_result["scope_policy_filtered_record_count"] += 1
                increment_counter(audit, "scope_policy_filter_reason_counts", filter_reason)
                continue
            events.append(event)
            path_result["emitted_event_count"] += 1
            if limit is not None and len(events) >= limit:
                audit["limit_reached"] = True
                break
        if path_result["candidate_record_count"]:
            if policy["enabled"] and path_result["scope_policy_filtered_record_count"] == path_result["candidate_record_count"] and path_result["emitted_event_count"] == 0:
                path_result["status"] = "filtered_by_scope_policy"
                path_result["reason"] = "scope_policy_excluded_all_records"
            elif path_result["scope_policy_filtered_record_count"]:
                path_result["scope_policy_filter_status"] = "partially_filtered"
        if audit["limit_reached"]:
            break
    scope_policy_filtered_all = (
        policy["enabled"]
        and audit["candidate_record_count"] > 0
        and audit["scope_policy_filtered_record_count"] == audit["candidate_record_count"]
        and not events
    )
    audit["china_wealth_scope_policy_filtered_all"] = scope_policy_filtered_all
    if scope_policy_filtered_all:
        events = [
            scope_policy_filtered_all_event(
                collection_audit=audit,
                collected_at=collected_at,
            )
        ]
    elif not events:
        events = [gap_event(collected_at=collected_at, reason="china_wealth_records_empty")]
    audit["emitted_event_count"] = len(events)
    finalize_audit(audit)
    return events, audit


CHINA_WEALTH_SCOPE_POLICY_KEYS = (
    "platforms",
    "accounts",
    "subtypes",
    "product_codes",
    "product_names",
    "currencies",
    "sides",
    "keywords",
)


def split_scope_values(values: Any) -> List[str]:
    if values in (None, ""):
        return []
    if isinstance(values, str):
        raw_values: Iterable[Any] = [values]
    elif isinstance(values, (list, tuple, set)):
        raw_values = values
    else:
        raw_values = [values]
    items: List[str] = []
    for value in raw_values:
        if value in (None, ""):
            continue
        if isinstance(value, (list, tuple, set)):
            items.extend(split_scope_values(value))
            continue
        items.extend(part.strip() for part in re.split(r"[,，、;；|\n]+", str(value)) if part.strip())
    return items


def normalize_china_wealth_scope_policy(scope_policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = scope_policy or {}
    policy: Dict[str, Any] = {}
    for key in CHINA_WEALTH_SCOPE_POLICY_KEYS:
        allow_key = f"allow_{key}"
        deny_key = f"deny_{key}"
        policy[allow_key] = normalize_scope_terms(split_scope_values(raw.get(allow_key)), key=key)
        policy[deny_key] = normalize_scope_terms(split_scope_values(raw.get(deny_key)), key=key)
    policy["enabled"] = any(policy[f"{prefix}_{key}"] for key in CHINA_WEALTH_SCOPE_POLICY_KEYS for prefix in ("allow", "deny"))
    return policy


def normalize_scope_terms(values: Iterable[str], *, key: str) -> List[str]:
    normalized: List[str] = []
    for value in values:
        text = value.strip()
        if not text:
            continue
        if key == "platforms":
            text = normalize_scope_platform(text)
        elif key == "subtypes":
            text = normalize_scope_subtype(text)
        elif key == "sides":
            text = normalize_side(text) or text
        elif key in {"product_codes", "currencies"}:
            text = re.sub(r"\s+", "", text)
        normalized.append(text.lower())
    return sorted(dict.fromkeys(normalized))


def normalize_scope_platform(value: str) -> str:
    return infer_platform({"platform": value}, Path(value))


def normalize_scope_subtype(value: str) -> str:
    return infer_subtype({"type": value, "类型": value})


def china_wealth_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy.get("enabled"):
        return None
    data = event.get("data") or {}
    platform = normalize_scope_platform(str(data.get("platform") or ""))
    account = str(data.get("account") or "").strip().lower()
    subtype = normalize_scope_subtype(str(data.get("subtype") or ""))
    product_code = re.sub(r"\s+", "", str(data.get("product_code") or "")).lower()
    product_name = str(data.get("product_name") or "").strip().lower()
    currency = re.sub(r"\s+", "", str(data.get("currency") or "")).lower()
    side = str(data.get("side") or "").strip().lower()
    search_text = china_wealth_scope_search_text(event)

    if scope_identity_match(platform, policy.get("deny_platforms", [])):
        return "platform_denied"
    if scope_identity_match(account, policy.get("deny_accounts", [])):
        return "account_denied"
    if scope_identity_match(subtype, policy.get("deny_subtypes", [])):
        return "subtype_denied"
    if scope_identity_match(product_code, policy.get("deny_product_codes", [])):
        return "product_code_denied"
    if scope_text_match(product_name, policy.get("deny_product_names", [])):
        return "product_name_denied"
    if scope_identity_match(currency, policy.get("deny_currencies", [])):
        return "currency_denied"
    if scope_identity_match(side, policy.get("deny_sides", [])):
        return "side_denied"
    if scope_text_match(search_text, policy.get("deny_keywords", [])):
        return "keyword_denied"

    if policy.get("allow_platforms") and not scope_identity_match(platform, policy["allow_platforms"]):
        return "platform_not_allowed"
    if policy.get("allow_accounts") and not scope_identity_match(account, policy["allow_accounts"]):
        return "account_not_allowed"
    if policy.get("allow_subtypes") and not scope_identity_match(subtype, policy["allow_subtypes"]):
        return "subtype_not_allowed"
    if policy.get("allow_product_codes") and not scope_identity_match(product_code, policy["allow_product_codes"]):
        return "product_code_not_allowed"
    if policy.get("allow_product_names") and not scope_text_match(product_name, policy["allow_product_names"]):
        return "product_name_not_allowed"
    if policy.get("allow_currencies") and not scope_identity_match(currency, policy["allow_currencies"]):
        return "currency_not_allowed"
    if policy.get("allow_sides") and not scope_identity_match(side, policy["allow_sides"]):
        return "side_not_allowed"
    if policy.get("allow_keywords") and not scope_text_match(search_text, policy["allow_keywords"]):
        return "keyword_not_allowed"
    return None


def scope_identity_match(value: str, patterns: Iterable[str]) -> bool:
    if not value:
        return False
    normalized = value.lower()
    return any(fnmatch.fnmatchcase(normalized, str(pattern).lower()) for pattern in patterns)


def scope_text_match(value: str, patterns: Iterable[str]) -> bool:
    if not value:
        return False
    haystack = value.lower()
    for pattern in patterns:
        needle = str(pattern).lower().strip()
        if not needle:
            continue
        if any(char in needle for char in "*?[]"):
            if fnmatch.fnmatchcase(haystack, needle):
                return True
        elif needle in haystack:
            return True
    return False


def china_wealth_scope_search_text(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    values = [
        data.get("platform"),
        data.get("account"),
        data.get("subtype"),
        data.get("product_code"),
        data.get("product_name"),
        data.get("product_type"),
        data.get("currency"),
        data.get("side"),
        raw_ref.get("path"),
        raw_ref.get("sheet"),
        raw_ref.get("archive_member"),
        raw_ref.get("har_endpoint"),
    ]
    return "\n".join(str(value) for value in values if value not in (None, "", [], {}))


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield child
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def parse_path(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_excel(path)
    if suffix == ".xls":
        return parse_legacy_excel(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".html", ".htm"}:
        return parse_html(path)
    if suffix == ".pdf":
        return parse_pdf(path, audit=audit)
    if suffix == ".har":
        return parse_har(path, audit=audit)
    if suffix == ".zip":
        return parse_zip(path, audit=audit)
    return [parse_text(path)]


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-china-wealth-") as tmp:
        tmp_root = Path(tmp)
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(member_name)
            suffix = Path(member_name).suffix.lower()
            if audit is not None:
                audit["archive_member_count"] += 1
                increment_counter(audit, "archive_member_extension_counts", suffix or "<none>")
            if not is_safe_archive_member(member_path) or suffix not in ARCHIVE_MEMBER_EXTENSIONS:
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", suffix or "<none>")
                continue
            target = tmp_root.joinpath(*member_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            for member_row, record in enumerate(parse_path(target, audit=audit), start=1):
                if isinstance(record, dict):
                    raw_ref = record.get("_collectorx_raw_ref") if isinstance(record.get("_collectorx_raw_ref"), dict) else {}
                    record["_collectorx_raw_ref"] = {
                        **raw_ref,
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
    return parse_delimited_text(text, delimiter=delimiter)


def parse_delimited_text(text: str, *, delimiter: Optional[str] = None, source_sheet: Optional[str] = None) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    actual_delimiter = delimiter or sniff_delimiter(text)
    records: List[Dict[str, Any]] = []
    for row in csv.DictReader(text.splitlines(), delimiter=actual_delimiter):
        record = {str(key): value for key, value in row.items() if key is not None}
        if source_sheet and record:
            record["source_sheet"] = source_sheet
        records.append(record)
    return records


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


def parse_legacy_excel(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_bytes()
    if raw.startswith(b"PK"):
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as handle:
            handle.write(raw)
            handle.flush()
            return parse_excel(Path(handle.name))
    text = decode_legacy_text(raw)
    stripped = text.lstrip()
    if stripped.startswith("<?xml") or "<Workbook" in stripped[:1000]:
        xml_records = parse_xml_spreadsheet(text)
        if xml_records:
            return xml_records
    if "<table" in stripped[:5000].lower() or "<html" in stripped[:5000].lower():
        table_records = html_tables_to_records(text)
        if table_records:
            return table_records
    table_records = parse_delimited_text(text, source_sheet="legacy_xls_text")
    if table_records:
        return table_records
    return [legacy_text_snapshot(path, text)]


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_records(json.loads(text))
    return [row if isinstance(row, dict) else {"value": row} for row in rows]


def parse_har(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if audit is not None:
        audit["authorized_browser_network_export_used"] = True
        audit["browser_network_export_file_count"] += 1
    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    entries = loaded.get("log", {}).get("entries", []) if isinstance(loaded, dict) else []
    records: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            record_har_skip(audit, "malformed_entry")
            continue
        if audit is not None:
            audit["har_entry_count"] += 1
            audit["har_secret_material_stripped_count"] += har_secret_material_count(entry)
        request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
        response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
        parsed_url = urlparse(str(request.get("url") or ""))
        platform = platform_for_har_host(parsed_url)
        if platform is None:
            record_har_skip(audit, "non_investment_platform_url")
            continue
        if audit is not None:
            audit["har_investment_entry_count"] += 1
            increment_counter(audit, "har_platform_entry_counts", platform)
            if parsed_url.query:
                audit["har_query_string_stripped_count"] += 1
        endpoint = har_endpoint(parsed_url)
        if audit is not None:
            increment_counter(audit, "har_endpoint_counts", endpoint)
        text = decode_har_response_text(response.get("content") if isinstance(response.get("content"), dict) else {})
        if not text:
            record_har_skip(audit, "missing_response_text")
            continue
        try:
            payload = loads_network_json(text)
        except json.JSONDecodeError:
            record_har_skip(audit, "non_json_response")
            continue
        extracted = extract_records(payload)
        if audit is not None:
            audit["har_response_record_count"] += len(extracted)
        for row, item in enumerate(extracted, start=1):
            record = item if isinstance(item, dict) else {"value": item}
            record = with_context(
                record,
                {
                    "platform": platform,
                    "har_endpoint": endpoint,
                    "har_status": response.get("status"),
                    "har_row": row,
                },
            )
            record["_collectorx_raw_ref"] = {
                "path": str(path),
                "har_entry": index,
                "har_row": row,
                "har_endpoint": endpoint,
                "har_status": response.get("status"),
                "parser": "har",
                "platform": platform,
            }
            records.append(record)
    return records


def platform_for_har_host(parsed_url: Any) -> Optional[str]:
    host = str(getattr(parsed_url, "netloc", "") or "").lower().split("@")[-1].split(":")[0]
    for platform, domains in HAR_PLATFORM_DOMAINS.items():
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            return platform
    return None


def har_endpoint(parsed_url: Any) -> str:
    path = str(getattr(parsed_url, "path", "") or "/")
    return path or "/"


def decode_har_response_text(content: Dict[str, Any]) -> Optional[str]:
    text = content.get("text")
    if text in (None, ""):
        return None
    if str(content.get("encoding") or "").lower() == "base64":
        try:
            return base64.b64decode(str(text)).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError, TypeError):
            return None
    return str(text)


def loads_network_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("while(1);"):
        stripped = stripped[len("while(1);") :].lstrip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        jsonp = re.match(r"^[A-Za-z_$][\w$]*\((.*)\)\s*;?\s*$", stripped, flags=re.DOTALL)
        if jsonp:
            return json.loads(jsonp.group(1))
        raise


def record_har_skip(audit: Optional[Dict[str, Any]], reason: str) -> None:
    if audit is None:
        return
    audit["har_skipped_entry_count"] += 1
    increment_counter(audit, "har_skip_reason_counts", reason)


def har_secret_material_count(entry: Dict[str, Any]) -> int:
    count = 0
    for section_name in ("request", "response"):
        section = entry.get(section_name)
        if not isinstance(section, dict):
            continue
        for list_name in ("headers", "cookies"):
            values = section.get(list_name)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").lower()
                if any(fragment in name for fragment in SECRET_KEY_FRAGMENTS):
                    count += 1
    return count


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
    rows: List[Any] = []
    for key in ("assets", "assetSnapshots", "holdings", "positions", "funds", "products", "transactions", "trades", "records", "items", "list", "data"):
        value = loaded.get(key)
        if isinstance(value, list):
            rows.extend(with_context(item, context) for item in value)
        if isinstance(value, dict):
            nested = extract_records(value)
            if not (len(nested) == 1 and nested[0] == value):
                rows.extend(with_context(item, context) for item in nested)
    if rows:
        return rows
    for value in loaded.values():
        if isinstance(value, list):
            return [with_context(item, context) for item in value]
    return [loaded]


def with_context(item: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {**context, "value": item}
    record = {**context, **item}
    return record


def parse_html(path: Path) -> List[Dict[str, Any]]:
    html = path.read_text(encoding="utf-8", errors="replace")
    table_records = html_tables_to_records(html)
    if table_records:
        return table_records
    text = html_to_text(html)
    return [{
        "record_type": "screen_snapshot",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(path, text),
        "content": text,
        "url": first_url(html),
        "path": str(path),
    }]


def parse_pdf(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if audit is not None:
        audit["pdf_file_count"] += 1
    try:
        import pdfplumber  # type: ignore
    except ModuleNotFoundError:
        if audit is not None:
            audit["pdf_parser_available"] = False
            audit["pdf_parse_error_count"] += 1
        return []

    if audit is not None:
        audit["pdf_parser_available"] = True
    records: List[Dict[str, Any]] = []
    text_chunks: List[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            if audit is not None:
                audit["pdf_page_count"] += len(pdf.pages)
            for page_index, page in enumerate(pdf.pages, start=1):
                table_index = 0
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                for table in tables:
                    rows = normalize_pdf_table_rows(table)
                    table_records = rows_to_records(rows, source_sheet=f"pdf_page_{page_index}_table_{table_index + 1}")
                    if table_records:
                        table_index += 1
                        if audit is not None:
                            audit["pdf_table_count"] += 1
                            audit["pdf_table_record_count"] += len(table_records)
                        for row_index, record in enumerate(table_records, start=1):
                            record["_collectorx_raw_ref"] = {
                                "path": str(path),
                                "parser": "pdfplumber",
                                "pdf_page": page_index,
                                "pdf_table": table_index,
                                "pdf_table_row": row_index,
                            }
                        records.extend(table_records)
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                if text.strip():
                    text_chunks.append(text)
    except Exception:
        if audit is not None:
            audit["pdf_parse_error_count"] += 1
        return []

    if records:
        return records

    text = "\n".join(text_chunks).strip()
    text_records = parse_pdf_text_records(text, path=path)
    if text_records:
        if audit is not None:
            audit["pdf_text_record_count"] += len(text_records)
        return text_records
    if text:
        if audit is not None:
            audit["pdf_text_record_count"] += 1
        return [pdf_text_snapshot(path, text)]
    return []


def normalize_pdf_table_rows(table: List[List[Any]]) -> List[List[str]]:
    rows: List[List[str]] = []
    for raw_row in table or []:
        row = ["" if cell is None else re.sub(r"\s+", " ", str(cell)).strip() for cell in raw_row]
        if any(row):
            rows.append(row)
    return rows


def parse_pdf_text_records(text: str, *, path: Path) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    rows: List[List[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "," in stripped or "\t" in stripped or "|" in stripped:
            rows.append([cell.strip() for cell in re.split(r"\t|,|\|", stripped) if cell.strip()])
        else:
            rows.append([cell.strip() for cell in re.split(r"\s{2,}", stripped) if cell.strip()])
    table_records = rows_to_records(rows, source_sheet="pdf_text_table")
    if table_records and any(record_has_wealth_signal(record) for record in table_records):
        for row_index, record in enumerate(table_records, start=1):
            record["_collectorx_raw_ref"] = {
                "path": str(path),
                "parser": "pdfplumber_text",
                "pdf_text_row": row_index,
            }
        return table_records

    kv_record = parse_pdf_key_value_record(text)
    if kv_record and record_has_wealth_signal(kv_record):
        kv_record["source_sheet"] = "pdf_key_value"
        kv_record["_collectorx_raw_ref"] = {"path": str(path), "parser": "pdfplumber_key_value"}
        return [kv_record]
    return []


def parse_pdf_key_value_record(text: str) -> Dict[str, Any]:
    record: Dict[str, Any] = {}
    patterns = {
        "平台": r"(?:平台|渠道|机构|来源|Platform)[:：]\s*([^\n]+)",
        "账户名称": r"(?:账户名称|账户|账号|理财账号|基金账号|Account)[:：]\s*([^\n]+)",
        "类型": r"(?:类型|资产类型|产品类型|Type)[:：]\s*([^\n]+)",
        "产品代码": r"(?:产品代码|基金代码|代码|Code)[:：]\s*([A-Za-z0-9_.-]+)",
        "产品名称": r"(?:产品名称|基金名称|名称|Name)[:：]\s*([^\n]+)",
        "总资产": r"(?:总资产|资产总额|Total Asset)[:：]\s*([0-9,.\-￥¥元]+)",
        "持仓金额": r"(?:持仓金额|持有金额|当前市值|Market Value)[:：]\s*([0-9,.\-￥¥元]+)",
        "持有份额": r"(?:持有份额|份额|Shares)[:：]\s*([0-9,.\-]+)",
        "单位净值": r"(?:单位净值|净值|NAV)[:：]\s*([0-9,.\-]+)",
        "持仓成本": r"(?:持仓成本|成本|Cost)[:：]\s*([0-9,.\-￥¥元]+)",
        "持有收益": r"(?:持有收益|收益|Profit|Pnl)[:：]\s*([0-9,.\-￥¥元]+)",
        "确认金额": r"(?:确认金额|交易金额|申购金额|赎回金额|Amount)[:：]\s*([0-9,.\-￥¥元]+)",
        "交易类型": r"(?:交易类型|操作|业务类型|Side)[:：]\s*([^\n]+)",
        "日期": r"(?:日期|确认日期|更新时间|Date)[:：]\s*([0-9:/.\- 年月日]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            record[key] = match.group(1).strip()
    return record


def record_has_wealth_signal(record: Dict[str, Any]) -> bool:
    keys = set(record)
    if keys & {"平台", "platform", "账户", "账户名称", "account", "产品代码", "基金代码", "product_code", "fund_code", "产品名称", "基金名称", "product_name", "fund_name"}:
        return True
    if keys & {"总资产", "持仓金额", "持有金额", "当前市值", "确认金额", "交易金额", "market_value", "total_asset", "amount"}:
        return True
    text = json.dumps(sanitized(record), ensure_ascii=False).lower()
    return any(token in text for token in ["支付宝", "天天基金", "蛋卷", "且慢", "银行理财", "alipay", "fund", "bank wealth"])


def pdf_text_snapshot(path: Path, text: str) -> Dict[str, Any]:
    return {
        "record_type": "screen_snapshot",
        "title": infer_title(path, text),
        "content": text[:5000],
        "path": str(path),
        "source_sheet": "pdf_text_snapshot",
        "_collectorx_raw_ref": {
            "path": str(path),
            "parser": "pdfplumber_text_snapshot",
            "pdf_text_snapshot": True,
        },
    }


def legacy_text_snapshot(path: Path, text: str) -> Dict[str, Any]:
    return {
        "record_type": "screen_snapshot",
        "title": infer_title(path, text),
        "content": text,
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
        "account": first(record, ACCOUNT_FIELDS),
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
    timestamp = collected_at or now_iso()
    statuses = {
        "china_wealth_authorized_input_missing": "needs_china_wealth_authorized_input",
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "中国基金理财授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": timestamp,
        "collected_at": timestamp,
        "data": {
            "subtype": "collector_gap",
            "gap": reason,
            "status": statuses.get(reason, "needs_china_wealth_authorized_input"),
            "profile_type": reason,
            "candidate_record_count": 0,
            "retained_record_count": 0,
            "filtered_record_count": 0,
            "filter_reason_counts": {},
            "policy_is_user_authorization_scope": True,
            "policy_does_not_assert_investment_relevance": True,
            "business_records_written": False,
            "complete_asset_boundary_claimed": False,
            "payment_or_bank_credentials_collected": False,
            "payment_or_transfer_performed": False,
            "order_or_redemption_performed": False,
            "consumption_flow_claimed": False,
            "read_only": True,
            "message": "No user-authorized fund or wealth-management export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["money", "portfolio", "collection_gap"]},
        "wiki_targets": [DATA_QUALITY_TARGET],
    }


def scope_policy_filtered_all_event(
    *,
    collection_audit: Dict[str, Any],
    collected_at: Optional[str],
) -> Dict[str, Any]:
    timestamp = collected_at or now_iso()
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(
            COLLECTOR,
            "china_wealth_scope_policy_filtered_all",
            json.dumps(collection_audit.get("scope_policy_filter_reason_counts", {}), ensure_ascii=False, sort_keys=True),
        ),
        "collector": COLLECTOR,
        "source": "中国基金理财授权范围策略",
        "owner_scope": "personal",
        "kind": "profile",
        "time": timestamp,
        "collected_at": timestamp,
        "data": {
            "subtype": "collector_gap",
            "gap": "china_wealth_scope_policy_filtered_all",
            "status": "scope_policy_filtered_all",
            "profile_type": "china_wealth_scope_policy_filtered_all",
            "candidate_record_count": collection_audit.get("candidate_record_count", 0),
            "retained_record_count": 0,
            "filtered_record_count": collection_audit.get("scope_policy_filtered_record_count", 0),
            "filter_reason_counts": collection_audit.get("scope_policy_filter_reason_counts", {}),
            "policy_is_user_authorization_scope": True,
            "policy_does_not_assert_investment_relevance": True,
            "business_records_written": False,
            "complete_asset_boundary_claimed": False,
            "read_only": True,
            "message": "输入已读取，但全部被基金/理财授权范围策略排除；未把任何资产、持仓或交易记录写入 Lake。",
        },
        "raw_ref": {"scope_policy_enabled": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["money", "portfolio", "collection_gap"]},
        "wiki_targets": [DATA_QUALITY_TARGET],
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
    return [DATA_QUALITY_TARGET]


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in events)
    collection_audit = collection_audit or {}
    gap_only = bool(events) and set(subtype_counts) == {"collector_gap"}
    no_events = not events
    scope_policy_filtered_all = bool(collection_audit.get("china_wealth_scope_policy_filtered_all"))
    gap_event_count = sum(1 for event in events if (event.get("data") or {}).get("subtype") == "collector_gap")
    usable_events = non_gap_events(events)
    usable_event_count = len(usable_events)
    asset_event_count = usable_event_count
    value_events = [
        event for event in events
        if any((event.get("data") or {}).get(key) is not None for key in ("market_value", "total_asset", "transaction_amount", "pnl"))
    ]
    return {
        "schema": "china_wealth.assets.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "usable_event_count": usable_event_count,
        "asset_event_count": asset_event_count,
        "gap_event_count": gap_event_count,
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
        "currency_summary": currency_summary(events),
        "asset_surface_summary": asset_surface_summary(events),
        "account_boundary_summary": account_boundary_summary(events),
        "asset_boundary_proof": asset_boundary_proof(events, collection_audit=collection_audit),
        "platform_coverage": platform_coverage(platform_counts),
        "evidence_policy": {
            "complete_asset_boundary_claimed": False,
            "real_account_validation": False,
            "personal_authorized_assets_only": True,
            "does_not_place_orders": True,
            "does_not_move_money": True,
            "does_not_collect_consumption_or_payment_flows": True,
            "payment_or_bank_credentials_collected": False,
            "requires_corroboration_with": ["brokerage_accounts", "bank_statements", "fund_platform_exports", "investment_notes"],
        },
        "collection_readiness": {
            "status": china_wealth_readiness_status(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "can_enter_finclaw": usable_event_count > 0,
            "can_enter_china_wealth_lake": usable_event_count > 0,
            "can_enter_data_quality_lake": gap_event_count > 0,
            "can_feed_investor_wiki_evidence": usable_event_count > 0,
            "can_claim_complete_asset_boundary": False,
            "asset_boundary_scope": china_wealth_asset_boundary_scope(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "usable_event_count": usable_event_count,
            "asset_event_count": asset_event_count,
            "gap_event_count": gap_event_count,
            "next_action": china_wealth_next_action(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
        },
        "collection_audit": collection_audit,
    }


def china_wealth_readiness_status(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_filtered_all"
    if gap_only or no_events:
        return "needs_china_wealth_authorized_input"
    return "events_collected"


def china_wealth_asset_boundary_scope(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_excluded_all"
    if gap_only or no_events:
        return "none"
    return "partial_authorized_input"


def china_wealth_next_action(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "放宽用户授权范围，或提供与当前平台/账户/产品/币种策略匹配的基金理财记录。"
    if gap_only or no_events:
        return "提供支付宝/基金/理财授权导出后重跑。"
    return "可进入投资分身蒸馏；后续按平台做只读真机验证后，才能声明完整资产边界。"


def build_evidence(
    events: List[Dict[str, Any]],
    *,
    generated_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = non_gap_events(events)
    gap_event_count = max(len(events) - len(usable_events), 0)
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in usable_events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in usable_events)
    for event in usable_events:
        for target in event.get("wiki_targets", []):
            by_target[target].append(event)
    evidence = {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": len(usable_events),
            "raw_event_count": len(events),
            "gap_event_count": gap_event_count,
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
            "field_coverage": field_coverage(usable_events),
            "asset_value_summary": asset_value_summary(usable_events),
            "currency_summary": currency_summary(usable_events),
            "asset_surface_summary": asset_surface_summary(usable_events),
            "account_boundary_summary": account_boundary_summary(usable_events),
            "asset_boundary_proof": asset_boundary_proof(usable_events, collection_audit=collection_audit),
            "asset_boundary_source": True,
            "complete_asset_boundary_claimed": False,
        },
    }
    return augment_evidence_with_dimensions(evidence, usable_events, INVESTOR_WIKI_SUBDIMENSION_RULES)


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
    usable_events = non_gap_events(events)
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


def non_gap_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [event for event in events if (event.get("data") or {}).get("subtype") != "collector_gap"]


def asset_value_summary(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = defaultdict(lambda: {"market_value": 0.0, "total_asset": 0.0, "transaction_amount": 0.0})
    for event in non_gap_events(events):
        data = event.get("data") or {}
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


def currency_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Counter = Counter()
    value_summary: Dict[str, Dict[str, float]] = defaultdict(lambda: {key: 0.0 for key in VALUE_FIELDS})
    platform_currency: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {key: 0.0 for key in VALUE_FIELDS}))
    for event in non_gap_events(events):
        data = event.get("data") or {}
        currency = str(data.get("currency") or "unknown")
        platform = str(data.get("platform") or "unknown")
        counts[currency] += 1
        for key in VALUE_FIELDS:
            value = data.get(key)
            if isinstance(value, (int, float)):
                value_summary[currency][key] += float(value)
                platform_currency[platform][currency][key] += float(value)
    return {
        "currency_counts": dict(sorted(counts.items())),
        "value_fields_by_currency": {
            currency: compact_float_dict(values)
            for currency, values in sorted(value_summary.items())
            if any(values.values())
        },
        "value_fields_by_platform_currency": {
            platform: {
                currency: compact_float_dict(values)
                for currency, values in sorted(currencies.items())
                if any(values.values())
            }
            for platform, currencies in sorted(platform_currency.items())
            if any(any(values.values()) for values in currencies.values())
        },
    }


def asset_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = non_gap_events(events)
    subtype_counts = Counter((event.get("data") or {}).get("subtype", "unknown") for event in usable_events)
    kind_counts = Counter(event.get("kind", "unknown") for event in usable_events)
    product_type_counts = Counter((event.get("data") or {}).get("product_type", "unknown") for event in usable_events)
    side_counts = Counter((event.get("data") or {}).get("side", "unknown") for event in usable_events if (event.get("data") or {}).get("subtype") in TRADE_SUBTYPES)
    platform_surface: Dict[str, Counter] = defaultdict(Counter)
    transaction_amount_by_side: Dict[str, float] = defaultdict(float)
    products = set()
    for event in usable_events:
        data = event.get("data") or {}
        platform = str(data.get("platform") or "unknown")
        subtype = str(data.get("subtype") or "unknown")
        platform_surface[platform][subtype] += 1
        product_ref = product_identity(data)
        if product_ref:
            products.add(product_ref)
        if subtype in TRADE_SUBTYPES:
            side = str(data.get("side") or "unknown")
            amount = data.get("transaction_amount")
            if isinstance(amount, (int, float)):
                transaction_amount_by_side[side] += float(amount)
    observed = sorted(surface for surface, count in subtype_counts.items() if count > 0)
    return {
        "expected_asset_surfaces": list(EXPECTED_ASSET_SURFACES),
        "observed_asset_surfaces": observed,
        "missing_expected_asset_surfaces": [surface for surface in EXPECTED_ASSET_SURFACES if subtype_counts.get(surface, 0) == 0],
        "kind_counts": dict(sorted(kind_counts.items())),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "product_type_counts": dict(sorted(product_type_counts.items())),
        "distinct_product_count": len(products),
        "holding_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("subtype") in HOLDING_SUBTYPES),
        "transaction_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("subtype") in TRADE_SUBTYPES),
        "asset_snapshot_event_count": subtype_counts.get("asset_snapshot", 0),
        "transaction_side_counts": dict(sorted(side_counts.items())),
        "transaction_amount_by_side": compact_float_dict(transaction_amount_by_side),
        "platform_surface_matrix": {platform: dict(sorted(counter.items())) for platform, counter in sorted(platform_surface.items())},
    }


def account_boundary_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = non_gap_events(events)
    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    unknown_account_events = 0
    for event in usable_events:
        data = event.get("data") or {}
        platform = str(data.get("platform") or "unknown")
        account = str(data.get("account") or "unknown")
        if account == "unknown":
            unknown_account_events += 1
        grouped[(platform, account)].append(event)
    accounts: List[Dict[str, Any]] = []
    for (platform, account), account_events in sorted(grouped.items()):
        product_refs = sorted({product_identity(event.get("data") or {}) for event in account_events if product_identity(event.get("data") or {})})
        accounts.append(
            {
                "platform": platform,
                "account_ref": account,
                "event_count": len(account_events),
                "kind_counts": dict(sorted(Counter(event.get("kind", "unknown") for event in account_events).items())),
                "subtype_counts": dict(sorted(Counter((event.get("data") or {}).get("subtype", "unknown") for event in account_events).items())),
                "asset_surfaces": sorted({str((event.get("data") or {}).get("subtype") or "unknown") for event in account_events}),
                "product_type_counts": dict(sorted(Counter((event.get("data") or {}).get("product_type", "unknown") for event in account_events).items())),
                "currency_counts": dict(sorted(Counter((event.get("data") or {}).get("currency", "unknown") for event in account_events).items())),
                "distinct_product_count": len(product_refs),
                "product_refs_sample": product_refs[:20],
                "product_refs_sample_truncated": len(product_refs) > 20,
                "value_summary": account_value_summary(account_events),
            }
        )
    return {
        "account_boundary_scope": "none" if not usable_events else "partial_authorized_input",
        "observed_account_group_count": len(accounts),
        "observed_named_account_group_count": sum(1 for account in accounts if account["account_ref"] != "unknown"),
        "unknown_account_event_count": unknown_account_events,
        "accounts": accounts,
        "complete_account_boundary_claimed": False,
        "requires_real_account_validation": True,
        "read_only_authorized_source": True,
    }


def asset_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = non_gap_events(events)
    gap_event_count = max(len(events) - len(usable_events), 0)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in usable_events)
    audit = collection_audit or {}
    if not usable_events:
        scope_policy_filtered_all = bool(audit.get("china_wealth_scope_policy_filtered_all"))
        return {
            "proof_scope": "scope_policy_excluded_all" if scope_policy_filtered_all else "none",
            "overall_proof_level": "scope_policy_filtered_all" if scope_policy_filtered_all else "no_authorized_asset_evidence",
            "complete_asset_boundary_claimed": False,
            "requires_real_account_validation": True,
            "asset_event_count": 0,
            "gap_event_count": gap_event_count,
            "can_enter_china_wealth_lake": False,
            "can_enter_data_quality_lake": gap_event_count > 0,
            "can_feed_investor_wiki_evidence": False,
            "requirements": asset_boundary_proof_requirements(),
            "account_proof_level_counts": {},
            "expected_p0_platforms": list(EXPECTED_P0_PLATFORMS),
            "missing_expected_platforms": list(EXPECTED_P0_PLATFORMS),
            "platform_proofs": platform_boundary_proofs({}, platform_counts),
            "account_proofs": [],
            "authorization_scope_boundary": china_wealth_authorization_scope_boundary(audit),
            "missing_global_requirements": ["scope_policy_retained_records"] if scope_policy_filtered_all else ["authorized_asset_input"],
        }

    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for event in usable_events:
        data = event.get("data") or {}
        platform = str(data.get("platform") or "unknown")
        account = str(data.get("account") or "unknown")
        grouped[(platform, account)].append(event)

    account_proofs = [
        build_account_boundary_proof(platform, account, account_events)
        for (platform, account), account_events in sorted(grouped.items())
    ]
    proofs_by_platform: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for proof in account_proofs:
        proofs_by_platform[str(proof["platform"])].append(proof)
    level_counts = Counter(str(proof["proof_level"]) for proof in account_proofs)
    platform_proofs = platform_boundary_proofs(proofs_by_platform, platform_counts)
    missing_global = []
    if all(proof["account_ref"] == "unknown" for proof in account_proofs):
        missing_global.append("named_account_refs")
    if not any(proof["has_asset_snapshot"] for proof in account_proofs):
        missing_global.append("asset_snapshot_surface")
    if not any(proof["has_holding_surface"] for proof in account_proofs):
        missing_global.append("holding_surface")
    if not any(proof["has_transaction_surface"] for proof in account_proofs):
        missing_global.append("transaction_surface")
    if not any(proof["has_value_fields"] for proof in account_proofs):
        missing_global.append("numeric_value_fields")
    if any(proof["platform"] == "unknown" for proof in account_proofs):
        missing_global.append("known_platform")
    missing_platforms = [platform for platform in EXPECTED_P0_PLATFORMS if platform_counts.get(platform, 0) == 0]
    if missing_platforms:
        missing_global.append("expected_platform_coverage")
    return {
        "proof_scope": "partial_authorized_input",
        "overall_proof_level": overall_boundary_proof_level(level_counts),
        "complete_asset_boundary_claimed": False,
        "requires_real_account_validation": True,
        "asset_event_count": len(usable_events),
        "gap_event_count": gap_event_count,
        "can_enter_china_wealth_lake": len(usable_events) > 0,
        "can_enter_data_quality_lake": gap_event_count > 0,
        "can_feed_investor_wiki_evidence": len(usable_events) > 0,
        "requirements": asset_boundary_proof_requirements(),
        "account_proof_level_counts": dict(sorted(level_counts.items())),
        "expected_p0_platforms": list(EXPECTED_P0_PLATFORMS),
        "missing_expected_platforms": missing_platforms,
        "platform_proofs": platform_proofs,
        "account_proofs": account_proofs,
        "authorization_scope_boundary": china_wealth_authorization_scope_boundary(audit),
        "missing_global_requirements": missing_global,
    }


def china_wealth_authorization_scope_boundary(collection_audit: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    audit = collection_audit or {}
    return {
        "policy": audit.get("china_wealth_scope_policy", normalize_china_wealth_scope_policy(None)),
        "candidate_record_count": audit.get("candidate_record_count", audit.get("parsed_record_count", 0)),
        "scope_policy_filtered_record_count": audit.get("scope_policy_filtered_record_count", 0),
        "scope_policy_filter_reason_counts": audit.get("scope_policy_filter_reason_counts", {}),
        "china_wealth_scope_policy_filtered_all": audit.get("china_wealth_scope_policy_filtered_all", False),
    }


def build_account_boundary_proof(platform: str, account: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    subtype_counts = Counter(str((event.get("data") or {}).get("subtype") or "unknown") for event in events)
    value_field_counts = {
        field: sum(1 for event in events if isinstance((event.get("data") or {}).get(field), (int, float)))
        for field in VALUE_FIELDS
    }
    surfaces = sorted(surface for surface, count in subtype_counts.items() if count)
    has_named_account = account != "unknown"
    has_asset_snapshot = subtype_counts.get("asset_snapshot", 0) > 0
    has_holding_surface = any(subtype_counts.get(subtype, 0) > 0 for subtype in HOLDING_SUBTYPES)
    has_transaction_surface = any(subtype_counts.get(subtype, 0) > 0 for subtype in TRADE_SUBTYPES)
    has_value_fields = any(value_field_counts.values())
    has_product_identity = any(product_identity(event.get("data") or {}) for event in events)
    proof_level = account_boundary_proof_level(
        has_named_account=has_named_account,
        has_value_fields=has_value_fields,
        has_asset_snapshot=has_asset_snapshot,
        has_holding_surface=has_holding_surface,
        has_transaction_surface=has_transaction_surface,
    )
    missing_requirements = []
    if platform == "unknown":
        missing_requirements.append("known_platform")
    if not has_named_account:
        missing_requirements.append("named_account_ref")
    if not has_value_fields:
        missing_requirements.append("numeric_value_fields")
    if not has_asset_snapshot:
        missing_requirements.append("asset_snapshot")
    if not has_holding_surface:
        missing_requirements.append("holding_surface")
    if not has_transaction_surface:
        missing_requirements.append("transaction_surface")
    return {
        "platform": platform,
        "account_ref": account,
        "event_count": len(events),
        "proof_level": proof_level,
        "has_named_account": has_named_account,
        "has_asset_snapshot": has_asset_snapshot,
        "has_holding_surface": has_holding_surface,
        "has_transaction_surface": has_transaction_surface,
        "has_value_fields": has_value_fields,
        "has_product_identity": has_product_identity,
        "asset_surfaces": surfaces,
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "value_field_counts": {field: count for field, count in sorted(value_field_counts.items()) if count},
        "missing_requirements": missing_requirements,
        "value_summary": account_value_summary(events),
    }


def account_boundary_proof_level(
    *,
    has_named_account: bool,
    has_value_fields: bool,
    has_asset_snapshot: bool,
    has_holding_surface: bool,
    has_transaction_surface: bool,
) -> str:
    if has_named_account and has_value_fields and has_asset_snapshot and has_holding_surface:
        return "strong_partial_account_boundary"
    if has_named_account and has_value_fields and (has_asset_snapshot or has_holding_surface or has_transaction_surface):
        return "medium_partial_account_boundary"
    if has_value_fields or has_asset_snapshot or has_holding_surface or has_transaction_surface:
        return "weak_partial_account_boundary"
    return "no_account_evidence"


def platform_boundary_proofs(
    proofs_by_platform: Dict[str, List[Dict[str, Any]]],
    platform_counts: Counter,
) -> List[Dict[str, Any]]:
    platforms = list(EXPECTED_P0_PLATFORMS)
    for platform in sorted(platform_counts):
        if platform not in platforms and platform not in {"", "unknown"}:
            platforms.append(str(platform))
    if platform_counts.get("unknown"):
        platforms.append("unknown")

    proofs = []
    for platform in platforms:
        account_proofs = proofs_by_platform.get(platform, [])
        account_level_counts = Counter(str(proof["proof_level"]) for proof in account_proofs)
        surfaces = sorted(
            {
                surface
                for proof in account_proofs
                for surface in proof.get("asset_surfaces", [])
            }
        )
        missing_requirements = []
        if platform_counts.get(platform, 0) == 0:
            missing_requirements.append("platform_input_missing")
        if not any(proof.get("has_named_account") for proof in account_proofs):
            missing_requirements.append("named_account_refs")
        if not any(proof.get("has_value_fields") for proof in account_proofs):
            missing_requirements.append("numeric_value_fields")
        if not any(proof.get("has_asset_snapshot") for proof in account_proofs):
            missing_requirements.append("asset_snapshot")
        if not any(proof.get("has_holding_surface") for proof in account_proofs):
            missing_requirements.append("holding_surface")
        if not any(proof.get("has_transaction_surface") for proof in account_proofs):
            missing_requirements.append("transaction_surface")
        proofs.append(
            {
                "platform": platform,
                "event_count": int(platform_counts.get(platform, 0)),
                "account_group_count": len(account_proofs),
                "named_account_group_count": sum(1 for proof in account_proofs if proof.get("has_named_account")),
                "proof_level": highest_account_proof_level(account_level_counts),
                "account_proof_level_counts": dict(sorted(account_level_counts.items())),
                "asset_surfaces": surfaces,
                "missing_requirements": missing_requirements,
            }
        )
    return proofs


def highest_account_proof_level(level_counts: Counter) -> str:
    for level in ACCOUNT_PROOF_LEVEL_ORDER:
        if level_counts.get(level):
            return level
    return "no_account_evidence"


def overall_boundary_proof_level(level_counts: Counter) -> str:
    highest = highest_account_proof_level(level_counts)
    return {
        "strong_partial_account_boundary": "strong_partial_asset_boundary",
        "medium_partial_account_boundary": "medium_partial_asset_boundary",
        "weak_partial_account_boundary": "weak_partial_asset_boundary",
    }.get(highest, "no_authorized_asset_evidence")


def asset_boundary_proof_requirements() -> List[str]:
    return [
        "known_platform",
        "named_account_ref",
        "asset_snapshot",
        "holding_surface",
        "transaction_surface",
        "numeric_value_fields",
        "real_account_or_readonly_screen_validation_before_complete_boundary_claim",
    ]


def account_value_summary(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = defaultdict(lambda: {key: 0.0 for key in VALUE_FIELDS})
    for event in events:
        data = event.get("data") or {}
        currency = str(data.get("currency") or "unknown")
        for key in VALUE_FIELDS:
            value = data.get(key)
            if isinstance(value, (int, float)):
                summary[currency][key] += float(value)
    return {
        currency: compact_float_dict(values)
        for currency, values in sorted(summary.items())
        if any(values.values())
    }


def product_identity(data: Dict[str, Any]) -> Optional[str]:
    code = data.get("product_code")
    name = data.get("product_name")
    if code and name:
        return f"{code} {name}"
    if code:
        return str(code)
    if name:
        return str(name)
    return None


def compact_float_dict(values: Dict[str, float]) -> Dict[str, float]:
    return {key: round(value, 6) for key, value in sorted(values.items()) if value}


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


def increment_counter(audit: Dict[str, Any], key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_audit(audit: Dict[str, Any]) -> None:
    for key in (
        "extension_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "har_skip_reason_counts",
        "har_endpoint_counts",
        "har_platform_entry_counts",
        "scope_policy_filter_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))


def decode_legacy_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "gbk", "utf-16", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_xml_spreadsheet(text: str) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    records: List[Dict[str, Any]] = []
    worksheet_index = 0
    for worksheet in root.iter():
        if local_name(worksheet.tag) != "Worksheet":
            continue
        worksheet_index += 1
        sheet_name = worksheet.attrib.get("{urn:schemas-microsoft-com:office:spreadsheet}Name") or worksheet.attrib.get("ss:Name") or f"xml_sheet_{worksheet_index}"
        rows: List[List[str]] = []
        for row in worksheet.iter():
            if local_name(row.tag) != "Row":
                continue
            values: List[str] = []
            for cell in row:
                if local_name(cell.tag) != "Cell":
                    continue
                data = next((child for child in cell.iter() if local_name(child.tag) == "Data"), None)
                value = "".join(data.itertext()).strip() if data is not None else "".join(cell.itertext()).strip()
                values.append(value)
            if any(values):
                rows.append(values)
        records.extend(rows_to_records(rows, source_sheet=sheet_name))
    return records


def html_tables_to_records(html: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for table_index, match in enumerate(re.finditer(r"(?is)<table\b.*?</table>", html), start=1):
        table = match.group(0)
        rows: List[List[str]] = []
        for row_match in re.finditer(r"(?is)<tr\b.*?</tr>", table):
            row_html = row_match.group(0)
            values = [
                html_to_text(cell_match.group(1))
                for cell_match in re.finditer(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html)
            ]
            if any(values):
                rows.append(values)
        records.extend(rows_to_records(rows, source_sheet=f"html_table_{table_index}"))
    return records


def rows_to_records(rows: List[List[str]], *, source_sheet: str) -> List[Dict[str, Any]]:
    if not rows:
        return []
    header_index = next((index for index, row in enumerate(rows) if any(cell.strip() for cell in row)), None)
    if header_index is None:
        return []
    headers = [cell.strip() or f"column_{index + 1}" for index, cell in enumerate(rows[header_index])]
    records: List[Dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        record = {
            headers[index]: row[index].strip()
            for index in range(min(len(headers), len(row)))
            if headers[index] and row[index].strip()
        }
        if record:
            record["source_sheet"] = source_sheet
            records.append(record)
    return records


def local_name(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1]


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
