"""Parse user-authorized Xueqiu watchlist exports."""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, Iterator, List, Optional

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


COLLECTOR = "xueqiu-watchlist"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".xlsx",
    ".xlsm",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".markdown",
    ".zip",
}
ARCHIVE_MEMBER_EXTENSIONS = SUPPORTED_EXTENSIONS - {".zip"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
INVESTOR_WIKI_SUBDIMENSION_RULES = {
    "inv-market-view": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist", "investor.capability_circle.attention_universe"],
        "signals": ["雪球自选股能反映用户正在观察的市场机会。"],
        "gaps": ["自选不是持仓，也不能证明用户的市场信念。"],
    },
    "inv-value-preference": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist"],
        "signals": ["自选分组、备注和标签可作为资产偏好侧影。"],
        "gaps": ["偏好原因需要研究笔记、聊天或复盘补充。"],
    },
    "inv-industry-circle": {
        "support_level": "medium",
        "route_targets": ["investor.capability_circle.attention_universe"],
        "signals": ["自选列表中的行业、板块和标的可形成关注宇宙。"],
        "gaps": ["关注宇宙不等于能力圈，需要研究产物和交易复盘验证。"],
    },
    "inv-information-learning-style": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist", "investor.capability_circle.attention_universe"],
        "signals": ["分组和标签能提示用户组织投资信息的方式。"],
        "gaps": ["仍缺少信息筛选、学习和验证过程。"],
    },
    "inv-style-profile": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist"],
        "signals": ["自选池结构可作为风格画像的弱线索。"],
        "gaps": ["自选不等于真实交易风格。"],
    },
    "inv-information-source": {
        "support_level": "weak",
        "route_targets": ["investor.capability_circle.attention_universe"],
        "signals": ["雪球自选源可记录用户的信息入口之一。"],
        "gaps": ["需要与阅读、收藏、讨论和交易时间线交叉验证。"],
    },
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(inputs, collected_at=collected_at, limit=limit)
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
    audit = {
        "source_type": "authorized_local_xueqiu_watchlist_export",
        "input_count": len(input_list),
        "resolved_input_file_count": len(paths),
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "parsed_record_count": 0,
        "filtered_record_count": 0,
        "emitted_event_count": 0,
        "limit": limit,
        "limit_reached": False,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "real_account_adapter_used": False,
        "broker_trade_source": False,
        "path_results": [],
    }
    if not paths:
        _unused, scope_audit = apply_watchlist_scope_policy([], scope_policy)
        attach_watchlist_scope_policy_audit(audit, scope_audit)
        events = [
            gap_event(
                collected_at=collected_at,
                reason="xueqiu_watchlist_authorized_input_missing",
                collection_audit=audit,
            )
        ]
        audit["emitted_event_count"] = len(events)
        finalize_audit(audit)
        return events, audit
    events: List[Dict[str, Any]] = []
    for path in paths:
        path_result = {
            "path": str(path),
            "extension": path.suffix.lower() or "<none>",
            "parsed_record_count": 0,
            "filtered_record_count": 0,
            "emitted_event_count": 0,
            "status": "parsed",
        }
        audit["path_results"].append(path_result)
        increment_counter(audit, "extension_counts", path_result["extension"])
        records = parse_path(path, audit=audit)
        path_result["parsed_record_count"] = len(records)
        audit["parsed_record_count"] += len(records)
        for row, record in enumerate(records, start=1):
            if not watchlist_symbol(record):
                path_result["filtered_record_count"] += 1
                audit["filtered_record_count"] += 1
                continue
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            path_result["emitted_event_count"] += 1
    pre_scope_policy_event_count = len(events)
    events, scope_audit = apply_watchlist_scope_policy(events, scope_policy)
    attach_watchlist_scope_policy_audit(audit, scope_audit)
    audit["pre_scope_policy_event_count"] = pre_scope_policy_event_count
    if limit is not None and len(events) > limit:
        audit["limit_reached"] = True
        events = events[:limit]
    if not events:
        reason = "xueqiu_watchlist_scope_policy_filtered_all" if audit.get("xueqiu_watchlist_scope_policy_filtered_all") else "xueqiu_watchlist_records_empty"
        events = [gap_event(collected_at=collected_at, reason=reason, collection_audit=audit)]
    audit["emitted_event_count"] = len(events)
    finalize_audit(audit)
    return events, audit


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
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path)
    if suffix == ".zip":
        return parse_zip(path, audit=audit)
    return parse_text_watchlist(path)


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-xueqiu-watchlist-") as tmp:
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


def parse_watchlist_csv(file_path: str) -> List[Dict[str, Any]]:
    """Backward-compatible parser used by the legacy CLI and old tests."""
    records = []
    for record in parse_path(Path(file_path)):
        symbol = normalize_symbol(watchlist_symbol(record) or "")
        if not symbol:
            continue
        records.append(
            {
                "source": "xueqiu",
                "code": symbol_code(symbol),
                "symbol": symbol,
                "market": normalize_market(symbol),
                "name": first(record, ["name", "stock_name", "security_name", "名称", "证券名称", "股票名称"]) or "",
                "industry": first(record, ["industry", "sector", "行业", "板块"]) or "",
                "note": first(record, ["note", "memo", "reason", "备注", "关注理由"]) or "",
            }
        )
    return records


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    lines = text.splitlines()
    if not looks_like_header(lines[0]):
        return parse_plain_lines(lines)
    return [{str(key): value for key, value in row.items() if key is not None} for row in csv.DictReader(lines, delimiter=delimiter)]


def looks_like_header(line: str) -> bool:
    normalized = normalize_key(line)
    return any(key in normalized for key in ("code", "symbol", "name", "股票代码", "证券代码", "代码", "名称"))


def parse_plain_lines(lines: Iterable[str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in lines:
        stripped = line.strip()
        symbol = first_symbol_in_text(stripped)
        if symbol:
            records.append({"code": symbol, "source_line": stripped})
    return records


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_records(json.loads(text))
    return [row if isinstance(row, dict) else {"code": row} for row in rows]


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"code": loaded}]
    context = {
        str(key): value
        for key, value in loaded.items()
        if not isinstance(value, (list, dict)) and value not in (None, "")
    }
    collected: List[Any] = []
    for key in ("watchlist", "watchlists", "stocks", "items", "records", "data", "list", "自选股", "关注列表"):
        value = loaded.get(key)
        if isinstance(value, list):
            collected.extend(with_context(item, key, context) for item in value)
        elif isinstance(value, dict):
            collected.extend(with_context(item, key, context) for item in extract_records(value))
    if collected:
        return collected
    return [loaded]


def with_context(item: Any, section: str, context: Dict[str, Any]) -> Any:
    if not isinstance(item, dict):
        return {**context, "code": item, "source_section": section}
    record = {**context, **item}
    record.setdefault("source_section", section)
    return record


def parse_workbook(path: Path) -> List[Dict[str, Any]]:
    if openpyxl is None:
        return []
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
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
                    records.append(record)
    finally:
        workbook.close()
    return records


def parse_text_watchlist(path: Path) -> List[Dict[str, Any]]:
    text = strip_tags(path.read_text(encoding="utf-8", errors="replace"))
    records: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        symbol = first_symbol_in_text(line)
        if not symbol:
            continue
        name = line.replace(symbol, "").strip(" -_,，\t")
        records.append({"code": symbol, "name": name, "source_line": line})
    return records


def first_symbol_in_text(line: str) -> Optional[str]:
    match = re.search(
        r"(?<![A-Z0-9])((?:SH|SZ|BJ)\d{6}|(?:HK)\d{4,5}|\d{6}|\d{5}\.HK|\d{6}\.(?:SH|SZ|BJ))(?![A-Z0-9])",
        line,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    raw_symbol = watchlist_symbol(record) or ""
    symbol = normalize_symbol(raw_symbol)
    followed_at = first(record, ["followed_at", "added_at", "created_at", "time", "date", "加入时间", "关注时间", "日期"])
    event_time = followed_at or collected_at or now_iso()
    group = first(record, ["group", "group_name", "folder", "watchlist", "分组", "自选分组"]) or first(record, ["sheet", "source_section"])
    data = {
        "symbol": symbol,
        "code": symbol_code(symbol),
        "market": normalize_market(first(record, ["market", "exchange", "市场", "交易所"]) or symbol),
        "name": first(record, ["name", "stock_name", "security_name", "名称", "证券名称", "股票名称"]),
        "group": group,
        "industry": first(record, ["industry", "sector", "行业", "板块"]),
        "note": first(record, ["note", "memo", "reason", "备注", "关注理由"]),
        "tags": list_values(record, ["tags", "labels", "标签"]),
        "followed_at": followed_at,
        "source_section": first(record, ["source_section", "sheet"]),
        "raw": sanitized(record),
        "broker_confirmed_trade": False,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {"path": str(path), "row": row, "symbol": symbol}
    if isinstance(record.get("_collectorx_raw_ref"), dict):
        raw_ref.update(record["_collectorx_raw_ref"])
        raw_ref["row"] = row
        raw_ref["symbol"] = symbol
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, symbol, group, followed_at),
        "collector": COLLECTOR,
        "source": "雪球关注列表用户授权导出",
        "owner_scope": "personal",
        "kind": "watchlist",
        "time": event_time,
        "collected_at": collected_at or event_time,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio"]},
        "wiki_targets": [
            "investor.opportunity_watchlist.watchlist",
            "investor.capability_circle.attention_universe",
        ],
    }


def gap_event(
    *,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    messages = {
        "xueqiu_watchlist_authorized_input_missing": "No user-authorized Xueqiu watchlist export was provided.",
        "xueqiu_watchlist_records_empty": "Authorized Xueqiu watchlist input did not contain usable watchlist records.",
        "xueqiu_watchlist_scope_policy_filtered_all": "Xueqiu watchlist records were found, but every candidate was outside the configured authorization scope policy.",
    }
    statuses = {
        "xueqiu_watchlist_authorized_input_missing": "needs_xueqiu_watchlist_authorized_input",
        "xueqiu_watchlist_records_empty": "no_usable_xueqiu_watchlist_records",
        "xueqiu_watchlist_scope_policy_filtered_all": "scope_policy_filtered_all",
    }
    audit = collection_audit or {}
    scope_audit = audit.get("xueqiu_watchlist_scope_policy") or {}
    timestamp = collected_at or now_iso()
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "雪球关注列表授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": timestamp,
        "collected_at": timestamp,
        "data": {
            "gap": reason,
            "status": statuses.get(reason, "no_usable_xueqiu_watchlist_records"),
            "profile_type": reason,
            "message": messages.get(reason, "No user-authorized Xueqiu watchlist evidence was collected."),
            "candidate_event_count": scope_audit.get("candidate_event_count", audit.get("scope_policy_candidate_event_count", 0)),
            "retained_event_count": scope_audit.get("retained_event_count", audit.get("scope_policy_retained_event_count", 0)),
            "filtered_event_count": scope_audit.get("filtered_event_count", audit.get("scope_policy_filtered_event_count", 0)),
            "filter_reason_counts": scope_audit.get("filter_reason_counts", audit.get("scope_policy_filter_reason_counts", {})),
            "policy_is_user_authorization_scope": scope_audit.get("policy_is_user_authorization_scope", True),
            "policy_does_not_assert_investment_relevance": scope_audit.get("policy_does_not_assert_investment_relevance", True),
            "watchlist_is_attention_universe_only": True,
            "broker_trade_fact_claimed": False,
            "holding_fact_claimed": False,
            "order_or_fund_flow_claimed": False,
        },
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "scope_policy_enabled": bool(scope_audit.get("configured", False)),
        },
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio", "collection_gap"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    market_counts = Counter((event.get("data") or {}).get("market", "unknown") for event in events if event["kind"] == "watchlist")
    group_counts = Counter((event.get("data") or {}).get("group", "unknown") for event in events if event["kind"] == "watchlist")
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    watchlist_event_count = sum(1 for event in events if event.get("kind") == "watchlist")
    gap_event_count = sum(1 for event in events if (event.get("data") or {}).get("gap"))
    audit = collection_audit or {}
    if gap_only and audit.get("xueqiu_watchlist_scope_policy_filtered_all"):
        readiness_status = "scope_policy_filtered_all"
        source_collection_scope = "scope_policy_excluded_all"
        next_action = "Review or relax Xueqiu watchlist scope policy, then rerun the collector."
    elif gap_only:
        readiness_status = "needs_xueqiu_watchlist_authorized_input"
        source_collection_scope = "none"
        next_action = "Provide authorized Xueqiu watchlist export."
    else:
        readiness_status = "events_collected"
        source_collection_scope = "partial_authorized_input"
        next_action = "Use as attention-universe evidence; corroborate with Xueqiu activity and broker trades."
    return {
        "schema": "collectorx.xueqiu_watchlist.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "watchlist_event_count": watchlist_event_count,
        "gap_event_count": gap_event_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "market_counts": dict(sorted(market_counts.items())),
        "group_counts": dict(sorted(group_counts.items())),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "field_coverage": build_watchlist_field_coverage(events),
        "xueqiu_watchlist_boundary_proof": build_watchlist_boundary_proof(events, audit),
        "evidence_policy": {
            "xueqiu_watchlist_is_strong_trade_source": False,
            "broker_confirmed_trade_collection": False,
            "evidence_role": "attention_universe_only",
            "requires_corroboration_with": ["broker_trades", "portfolio_holdings", "research_documents", "investment_notes", "reviews"],
        },
        "collection_readiness": {
            "status": readiness_status,
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_xueqiu_watchlist_boundary": False,
            "source_collection_scope": source_collection_scope,
            "next_action": next_action,
        },
        "collection_audit": audit,
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    usable_events = [event for event in events if not (event.get("data") or {}).get("gap")]
    by_target: Dict[str, List[Dict[str, Any]]] = {}
    for event in usable_events:
        for target in event.get("wiki_targets") or []:
            by_target.setdefault(str(target), []).append(event)
    evidence = {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": len(usable_events),
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
        },
        "coverage_summary": {
            "xueqiu_watchlist_is_strong_trade_source": False,
            "watchlist_attention_universe_only": True,
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }
    return augment_evidence_with_dimensions(evidence, usable_events, INVESTOR_WIKI_SUBDIMENSION_RULES)


def build_watchlist_field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    watchlist_events = [event for event in events if event.get("kind") == "watchlist"]
    fields = [
        "symbol",
        "code",
        "market",
        "name",
        "group",
        "industry",
        "note",
        "tags",
        "followed_at",
        "source_section",
    ]
    coverage: Dict[str, Dict[str, int]] = {}
    for field in fields:
        count = sum(1 for event in watchlist_events if (event.get("data") or {}).get(field) not in (None, "", [], {}))
        coverage[field] = {"present": count, "missing": max(len(watchlist_events) - count, 0)}
    return {
        "watchlist_event_count": len(watchlist_events),
        "fields": coverage,
    }


WATCHLIST_SCOPE_POLICY_KEYS = (
    "allow_symbol",
    "deny_symbol",
    "allow_market",
    "deny_market",
    "allow_group",
    "deny_group",
    "allow_industry",
    "deny_industry",
    "allow_tag",
    "deny_tag",
    "allow_keyword",
    "deny_keyword",
)


def split_scope_values(values: Any) -> List[str]:
    if values in (None, ""):
        return []
    raw_items = values if isinstance(values, (list, tuple, set)) else [values]
    out: List[str] = []
    seen = set()
    for item in raw_items:
        if isinstance(item, (list, tuple, set)):
            parts = split_scope_values(item)
        else:
            parts = [part.strip() for part in re.split(r"[,，;；]", str(item)) if part.strip()]
        for part in parts:
            key = part.lower()
            if key and key not in seen:
                seen.add(key)
                out.append(part)
    return out


def normalize_watchlist_scope_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    policy = policy or {}
    return {key: split_scope_values(policy.get(key)) for key in WATCHLIST_SCOPE_POLICY_KEYS}


def watchlist_scope_policy_configured(policy: Dict[str, List[str]]) -> bool:
    return any(policy.get(key) for key in WATCHLIST_SCOPE_POLICY_KEYS)


def apply_watchlist_scope_policy(
    events: List[Dict[str, Any]],
    policy: Optional[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    normalized_policy = normalize_watchlist_scope_policy(policy)
    configured = watchlist_scope_policy_configured(normalized_policy)
    candidates = [event for event in events if event.get("kind") == "watchlist"]
    retained: List[Dict[str, Any]] = []
    reason_counts: Counter = Counter()
    for event in events:
        if event.get("kind") != "watchlist":
            retained.append(event)
            continue
        reasons = watchlist_scope_filter_reasons(event, normalized_policy) if configured else []
        if reasons:
            for reason in reasons:
                reason_counts[reason] += 1
            continue
        retained.append(event)
    audit = {
        "configured": configured,
        "filters": normalized_policy,
        "candidate_event_count": len(candidates),
        "retained_event_count": sum(1 for event in retained if event.get("kind") == "watchlist"),
        "filtered_event_count": len(candidates) - sum(1 for event in retained if event.get("kind") == "watchlist"),
        "filter_reason_counts": dict(sorted(reason_counts.items())),
        "filtered_all": configured and bool(candidates) and not any(event.get("kind") == "watchlist" for event in retained),
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "watchlist_is_attention_universe_only": True,
        "deny_rules_win_over_allow_rules": True,
    }
    return retained, audit


def attach_watchlist_scope_policy_audit(audit: Dict[str, Any], scope_audit: Dict[str, Any]) -> None:
    audit["xueqiu_watchlist_scope_policy"] = scope_audit
    audit["scope_policy_candidate_event_count"] = scope_audit.get("candidate_event_count", 0)
    audit["scope_policy_retained_event_count"] = scope_audit.get("retained_event_count", 0)
    audit["scope_policy_filtered_event_count"] = scope_audit.get("filtered_event_count", 0)
    audit["scope_policy_filter_reason_counts"] = scope_audit.get("filter_reason_counts", {})
    audit["xueqiu_watchlist_scope_policy_filtered_all"] = bool(scope_audit.get("filtered_all"))


def watchlist_scope_filter_reasons(event: Dict[str, Any], policy: Dict[str, List[str]]) -> List[str]:
    data = event.get("data") or {}
    checks = [
        ("symbol", policy.get("allow_symbol", []), policy.get("deny_symbol", []), [data.get("symbol"), data.get("code")], scope_identity_match),
        ("market", policy.get("allow_market", []), policy.get("deny_market", []), [data.get("market")], scope_identity_match),
        ("group", policy.get("allow_group", []), policy.get("deny_group", []), [data.get("group")], scope_text_match),
        ("industry", policy.get("allow_industry", []), policy.get("deny_industry", []), [data.get("industry")], scope_text_match),
        ("tag", policy.get("allow_tag", []), policy.get("deny_tag", []), list(data.get("tags") or []), scope_text_match),
        ("keyword", policy.get("allow_keyword", []), policy.get("deny_keyword", []), [watchlist_scope_search_text(event)], scope_text_match),
    ]
    reasons: List[str] = []
    for name, allow_patterns, deny_patterns, values, matcher in checks:
        if deny_patterns and any_scope_match(values, deny_patterns, matcher):
            reasons.append(f"deny_{name}")
        if allow_patterns and not any_scope_match(values, allow_patterns, matcher):
            reasons.append(f"allow_{name}_mismatch")
    return reasons


def any_scope_match(values: Iterable[Any], patterns: Iterable[str], matcher) -> bool:
    return any(matcher(value, pattern) for value in values if value not in (None, "", [], {}) for pattern in patterns)


def scope_identity_match(value: Any, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    normalized_value_symbol = normalize_symbol(value_norm).lower()
    normalized_pattern_symbol = normalize_symbol(pattern_norm).lower()
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm) or fnmatch.fnmatch(normalized_value_symbol, normalized_pattern_symbol)
    return value_norm == pattern_norm or normalized_value_symbol == normalized_pattern_symbol


def scope_text_match(value: Any, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm)
    return pattern_norm in value_norm


def watchlist_scope_search_text(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    values = [
        data.get("symbol"),
        data.get("code"),
        data.get("market"),
        data.get("name"),
        data.get("group"),
        data.get("industry"),
        data.get("note"),
        data.get("source_section"),
        *(data.get("tags") or []),
        json.dumps(raw, ensure_ascii=False, sort_keys=True) if raw else "",
    ]
    return "\n".join(str(value) for value in values if value not in (None, "", [], {}))


def watchlist_authorization_scope_boundary(collection_audit: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    audit = collection_audit or {}
    scope = audit.get("xueqiu_watchlist_scope_policy") or {}
    return {
        "policy_configured": bool(scope.get("configured")),
        "filters": scope.get("filters", {}),
        "candidate_event_count": scope.get("candidate_event_count", 0),
        "retained_event_count": scope.get("retained_event_count", 0),
        "filtered_event_count": scope.get("filtered_event_count", 0),
        "filter_reason_counts": scope.get("filter_reason_counts", {}),
        "filtered_all": bool(scope.get("filtered_all")),
        "policy_is_user_authorization_scope": scope.get("policy_is_user_authorization_scope", True),
        "policy_does_not_assert_investment_relevance": scope.get("policy_does_not_assert_investment_relevance", True),
    }


def build_watchlist_boundary_proof(events: List[Dict[str, Any]], collection_audit: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    watchlist_events = [event for event in events if event.get("kind") == "watchlist"]
    audit = collection_audit or {}
    scope_policy_filtered_all = bool(audit.get("xueqiu_watchlist_scope_policy_filtered_all"))
    market_counts = Counter((event.get("data") or {}).get("market", "unknown") for event in watchlist_events)
    group_counts = Counter((event.get("data") or {}).get("group", "unknown") for event in watchlist_events)
    if scope_policy_filtered_all:
        proof_scope = "scope_policy_excluded_all"
        proof_level = "scope_policy_filtered_all"
    else:
        proof_scope = "none" if not watchlist_events else "partial_authorized_input"
        proof_level = "no_authorized_watchlist_evidence" if not watchlist_events else "partial_attention_universe_boundary"
    return {
        "proof_scope": proof_scope,
        "proof_level": proof_level,
        "watchlist_event_count": len(watchlist_events),
        "complete_xueqiu_watchlist_boundary_claimed": False,
        "xueqiu_watchlist_is_strong_trade_source": False,
        "broker_confirmed_trade_collection": False,
        "authorization_scope_boundary": watchlist_authorization_scope_boundary(collection_audit),
        "market_counts": dict(sorted(market_counts.items())),
        "group_counts": dict(sorted(group_counts.items())),
        "requires_corroboration_with": ["xueqiu_investor_activity", "broker_trades", "portfolio_holdings", "research_documents", "investment_notes", "reviews"],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_summary(path: Path, manifest: Dict[str, Any]) -> None:
    lines = [
        "# Xueqiu Watchlist Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Xueqiu watchlists are attention-universe evidence, not broker-confirmed holdings or trades.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def watchlist_symbol(record: Dict[str, Any]) -> Optional[str]:
    stock = dict_child(record, "stock")
    return first(record, ["symbol", "code", "stock_symbol", "stockCode", "股票代码", "证券代码", "代码"]) or first(stock, ["symbol", "code"])


def dict_child(record: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


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


def list_values(record: Dict[str, Any], keys: Iterable[str]) -> List[str]:
    for key in keys:
        value = first_raw(record, key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,，、;；|\n]+", value) if item.strip()]
        if isinstance(value, list):
            return [str(item.get("name") if isinstance(item, dict) else item) for item in value if str(item)]
    return []


def first_raw(record: Dict[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    normalized_key = normalize_key(key)
    for candidate, value in record.items():
        if normalize_key(candidate) == normalized_key:
            return value
    return None


def normalize_symbol(value: str) -> str:
    text = str(value).strip().upper()
    text = text.strip("$")
    text = re.sub(r"\s+", "", text)
    suffix_match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", text)
    if suffix_match:
        return f"{suffix_match.group(2)}{suffix_match.group(1)}"
    hk_suffix = re.fullmatch(r"(\d{4,5})\.HK", text)
    if hk_suffix:
        return f"HK{hk_suffix.group(1).zfill(5)}"
    if re.fullmatch(r"(SH|SZ|BJ)\d{6}", text):
        return text
    if re.fullmatch(r"HK\d{4,5}", text):
        return "HK" + text[2:].zfill(5)
    if text.isdigit() and len(text) == 6:
        market = normalize_market(text)
        return f"{market}{text}" if market in {"SH", "SZ", "BJ"} else text
    if text.isdigit() and len(text) == 5 and text.startswith("0"):
        return f"HK{text}"
    return text


def symbol_code(symbol: str) -> str:
    text = str(symbol)
    if re.fullmatch(r"(SH|SZ|BJ)\d{6}", text):
        return text[2:]
    if re.fullmatch(r"HK\d{5}", text):
        return text[2:]
    return text


def normalize_market(value: Optional[str]) -> str:
    text = str(value or "").upper()
    if text.startswith("SH") or text.endswith(".SH") or "沪" in text:
        return "SH"
    if text.startswith("SZ") or text.endswith(".SZ") or "深" in text:
        return "SZ"
    if text.startswith("BJ") or text.endswith(".BJ") or "北" in text:
        return "BJ"
    if text.startswith("HK") or text.endswith(".HK") or "港" in text:
        return "HK"
    if text.isdigit() and len(text) == 6:
        if text.startswith(("6", "9")):
            return "SH"
        if text.startswith(("0", "2", "3")):
            return "SZ"
        if text.startswith(("4", "8")):
            return "BJ"
    if text.isdigit() and len(text) == 5 and text.startswith("0"):
        return "HK"
    return "unknown"


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).startswith("_collectorx_"):
                continue
            if any(fragment in str(key).lower() for fragment in SECRET_KEY_FRAGMENTS):
                continue
            clean[str(key)] = sanitized(item)
        return clean
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:4000]
    return value


def increment_counter(audit: Dict[str, Any], key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_audit(audit: Dict[str, Any]) -> None:
    for key in (
        "extension_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "scope_policy_filter_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))


def strip_tags(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "\n", value))


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
