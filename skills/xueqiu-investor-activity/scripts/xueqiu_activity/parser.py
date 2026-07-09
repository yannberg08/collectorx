"""Parse user-authorized Xueqiu exports into CollectorX events."""

from __future__ import annotations

import base64
import binascii
import csv
import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlparse, urlunparse

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


COLLECTOR = "xueqiu-investor-activity"
PREFLIGHT_SCHEMA = "collectorx.xueqiu_activity_preflight.v1"
CN_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc
SUPPORTED_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".ndjson",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xlsm",
    ".txt",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".har",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".zip",
}
ARCHIVE_MEMBER_EXTENSIONS = SUPPORTED_EXTENSIONS - {".zip"}
BROWSER_HISTORY_NAMES = {"History", "History.db"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
LOCAL_PATH_KEYS = {
    "archive",
    "archive_path",
    "file",
    "file_name",
    "file_path",
    "filename",
    "filepath",
    "local_file",
    "local_path",
    "path",
    "source_file",
    "source_path",
}
RAW_REF_PATH_KEYS = {"archive", "path"}
CN_MOBILE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
INLINE_SECRET_RE = re.compile(r"(?i)\b(cookie|token|authorization|session|password|passwd|xq_[a-z_]*token)=([^\s&;,'\"<>]+)")
EXPECTED_ACTIVITY_TYPES = ("watchlist", "follow_user", "follow_portfolio", "portfolio_activity", "comment", "favorite", "post", "saved_page")
ACTIVITY_REQUIRED_FIELDS = {
    "watchlist": ("symbols", "name"),
    "follow_user": ("author", "author_id", "target_user", "url"),
    "follow_portfolio": ("portfolio_symbol", "portfolio_name", "url"),
    "portfolio_activity": ("portfolio_symbol", "portfolio_name", "portfolio_changes"),
    "comment": ("content_preview", "author", "url"),
    "favorite": ("content_preview", "url"),
    "post": ("content_preview", "url"),
    "saved_page": ("content_preview", "url"),
}
INVESTOR_WIKI_SUBDIMENSION_RULES = {
    "inv-market-view": {
        "support_level": "weak",
        "route_targets": ["investor.information_sources.news_consumption", "investor.opportunity_watchlist.watchlist"],
        "signals": ["雪球关注、自选、收藏和发帖可作为市场关注面的弱证据。"],
        "gaps": ["雪球不是券商强交易事实，市场观仍需聊天、笔记或复盘解释。"],
    },
    "inv-value-preference": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist", "investor.risk_portfolio.portfolio_constraints"],
        "signals": ["自选、关注组合和组合活动可侧面反映偏好的资产或主题。"],
        "gaps": ["关注不等于真实持仓或价值信念，需要券商/基金账户和研究理由交叉验证。"],
    },
    "inv-industry-circle": {
        "support_level": "medium",
        "route_targets": ["investor.capability_circle.attention_universe", "investor.opportunity_watchlist.watchlist"],
        "signals": ["雪球自选和关注对象可形成用户注意力宇宙。"],
        "gaps": ["注意力宇宙不等于能力圈，需要研究文档、笔记和复盘验证。"],
    },
    "inv-information-learning-style": {
        "support_level": "medium",
        "route_targets": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "signals": ["收藏、保存页、关注用户和组合能描述信息输入习惯。"],
        "gaps": ["仍缺少用户如何筛选、验证和反思信息的过程证据。"],
    },
    "inv-style-profile": {
        "support_level": "weak",
        "route_targets": ["investor.risk_portfolio.portfolio_constraints", "investor.decision_framework.strategy_rules"],
        "signals": ["关注组合和组合活动可以作为风格侧影。"],
        "gaps": ["雪球组合不等于真实券商持仓，不能单独形成投资风格结论。"],
    },
    "inv-emotion-pattern": {
        "support_level": "weak",
        "route_targets": ["investor.behavior.emotion_pattern", "investor.network_collaboration.discussions"],
        "signals": ["评论和发帖文本可能包含情绪表达线索。"],
        "gaps": ["短文本容易误判，需要交易前后语境和多源交叉验证。"],
    },
    "inv-review-record": {
        "support_level": "medium",
        "route_targets": ["investor.record_review.review_record"],
        "signals": ["个人发帖或保存页中的复盘内容可进入复盘证据池。"],
        "gaps": ["需要区分原创复盘和转发/收藏材料。"],
    },
    "inv-rules-library": {
        "support_level": "weak",
        "route_targets": ["investor.decision_framework.strategy_rules"],
        "signals": ["组合活动和发帖中的规则表达可作为规则库候选。"],
        "gaps": ["需验证是否为用户自己的稳定规则，而非临时观点或他人策略。"],
    },
    "inv-information-source": {
        "support_level": "medium",
        "route_targets": ["investor.information_sources.news_consumption"],
        "signals": ["关注用户、收藏和阅读痕迹可明确用户的信息来源。"],
        "gaps": ["信息来源影响力需要和真实决策时间线回测。"],
    },
    "inv-consultation-network": {
        "support_level": "medium",
        "route_targets": ["investor.network_collaboration.discussions"],
        "signals": ["关注用户、评论和讨论可以形成投资人际网络线索。"],
        "gaps": ["平台互动不等于真实咨询关系，需要微信/会议/邮件等强关系证据。"],
    },
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def source_id_for_path(path: Path) -> str:
    try:
        normalized = str(path.expanduser().resolve())
    except OSError:
        normalized = str(path)
    digest = hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"xqsrc_{digest}"


def source_id_for_text(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"xqsrc_{digest}"


def public_raw_ref(raw_ref: Dict[str, Any], *, source_path: Path) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {
        "source_id": source_id_for_path(source_path),
        "source_extension": extension_label(source_path),
    }
    for key, value in raw_ref.items():
        normalized = normalize_audit_key(key)
        if normalized in RAW_REF_PATH_KEYS:
            continue
        cleaned[str(key)] = sanitized(value)
    return cleaned


def file_size_bucket(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "unknown"
    if size == 0:
        return "empty"
    if size < 100 * 1024:
        return "lt_100kb"
    if size < 10 * 1024 * 1024:
        return "100kb_to_10mb"
    return "gt_10mb"


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
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
        "source_type": "authorized_local_xueqiu_export",
        "input_count": len(input_list),
        "resolved_input_file_count": len(paths),
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "parsed_record_count": 0,
        "emitted_event_count": 0,
        "pagination_marker_count": 0,
        "pagination_marker_field_counts": {},
        "browser_network_export_supported": True,
        "authorized_browser_network_export_used": False,
        "browser_network_export_file_count": 0,
        "har_entry_count": 0,
        "har_xueqiu_entry_count": 0,
        "har_response_record_count": 0,
        "har_skipped_entry_count": 0,
        "har_skip_reason_counts": {},
        "har_endpoint_counts": {},
        "har_secret_material_stripped_count": 0,
        "har_query_string_stripped_count": 0,
        "har_secret_material_policy": "request_headers_cookies_authorization_query_strings_are_never_written_to_events_or_manifest",
        "browser_history_supported": True,
        "browser_history_domain_filtering": True,
        "browser_history_input_count": 0,
        "browser_history_event_count": 0,
        "browser_history_source_apps": [],
        "browser_history_supported_names": sorted(BROWSER_HISTORY_NAMES),
        "limit": limit,
        "limit_reached": False,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "real_account_adapter_used": False,
        "broker_trade_source": False,
        "path_results": [],
    }
    if not paths:
        _unused, scope_audit = apply_activity_scope_policy([], scope_policy)
        attach_activity_scope_policy_audit(audit, scope_audit)
        events = [
            gap_event(
                collected_at=collected_at,
                reason="xueqiu_authorized_input_missing",
                collection_audit=audit,
            )
        ]
        audit["emitted_event_count"] = len(events)
        finalize_audit(audit)
        return events, audit
    events: List[Dict[str, Any]] = []
    for path in paths:
        path_result = {
            "source_id": source_id_for_path(path),
            "extension": extension_label(path),
            "parser": parser_name_for_path(path),
            "parsed_record_count": 0,
            "emitted_event_count": 0,
            "status": "parsed",
        }
        audit["path_results"].append(path_result)
        increment_counter(audit, "extension_counts", path_result["extension"])
        records = parse_path(path, audit=audit)
        path_result["parsed_record_count"] = len(records)
        audit["parsed_record_count"] += len(records)
        for row, record in enumerate(records, start=1):
            record_pagination_markers(record, audit)
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            path_result["emitted_event_count"] += 1
            if (record.get("_collectorx_raw_ref") or {}).get("parser") == "browser_history":
                audit["browser_history_event_count"] += 1
    pre_scope_policy_event_count = len(events)
    events, scope_audit = apply_activity_scope_policy(events, scope_policy)
    attach_activity_scope_policy_audit(audit, scope_audit)
    audit["pre_scope_policy_event_count"] = pre_scope_policy_event_count
    audit["browser_history_event_count"] = sum(
        1 for event in events if (event.get("data") or {}).get("source_surface") == "browser_history"
    )
    if limit is not None and len(events) > limit:
        audit["limit_reached"] = True
        events = events[:limit]
        audit["browser_history_event_count"] = sum(
            1 for event in events if (event.get("data") or {}).get("source_surface") == "browser_history"
        )
    if not events:
        reason = "xueqiu_scope_policy_filtered_all" if audit.get("xueqiu_activity_scope_policy_filtered_all") else "xueqiu_records_empty"
        events = [gap_event(collected_at=collected_at, reason=reason, collection_audit=audit)]
    audit["emitted_event_count"] = len(events)
    finalize_audit(audit)
    return events, audit


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and is_supported_input_path(child):
                    yield child
        elif path.is_file() and is_supported_input_path(path):
            yield path


def is_supported_input_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS or path.name in BROWSER_HISTORY_NAMES


def extension_label(path: Path) -> str:
    if path.name in BROWSER_HISTORY_NAMES:
        return "<browser_history>"
    return path.suffix.lower() or "<none>"


def parser_name_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if path.name in BROWSER_HISTORY_NAMES or suffix in {".sqlite", ".sqlite3", ".db"}:
        return "browser_history"
    if suffix == ".har":
        return "har"
    if suffix == ".zip":
        return "zip"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
    if suffix in {".csv", ".tsv"}:
        return "table"
    if suffix in {".xlsx", ".xlsm"}:
        return "openpyxl"
    if suffix in {".html", ".htm"}:
        return "html"
    return "text"


def parse_path(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if path.name in BROWSER_HISTORY_NAMES or suffix in {".sqlite", ".sqlite3", ".db"}:
        return parse_browser_history(path, audit=audit)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path)
    if suffix in {".html", ".htm"}:
        return [parse_html(path)]
    if suffix == ".har":
        return parse_har(path, audit=audit)
    if suffix == ".zip":
        return parse_zip(path, audit=audit)
    return [parse_text(path)]


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-xueqiu-activity-") as tmp:
        tmp_root = Path(tmp)
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(member_name)
            member_fs_path = Path(member_name)
            suffix = member_fs_path.suffix.lower()
            extension = extension_label(member_fs_path)
            if audit is not None:
                audit["archive_member_count"] += 1
                increment_counter(audit, "archive_member_extension_counts", extension)
            if not is_safe_archive_member(member_path) or (suffix not in ARCHIVE_MEMBER_EXTENSIONS and member_fs_path.name not in BROWSER_HISTORY_NAMES):
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", extension)
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
        url = str(request.get("url") or "")
        parsed_url = urlparse(url)
        if not is_xueqiu_url(parsed_url):
            record_har_skip(audit, "non_xueqiu_url")
            continue
        if audit is not None:
            audit["har_xueqiu_entry_count"] += 1
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
                "har_response",
                {
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
            }
            records.append(record)
    return records


def is_xueqiu_url(parsed_url: Any) -> bool:
    host = str(getattr(parsed_url, "netloc", "") or "").lower()
    return host == "xueqiu.com" or host.endswith(".xueqiu.com")


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


def parse_browser_history(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if audit is not None:
        audit["browser_history_input_count"] += 1
    uri = f"{path.expanduser().resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return []
    try:
        names = table_names(conn)
        try:
            if {"urls", "visits"}.issubset(names):
                records = parse_chromium_history(conn, path)
            elif {"history_items", "history_visits"}.issubset(names):
                records = parse_safari_history(conn, path)
            else:
                records = []
        except sqlite3.Error:
            records = []
    finally:
        conn.close()
    if audit is not None:
        source_apps = sorted({str(record.get("source_app")) for record in records if record.get("source_app")})
        audit["browser_history_source_apps"] = sorted(set(audit.get("browser_history_source_apps") or []).union(source_apps))
    return records


def build_preflight_diagnosis(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    scan_browser_profiles: bool = False,
    browser_profile_roots: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    input_list = list(inputs)
    source_probe = probe_authorized_inputs(input_list)
    browser_profile_probe = probe_browser_profile_candidates(
        enabled=scan_browser_profiles,
        roots=[Path(raw).expanduser() for raw in (browser_profile_roots or [])],
    )
    candidate_kinds = Counter(candidate["source_kind"] for candidate in source_probe["candidates"])
    har_candidates = [candidate for candidate in source_probe["candidates"] if candidate["source_kind"] == "authorized_har"]
    browser_history_candidates = [
        candidate for candidate in source_probe["candidates"] if candidate["source_kind"] == "authorized_browser_history_copy"
    ]
    local_export_candidates = [
        candidate
        for candidate in source_probe["candidates"]
        if candidate["source_kind"] in {"authorized_export_file", "authorized_saved_page", "authorized_zip_package"}
    ]
    can_attempt_har_collect = any(candidate.get("can_attempt_collect") for candidate in har_candidates)
    can_attempt_browser_history_collect = any(candidate.get("can_attempt_collect") for candidate in browser_history_candidates)
    can_attempt_local_export_collect = any(candidate.get("can_attempt_collect") for candidate in local_export_candidates)
    can_attempt_collect = can_attempt_har_collect or can_attempt_browser_history_collect or can_attempt_local_export_collect
    can_prepare_authorized_browser_history_copy = bool(browser_profile_probe.get("candidate_count"))
    if can_attempt_collect:
        status = "authorized_sources_detected"
        next_action = "Run collect with the diagnosed user-authorized Xueqiu source files."
    elif can_prepare_authorized_browser_history_copy:
        status = "needs_authorized_browser_history_copy"
        next_action = "Copy the browser History/History.db file to an authorized working folder, then rerun diagnose or collect with --input."
    else:
        status = "needs_authorized_xueqiu_source"
        next_action = "Provide a Xueqiu export, saved page, HAR, ZIP package, or copied browser history file before collection."
    return {
        "schema": PREFLIGHT_SCHEMA,
        "collector": COLLECTOR,
        "diagnosed_at": collected_at or now_iso(),
        "diagnostic_scope": {
            "activity_events_collected": False,
            "har_response_payloads_parsed": False,
            "browser_history_urls_emitted": False,
            "browser_history_titles_emitted": False,
            "cookies_or_tokens_emitted": False,
            "local_paths_emitted": False,
            "phone_numbers_emitted": False,
            "public_news_collected_as_personal_fact": False,
            "direct_browser_profile_databases_read": False,
            "real_account_network_adapter_used": False,
        },
        "authorized_source_policy": {
            "official_or_user_export_files": "supported_when_user_provides_files; parsed as personal activity evidence only",
            "authorized_web_har": "supported_for_user_exported_logged-in HAR; request headers, cookies, authorization, and query strings are never emitted",
            "browser_history_copy": "supported_only_from user-copied Chromium/Safari history files; xueqiu.com domain-filtered",
            "browser_cache": "not_collected; cache files are not treated as personal investment facts",
            "local_saved_pages": "supported for user-saved pages or markdown/text snippets that mention Xueqiu",
            "official_realtime_account_api": "not_implemented; no direct real-account adapter is claimed",
            "public_news_or_market_timeline": "not_collected_as_personal_fact",
            "broker_trade_records": "not_collected_by_xueqiu; use broker collectors for holdings, orders, executions, or fund flows",
        },
        "source_probe": {
            **source_probe,
            "candidate_kind_counts": dict(sorted(candidate_kinds.items())),
            "har_candidate_count": len(har_candidates),
            "browser_history_candidate_count": len(browser_history_candidates),
            "local_export_candidate_count": len(local_export_candidates),
            "har_xueqiu_entry_count": sum(int(candidate.get("har_xueqiu_entry_count") or 0) for candidate in har_candidates),
            "browser_history_xueqiu_visit_count": sum(
                int(candidate.get("browser_history_xueqiu_visit_count") or 0)
                for candidate in browser_history_candidates
            ),
        },
        "browser_profile_probe": browser_profile_probe,
        "collection_readiness": {
            "status": status,
            "can_attempt_collect": can_attempt_collect,
            "can_attempt_har_collect": can_attempt_har_collect,
            "can_attempt_browser_history_collect": can_attempt_browser_history_collect,
            "can_attempt_local_export_collect": can_attempt_local_export_collect,
            "can_prepare_authorized_browser_history_copy": can_prepare_authorized_browser_history_copy,
            "can_attempt_real_account_network_collect": False,
            "can_claim_real_account_validation": False,
            "can_claim_complete_xueqiu_activity_boundary": False,
            "can_claim_broker_trade_collection": False,
            "can_feed_investor_wiki_evidence": False,
            "requires_collect_run_for_events": True,
            "next_action": next_action,
        },
    }


def probe_authorized_inputs(inputs: Iterable[str]) -> Dict[str, Any]:
    counters: Dict[str, Any] = {
        "input_count": 0,
        "directory_input_count": 0,
        "file_input_count": 0,
        "missing_input_count": 0,
        "resolved_input_file_count": 0,
        "supported_input_file_count": 0,
        "unsupported_input_file_count": 0,
        "extension_counts": {},
        "candidates": [],
    }
    for raw in inputs:
        counters["input_count"] += 1
        path = Path(raw).expanduser()
        if path.is_dir():
            counters["directory_input_count"] += 1
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    probe_input_file(child, counters)
        elif path.is_file():
            counters["file_input_count"] += 1
            probe_input_file(path, counters)
        else:
            counters["missing_input_count"] += 1
    counters["extension_counts"] = dict(sorted((counters.get("extension_counts") or {}).items()))
    return counters


def probe_input_file(path: Path, counters: Dict[str, Any]) -> None:
    counters["resolved_input_file_count"] += 1
    if not is_supported_input_path(path):
        counters["unsupported_input_file_count"] += 1
        return
    counters["supported_input_file_count"] += 1
    increment_counter(counters, "extension_counts", extension_label(path))
    counters["candidates"].append(probe_authorized_source(path))


def probe_authorized_source(path: Path) -> Dict[str, Any]:
    parser = parser_name_for_path(path)
    source_kind = preflight_source_kind(path, parser)
    probe: Dict[str, Any] = {
        "source_id": source_id_for_path(path),
        "source_kind": source_kind,
        "parser": parser,
        "extension": extension_label(path),
        "size_bucket": file_size_bucket(path),
        "readable": os.access(path, os.R_OK),
        "supported": True,
        "can_attempt_collect": False,
    }
    if not probe["readable"]:
        probe["status"] = "not_readable"
        return probe
    if parser == "har":
        probe.update(probe_har_for_preflight(path))
    elif parser == "browser_history":
        probe.update(probe_browser_history_for_preflight(path))
    elif parser == "zip":
        probe.update(probe_zip_for_preflight(path))
    else:
        probe["status"] = "supported_local_source"
        probe["can_attempt_collect"] = probe["size_bucket"] != "empty"
    return probe


def preflight_source_kind(path: Path, parser: str) -> str:
    if parser == "har":
        return "authorized_har"
    if parser == "browser_history":
        return "authorized_browser_history_copy"
    if parser == "zip":
        return "authorized_zip_package"
    if path.suffix.lower() in {".html", ".htm", ".txt", ".md", ".markdown"}:
        return "authorized_saved_page"
    return "authorized_export_file"


def probe_har_for_preflight(path: Path) -> Dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "har_unreadable_or_invalid_json",
            "can_attempt_collect": False,
            "har_entry_count": 0,
            "har_xueqiu_entry_count": 0,
        }
    entries = loaded.get("log", {}).get("entries", []) if isinstance(loaded, dict) else []
    endpoint_counts: Counter = Counter()
    secret_count = 0
    query_string_count = 0
    xueqiu_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        secret_count += har_secret_material_count(entry)
        request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
        url = str(request.get("url") or "")
        parsed_url = urlparse(url)
        if not is_xueqiu_url(parsed_url):
            continue
        xueqiu_count += 1
        if parsed_url.query:
            query_string_count += 1
        endpoint_counts[har_endpoint(parsed_url)] += 1
    return {
        "status": "har_has_xueqiu_entries" if xueqiu_count else "har_has_no_xueqiu_entries",
        "can_attempt_collect": xueqiu_count > 0,
        "har_entry_count": len(entries),
        "har_xueqiu_entry_count": xueqiu_count,
        "har_endpoint_counts": dict(sorted(endpoint_counts.items())),
        "har_secret_material_observed_count": secret_count,
        "har_query_string_observed_count": query_string_count,
        "har_response_payloads_parsed": False,
    }


def probe_browser_history_for_preflight(path: Path) -> Dict[str, Any]:
    uri = f"{path.expanduser().resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return {
            "status": "browser_history_unreadable",
            "can_attempt_collect": False,
            "browser_history_schema_supported": False,
            "browser_history_xueqiu_visit_count": 0,
        }
    try:
        names = table_names(conn)
        if {"urls", "visits"}.issubset(names):
            source_app = "chromium_history"
            count = browser_history_xueqiu_count(conn, source_app)
        elif {"history_items", "history_visits"}.issubset(names):
            source_app = "safari_history"
            count = browser_history_xueqiu_count(conn, source_app)
        else:
            source_app = "unknown"
            count = 0
    except sqlite3.Error:
        source_app = "unknown"
        count = 0
        schema_supported = False
    else:
        schema_supported = source_app != "unknown"
    finally:
        conn.close()
    return {
        "status": "browser_history_schema_supported" if schema_supported else "browser_history_schema_unsupported",
        "can_attempt_collect": schema_supported,
        "browser_history_schema_supported": schema_supported,
        "browser_history_source_app": source_app,
        "browser_history_xueqiu_visit_count": count,
        "browser_history_urls_emitted": False,
        "browser_history_titles_emitted": False,
    }


def browser_history_xueqiu_count(conn: sqlite3.Connection, source_app: str) -> int:
    if source_app == "chromium_history":
        query = f"""
            SELECT COUNT(*) AS count
            FROM urls
            JOIN visits ON visits.url = urls.id
            WHERE {xueqiu_domain_where('urls.url')}
        """
    else:
        query = f"""
            SELECT COUNT(*) AS count
            FROM history_items
            JOIN history_visits ON history_visits.history_item = history_items.id
            WHERE {xueqiu_domain_where('history_items.url')}
        """
    row = conn.execute(query).fetchone()
    return int(row["count"] or 0) if row is not None else 0


def probe_zip_for_preflight(path: Path) -> Dict[str, Any]:
    member_count = 0
    supported_member_count = 0
    skipped_member_count = 0
    member_extension_counts: Counter = Counter()
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member_count += 1
                member_name = info.filename.replace("\\", "/")
                member_path = PurePosixPath(member_name)
                member_fs_path = Path(member_name)
                extension = extension_label(member_fs_path)
                member_extension_counts[extension] += 1
                suffix = member_fs_path.suffix.lower()
                if is_safe_archive_member(member_path) and (suffix in ARCHIVE_MEMBER_EXTENSIONS or member_fs_path.name in BROWSER_HISTORY_NAMES):
                    supported_member_count += 1
                else:
                    skipped_member_count += 1
    except (OSError, zipfile.BadZipFile):
        return {
            "status": "zip_unreadable",
            "can_attempt_collect": False,
            "archive_member_count": 0,
            "supported_archive_member_count": 0,
        }
    return {
        "status": "zip_has_supported_members" if supported_member_count else "zip_has_no_supported_members",
        "can_attempt_collect": supported_member_count > 0,
        "archive_member_count": member_count,
        "supported_archive_member_count": supported_member_count,
        "skipped_archive_member_count": skipped_member_count,
        "archive_member_extension_counts": dict(sorted(member_extension_counts.items())),
    }


def probe_browser_profile_candidates(*, enabled: bool, roots: List[Path]) -> Dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "candidate_count": 0,
            "copy_required_before_collect": True,
            "direct_profile_databases_read": False,
            "source_app_counts": {},
        }
    candidates = discover_browser_history_candidates(roots)
    counts = Counter(browser_history_source_app_for_path(path) for path in candidates)
    return {
        "enabled": True,
        "candidate_count": len(candidates),
        "copy_required_before_collect": True,
        "direct_profile_databases_read": False,
        "source_app_counts": dict(sorted(counts.items())),
    }


def discover_browser_history_candidates(roots: List[Path]) -> List[Path]:
    candidates: List[Path] = []
    scan_roots = roots or default_browser_profile_roots()
    for root in scan_roots:
        try:
            if root.is_file() and root.name in BROWSER_HISTORY_NAMES:
                candidates.append(root)
                continue
            if not root.is_dir():
                continue
            for child in root.rglob("*"):
                if child.is_file() and child.name in BROWSER_HISTORY_NAMES:
                    candidates.append(child)
        except OSError:
            continue
    return sorted(set(candidates), key=lambda item: str(item))


def default_browser_profile_roots() -> List[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [
            home / "Library" / "Application Support" / "Google" / "Chrome",
            home / "Library" / "Application Support" / "Chromium",
            home / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser",
            home / "Library" / "Application Support" / "Microsoft Edge",
            home / "Library" / "Safari",
        ]
    if sys.platform.startswith("win"):
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        return [
            local_app_data / "Google" / "Chrome" / "User Data",
            local_app_data / "Microsoft" / "Edge" / "User Data",
            local_app_data / "BraveSoftware" / "Brave-Browser" / "User Data",
        ]
    return [
        home / ".config" / "google-chrome",
        home / ".config" / "chromium",
        home / ".config" / "BraveSoftware" / "Brave-Browser",
        home / ".config" / "microsoft-edge",
    ]


def browser_history_source_app_for_path(path: Path) -> str:
    return "safari_history" if path.name == "History.db" else "chromium_history"


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row["name"]) for row in rows}


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def parse_chromium_history(conn: sqlite3.Connection, path: Path) -> List[Dict[str, Any]]:
    query = f"""
        SELECT
          urls.id AS url_id,
          urls.url AS url,
          urls.title AS title,
          urls.visit_count AS visit_count,
          urls.typed_count AS typed_count,
          visits.id AS visit_id,
          visits.visit_time AS visit_time,
          visits.transition AS transition
        FROM urls
        JOIN visits ON visits.url = urls.id
        WHERE {xueqiu_domain_where('urls.url')}
        ORDER BY visits.visit_time ASC
    """
    records = []
    for row in conn.execute(query):
        records.append(
            browser_history_record(
                source_app="chromium_history",
                path=path,
                url=row["url"],
                title=row["title"],
                visit_id=row["visit_id"],
                url_id=row["url_id"],
                event_time=chromium_time_to_iso(row["visit_time"]),
                visit_count=row["visit_count"],
                typed_count=row["typed_count"],
                transition=row["transition"],
            )
        )
    return records


def parse_safari_history(conn: sqlite3.Connection, path: Path) -> List[Dict[str, Any]]:
    visit_columns = table_columns(conn, "history_visits")
    load_successful_select = (
        "history_visits.load_successful AS load_successful"
        if "load_successful" in visit_columns
        else "NULL AS load_successful"
    )
    query = f"""
        SELECT
          history_items.id AS url_id,
          history_items.url AS url,
          history_items.title AS title,
          history_items.visit_count AS visit_count,
          history_visits.id AS visit_id,
          history_visits.visit_time AS visit_time,
          {load_successful_select}
        FROM history_items
        JOIN history_visits ON history_visits.history_item = history_items.id
        WHERE {xueqiu_domain_where('history_items.url')}
        ORDER BY history_visits.visit_time ASC
    """
    records = []
    for row in conn.execute(query):
        load_successful = int_number(row["load_successful"])
        records.append(
            browser_history_record(
                source_app="safari_history",
                path=path,
                url=row["url"],
                title=row["title"],
                visit_id=row["visit_id"],
                url_id=row["url_id"],
                event_time=safari_time_to_iso(row["visit_time"]),
                visit_count=row["visit_count"],
                typed_count=None,
                transition=load_successful,
                transition_type=safari_transition_type(load_successful),
            )
        )
    return records


def xueqiu_domain_where(column: str) -> str:
    patterns = []
    for scheme in ("https", "http"):
        patterns.extend(
            [
                f"{column} = '{scheme}://xueqiu.com'",
                f"{column} LIKE '{scheme}://xueqiu.com/%'",
                f"{column} LIKE '{scheme}://xueqiu.com?%'",
                f"{column} LIKE '{scheme}://xueqiu.com#%'",
                f"{column} LIKE '{scheme}://%.xueqiu.com'",
                f"{column} LIKE '{scheme}://%.xueqiu.com/%'",
                f"{column} LIKE '{scheme}://%.xueqiu.com?%'",
                f"{column} LIKE '{scheme}://%.xueqiu.com#%'",
            ]
        )
    return "(" + " OR ".join(patterns) + ")"


def browser_history_record(
    *,
    source_app: str,
    path: Path,
    url: str,
    title: Optional[str],
    visit_id: Any,
    url_id: Any,
    event_time: Optional[str],
    visit_count: Any,
    typed_count: Any,
    transition: Any,
    transition_type: Optional[str] = None,
) -> Dict[str, Any]:
    output_url = safe_url_for_output(url) or url
    return {
        "activity_type": "saved_page",
        "source_surface": "browser_history",
        "title": title or output_url,
        "content": title or output_url,
        "url": output_url,
        "time": event_time,
        "source_app": source_app,
        "visit_count": int_number(visit_count),
        "typed_count": int_number(typed_count),
        "transition": int_number(transition),
        "transition_type": transition_type or browser_transition_type(transition),
        "_collectorx_raw_ref": {
            "path": str(path),
            "parser": "browser_history",
            "source_app": source_app,
            "visit_id": visit_id,
            "url_id": url_id,
        },
    }


def chromium_time_to_iso(value: Any) -> Optional[str]:
    try:
        micros = int(value)
    except (TypeError, ValueError):
        return None
    if micros <= 0:
        return None
    epoch = datetime(1601, 1, 1, tzinfo=UTC)
    return (epoch + timedelta(microseconds=micros)).astimezone(CN_TZ).isoformat(timespec="seconds")


def safari_time_to_iso(value: Any) -> Optional[str]:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    epoch = datetime(2001, 1, 1, tzinfo=UTC)
    return (epoch + timedelta(seconds=seconds)).astimezone(CN_TZ).isoformat(timespec="seconds")


def safari_transition_type(load_successful: Optional[int]) -> Optional[str]:
    if load_successful is None:
        return None
    return "load_successful" if load_successful else "load_unknown"


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
    for key in (
        "activities",
        "statuses",
        "comments",
        "favorites",
        "follows",
        "followers",
        "friends",
        "watchlist",
        "stocks",
        "cubes",
        "portfolios",
        "rebalancing_histories",
        "items",
        "records",
        "list",
        "data",
    ):
        value = loaded.get(key)
        if isinstance(value, list):
            return [with_context(item, key, context) for item in value]
        if isinstance(value, dict):
            nested = extract_records(value)
            if not (len(nested) == 1 and nested[0] == value):
                return [with_context(item, key, context) for item in nested]
    for value in loaded.values():
        if isinstance(value, list):
            return [with_context(item, "list", context) for item in value]
    return [loaded]


def with_context(item: Any, section: str, context: Dict[str, Any]) -> Any:
    if not isinstance(item, dict):
        return {**context, "value": item, "source_section": section}
    record = {**context, **item}
    record.setdefault("source_section", section)
    return record


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


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


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "activity_type": "saved_page",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(path, text),
        "author": meta_content(html, "author") or meta_content(html, "og:site_name"),
        "url": canonical_url(html) or first_url(html),
        "content": text,
        "path": str(path),
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "activity_type": "saved_page" if "xueqiu.com" in text.lower() else "post",
        "title": infer_title(path, text),
        "url": first_url(text),
        "content": text,
        "path": str(path),
    }


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    activity_type = infer_activity_type(record, path)
    kind = kind_for_activity(activity_type)
    stock = dict_child(record, "stock")
    user = dict_child(record, "user")
    cube = dict_child(record, "cube")
    symbol = normalize_symbol(
        first(record, ["symbol", "code", "stock_symbol", "stockCode", "股票代码", "证券代码"])
        or first(stock, ["symbol", "code"])
    )
    name = (
        first(record, ["name", "stock_name", "stockName", "股票名称", "证券名称", "title", "标题"])
        or first(stock, ["name", "stock_name"])
        or first(cube, ["name", "cube_name", "title"])
    )
    content = first(record, ["text", "content", "description", "正文", "内容", "评论", "comment", "note", "备注"]) or ""
    url = safe_url_for_output(first(record, ["url", "link", "target_url", "链接"]) or build_xueqiu_url(record, user))
    event_time = first(
        record,
        [
            "time",
            "date",
            "created_at",
            "createdAt",
            "updated_at",
            "updatedAt",
            "created",
            "created_time",
            "日期",
            "时间",
        ],
    )
    event_time = event_time or collected_at or now_iso()
    data = {
        "activity_type": activity_type,
        "source_surface": infer_source_surface(record, path),
        "symbol": symbol,
        "symbols": symbols_for(record),
        "name": name,
        "group": first(record, ["group", "分组", "组合", "portfolio_name"]),
        "author": first(record, ["author", "screen_name", "用户名", "作者"]) or first(user, ["screen_name", "name"]),
        "author_id": first(record, ["user_id", "userid", "uid"]) or first(user, ["id", "uid", "user_id"]),
        "target_user": first(record, ["target_user", "target_screen_name", "followed_user", "被关注用户"]),
        "portfolio_symbol": first(record, ["cube_symbol", "portfolio_symbol", "组合代码"]) or first(cube, ["symbol"]),
        "portfolio_name": first(record, ["cube_name", "portfolio_name", "组合名称"]) or first(cube, ["name"]),
        "content_preview": preview(content),
        "url": url,
        "tags": tags_for(record),
        "metrics": metrics_for(record),
        "portfolio_changes": portfolio_changes_for(record),
        "source_app": first(record, ["source_app"]),
        "visit_count": int_number(first(record, ["visit_count"])),
        "typed_count": int_number(first(record, ["typed_count"])),
        "transition": int_number(first(record, ["transition"])),
        "transition_type": first(record, ["transition_type"]),
        "raw": sanitized(record),
        "broker_confirmed_trade": False,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}
    raw_ref = {
        "source_id": source_id_for_path(path),
        "source_extension": extension_label(path),
        "row": row,
        "activity_type": activity_type,
        "source_surface": data.get("source_surface"),
    }
    if isinstance(record.get("_collectorx_raw_ref"), dict):
        raw_ref.update(public_raw_ref(record["_collectorx_raw_ref"], source_path=path))
        raw_ref["row"] = row
        raw_ref["activity_type"] = activity_type
        raw_ref["source_surface"] = data.get("source_surface")
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, activity_type, event_time, symbol, name, url, json.dumps(sanitized(record), ensure_ascii=False, sort_keys=True)),
        "collector": COLLECTOR,
        "source": "雪球用户授权浏览器历史" if data.get("source_surface") == "browser_history" else "雪球用户授权投资活动",
        "owner_scope": "personal",
        "kind": kind,
        "time": event_time,
        "collected_at": collected_at or event_time,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio", "personal_message", "contact"]},
        "wiki_targets": wiki_targets_for_activity(activity_type),
    }


def gap_event(
    *,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    messages = {
        "xueqiu_authorized_input_missing": "No user-authorized Xueqiu export or local input was provided.",
        "xueqiu_records_empty": "Authorized Xueqiu input did not contain usable activity records.",
        "xueqiu_scope_policy_filtered_all": "Xueqiu activity records were found, but every candidate was outside the configured authorization scope policy.",
        "xueqiu_preflight_diagnosis_only": "Xueqiu preflight diagnosed local authorized-source readiness without collecting activity events.",
    }
    statuses = {
        "xueqiu_authorized_input_missing": "needs_xueqiu_authorized_input",
        "xueqiu_records_empty": "no_usable_xueqiu_activity_records",
        "xueqiu_scope_policy_filtered_all": "scope_policy_filtered_all",
        "xueqiu_preflight_diagnosis_only": "preflight_diagnosis_only",
    }
    audit = collection_audit or {}
    scope_audit = audit.get("xueqiu_activity_scope_policy") or {}
    preflight = audit.get("xueqiu_preflight_diagnosis") or {}
    preflight_readiness = preflight.get("collection_readiness") if isinstance(preflight.get("collection_readiness"), dict) else {}
    source_probe = preflight.get("source_probe") if isinstance(preflight.get("source_probe"), dict) else {}
    timestamp = collected_at or now_iso()
    raw_ref = {
        "preflight": True,
        "reason": reason,
        "scope_policy_enabled": bool(scope_audit.get("configured", False)),
    }
    if reason == "xueqiu_preflight_diagnosis_only":
        raw_ref["diagnosis_only"] = True
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "雪球投资活动授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": timestamp,
        "collected_at": timestamp,
        "data": {
            "activity_type": "collector_gap",
            "gap": reason,
            "status": statuses.get(reason, "no_usable_xueqiu_activity_records"),
            "profile_type": reason,
            "message": messages.get(reason, "No user-authorized Xueqiu activity evidence was collected."),
            "candidate_event_count": scope_audit.get("candidate_event_count", audit.get("scope_policy_candidate_event_count", 0)),
            "retained_event_count": scope_audit.get("retained_event_count", audit.get("scope_policy_retained_event_count", 0)),
            "filtered_event_count": scope_audit.get("filtered_event_count", audit.get("scope_policy_filtered_event_count", 0)),
            "filter_reason_counts": scope_audit.get("filter_reason_counts", audit.get("scope_policy_filter_reason_counts", {})),
            "policy_is_user_authorization_scope": scope_audit.get("policy_is_user_authorization_scope", True),
            "policy_does_not_assert_investment_relevance": scope_audit.get("policy_does_not_assert_investment_relevance", True),
            "xueqiu_is_broker_trade_source": False,
            "broker_trade_fact_claimed": False,
            "holding_fact_claimed": False,
            "order_or_fund_flow_claimed": False,
            "preflight_diagnosis_status": preflight_readiness.get("status"),
            "can_attempt_collect": preflight_readiness.get("can_attempt_collect", False),
            "can_attempt_har_collect": preflight_readiness.get("can_attempt_har_collect", False),
            "can_attempt_browser_history_collect": preflight_readiness.get("can_attempt_browser_history_collect", False),
            "can_attempt_local_export_collect": preflight_readiness.get("can_attempt_local_export_collect", False),
            "can_prepare_authorized_browser_history_copy": preflight_readiness.get("can_prepare_authorized_browser_history_copy", False),
            "can_attempt_real_account_network_collect": False,
            "diagnosed_source_count": source_probe.get("supported_input_file_count", 0),
            "diagnosed_har_xueqiu_entry_count": source_probe.get("har_xueqiu_entry_count", 0),
            "diagnosed_browser_history_xueqiu_visit_count": source_probe.get("browser_history_xueqiu_visit_count", 0),
        },
        "raw_ref": raw_ref,
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio", "collection_gap"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def infer_activity_type(record: Dict[str, Any], path: Optional[Path] = None) -> str:
    explicit = first(record, ["activity_type", "type", "kind", "action", "event", "类别", "类型", "动作"])
    text = json.dumps(sanitized(record), ensure_ascii=False).lower()
    if path is not None:
        text += " " + str(path).lower()
    if explicit:
        explicit_text = explicit.lower()
        if any(token in explicit_text for token in ["watch", "watchlist", "自选", "stock"]):
            return "watchlist"
        if any(token in explicit_text for token in ["follow_portfolio", "follow_cube", "关注组合"]):
            return "follow_portfolio"
        if any(token in explicit_text for token in ["follow_user", "user_follow", "关注用户", "follow"]):
            return "follow_user"
        if any(token in explicit_text for token in ["portfolio", "cube", "组合", "调仓", "rebalance"]):
            return "portfolio_activity"
        if any(token in explicit_text for token in ["comment", "评论", "reply"]):
            return "comment"
        if any(token in explicit_text for token in ["favorite", "fav", "收藏", "like"]):
            return "favorite"
        if any(token in explicit_text for token in ["saved_page", "保存页面"]):
            return "saved_page"
        if any(token in explicit_text for token in ["post", "status", "发帖"]):
            return "post"
    if any(key in record for key in ["rebalancing_histories", "cube_symbol", "cube_name", "portfolio_symbol", "组合代码"]):
        return "portfolio_activity"
    if any(key in record for key in ["comment_id", "reply_comment_id", "评论"]) or "评论" in text or "comment" in text:
        return "comment"
    if "调仓" in text or "组合" in text or "rebalance" in text or "portfolio" in text or "cube" in text:
        return "portfolio_activity"
    if "收藏" in text or "favorite" in text or '"fav' in text:
        return "favorite"
    if "关注组合" in text:
        return "follow_portfolio"
    if "关注用户" in text or "follow_user" in text:
        return "follow_user"
    if any(key in record for key in ["code", "symbol", "stock_symbol", "stockCode", "股票代码", "证券代码"]):
        return "watchlist"
    if first_url(text) and "xueqiu.com" in text:
        return "saved_page"
    return "post"


def infer_source_surface(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["source_surface"])
    if explicit:
        return explicit
    if first(record, ["activity_type", "type", "kind"]) == "saved_page" or path.suffix.lower() in {".html", ".htm"}:
        return "saved_page"
    text = json.dumps(sanitized(record), ensure_ascii=False).lower() + " " + str(path).lower()
    if "cube" in text or "组合" in text or "portfolio" in text:
        return "portfolio"
    if "comment" in text or "评论" in text:
        return "comment"
    if "favorite" in text or "收藏" in text:
        return "favorite"
    if "watchlist" in text or "自选" in text or "stock" in text:
        return "watchlist"
    if "follow" in text or "关注" in text:
        return "follow"
    if "status" in text or "timeline" in text:
        return "status"
    return "unknown"


def kind_for_activity(activity_type: str) -> str:
    if activity_type == "watchlist":
        return "watchlist"
    if activity_type in {"follow_user", "follow_portfolio"}:
        return "profile"
    if activity_type == "portfolio_activity":
        return "holding"
    if activity_type == "comment":
        return "message"
    if activity_type in {"favorite", "post", "saved_page"}:
        return "note"
    return "other"


def wiki_targets_for_activity(activity_type: str) -> List[str]:
    targets = {
        "watchlist": ["investor.opportunity_watchlist.watchlist", "investor.capability_circle.attention_universe"],
        "follow_user": ["investor.network_collaboration.discussions", "investor.information_sources.news_consumption"],
        "follow_portfolio": ["investor.information_sources.news_consumption", "investor.risk_portfolio.portfolio_constraints"],
        "portfolio_activity": ["investor.decision_framework.strategy_rules", "investor.risk_portfolio.portfolio_constraints"],
        "comment": ["investor.network_collaboration.discussions", "investor.behavior.emotion_pattern"],
        "favorite": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "saved_page": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "post": ["investor.record_review.review_record", "investor.decision_framework.strategy_rules"],
    }
    return targets.get(activity_type, ["collectorx.data_quality.collection_gaps"])


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    counts = Counter(event["kind"] for event in events)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in events)
    surface_counts = Counter((event.get("data") or {}).get("source_surface", "unknown") for event in events)
    gap_only = bool(events) and set(activity_counts) == {"collector_gap"}
    activity_event_count = sum(1 for event in events if (event.get("data") or {}).get("activity_type") != "collector_gap")
    gap_event_count = sum(1 for event in events if (event.get("data") or {}).get("gap"))
    usable_event_count = activity_event_count
    observed = sorted(activity for activity in activity_counts if activity != "collector_gap")
    missing = [activity for activity in EXPECTED_ACTIVITY_TYPES if activity not in activity_counts]
    audit = collection_audit or {}
    preflight = audit.get("xueqiu_preflight_diagnosis") if isinstance(audit.get("xueqiu_preflight_diagnosis"), dict) else {}
    preflight_readiness = preflight.get("collection_readiness") if isinstance(preflight.get("collection_readiness"), dict) else {}
    if gap_only and preflight:
        readiness_status = "preflight_diagnosis_only"
        activity_boundary_scope = "preflight_only"
        next_action = str(preflight_readiness.get("next_action") or "Run collect after providing an authorized Xueqiu source.")
    elif gap_only and audit.get("xueqiu_activity_scope_policy_filtered_all"):
        readiness_status = "scope_policy_filtered_all"
        activity_boundary_scope = "scope_policy_excluded_all"
        next_action = "Review or relax Xueqiu activity scope policy, then rerun the collector."
    elif gap_only:
        readiness_status = "needs_xueqiu_authorized_input"
        activity_boundary_scope = "none"
        next_action = "提供雪球个人活动导出或授权输入后重跑。"
    else:
        readiness_status = "events_collected"
        activity_boundary_scope = "partial_authorized_input"
        next_action = "可进入投资分身蒸馏；后续补真实账号分页/关注/收藏/组合覆盖验证。"
    return {
        "schema": "xueqiu.investor_activity.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "usable_event_count": usable_event_count,
        "activity_event_count": activity_event_count,
        "gap_event_count": gap_event_count,
        "source_file_count": len({(event.get("raw_ref") or {}).get("source_id") for event in events if (event.get("raw_ref") or {}).get("source_id")}),
        "kind_counts": dict(sorted(counts.items())),
        "activity_counts": dict(sorted(activity_counts.items())),
        "surface_counts": dict(sorted(surface_counts.items())),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "observed_activity_types": observed,
        "missing_expected_activity_types": missing,
        "field_coverage": build_activity_field_coverage(events),
        "activity_boundary_proof": activity_boundary_proof(events, collection_audit=collection_audit),
        "evidence_policy": {
            "xueqiu_is_broker_trade_source": False,
            "broker_confirmed_trade_collection": False,
            "evidence_role": "attention_network_opinion_and_model_portfolio_only",
            "requires_corroboration_with": ["broker_trades", "portfolio_holdings", "research_documents", "investment_notes", "reviews"],
        },
        "collection_readiness": {
            "status": readiness_status,
            "can_enter_finclaw": usable_event_count > 0,
            "can_enter_xueqiu_activity_lake": usable_event_count > 0,
            "can_enter_data_quality_lake": gap_event_count > 0,
            "can_feed_investor_wiki_evidence": usable_event_count > 0,
            "can_claim_broker_trade_collection": False,
            "can_claim_complete_xueqiu_activity_boundary": False,
            "activity_boundary_scope": activity_boundary_scope,
            "usable_event_count": usable_event_count,
            "activity_event_count": activity_event_count,
            "gap_event_count": gap_event_count,
            "preflight_can_attempt_collect": bool(preflight_readiness.get("can_attempt_collect", False)),
            "preflight_can_attempt_har_collect": bool(preflight_readiness.get("can_attempt_har_collect", False)),
            "preflight_can_attempt_browser_history_collect": bool(preflight_readiness.get("can_attempt_browser_history_collect", False)),
            "preflight_can_attempt_local_export_collect": bool(preflight_readiness.get("can_attempt_local_export_collect", False)),
            "preflight_can_prepare_authorized_browser_history_copy": bool(
                preflight_readiness.get("can_prepare_authorized_browser_history_copy", False)
            ),
            "next_action": next_action,
        },
        "collection_audit": audit,
    }


def build_activity_field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    activity_events = [event for event in events if (event.get("data") or {}).get("activity_type") != "collector_gap"]
    fields = [
        "activity_type",
        "source_surface",
        "symbol",
        "symbols",
        "name",
        "author",
        "author_id",
        "target_user",
        "portfolio_symbol",
        "portfolio_name",
        "portfolio_changes",
        "content_preview",
        "url",
        "tags",
        "metrics",
        "source_app",
        "visit_count",
        "typed_count",
        "transition_type",
    ]
    coverage: Dict[str, Dict[str, int]] = {}
    for field in fields:
        count = sum(1 for event in activity_events if (event.get("data") or {}).get(field) not in (None, "", [], {}))
        coverage[field] = {"present": count, "missing": max(len(activity_events) - count, 0)}
    return {
        "activity_event_count": len(activity_events),
        "fields": coverage,
    }


ACTIVITY_SCOPE_POLICY_KEYS = (
    "allow_activity",
    "deny_activity",
    "allow_source_surface",
    "deny_source_surface",
    "allow_source_app",
    "deny_source_app",
    "allow_domain",
    "deny_domain",
    "allow_symbol",
    "deny_symbol",
    "allow_author",
    "deny_author",
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


def normalize_activity_scope_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    policy = policy or {}
    return {key: split_scope_values(policy.get(key)) for key in ACTIVITY_SCOPE_POLICY_KEYS}


def activity_scope_policy_configured(policy: Dict[str, List[str]]) -> bool:
    return any(policy.get(key) for key in ACTIVITY_SCOPE_POLICY_KEYS)


def apply_activity_scope_policy(
    events: List[Dict[str, Any]],
    policy: Optional[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    normalized_policy = normalize_activity_scope_policy(policy)
    configured = activity_scope_policy_configured(normalized_policy)
    candidates = [event for event in events if (event.get("data") or {}).get("activity_type") != "collector_gap"]
    retained: List[Dict[str, Any]] = []
    reason_counts: Counter = Counter()
    for event in events:
        if (event.get("data") or {}).get("activity_type") == "collector_gap":
            retained.append(event)
            continue
        reasons = activity_scope_filter_reasons(event, normalized_policy) if configured else []
        if reasons:
            for reason in reasons:
                reason_counts[reason] += 1
            continue
        retained.append(event)
    retained_candidate_count = sum(1 for event in retained if (event.get("data") or {}).get("activity_type") != "collector_gap")
    audit = {
        "configured": configured,
        "filters": normalized_policy,
        "candidate_event_count": len(candidates),
        "retained_event_count": retained_candidate_count,
        "filtered_event_count": len(candidates) - retained_candidate_count,
        "filter_reason_counts": dict(sorted(reason_counts.items())),
        "filtered_all": configured and bool(candidates) and retained_candidate_count == 0,
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "xueqiu_is_broker_trade_source": False,
        "deny_rules_win_over_allow_rules": True,
    }
    return retained, audit


def attach_activity_scope_policy_audit(audit: Dict[str, Any], scope_audit: Dict[str, Any]) -> None:
    audit["xueqiu_activity_scope_policy"] = scope_audit
    audit["scope_policy_candidate_event_count"] = scope_audit.get("candidate_event_count", 0)
    audit["scope_policy_retained_event_count"] = scope_audit.get("retained_event_count", 0)
    audit["scope_policy_filtered_event_count"] = scope_audit.get("filtered_event_count", 0)
    audit["scope_policy_filter_reason_counts"] = scope_audit.get("filter_reason_counts", {})
    audit["xueqiu_activity_scope_policy_filtered_all"] = bool(scope_audit.get("filtered_all"))


def activity_scope_filter_reasons(event: Dict[str, Any], policy: Dict[str, List[str]]) -> List[str]:
    data = event.get("data") or {}
    checks = [
        ("activity", policy.get("allow_activity", []), policy.get("deny_activity", []), [data.get("activity_type")], scope_identity_match),
        ("source_surface", policy.get("allow_source_surface", []), policy.get("deny_source_surface", []), [data.get("source_surface")], scope_identity_match),
        ("source_app", policy.get("allow_source_app", []), policy.get("deny_source_app", []), [data.get("source_app")], scope_identity_match),
        ("domain", policy.get("allow_domain", []), policy.get("deny_domain", []), [activity_event_domain(event)], scope_domain_match),
        ("symbol", policy.get("allow_symbol", []), policy.get("deny_symbol", []), activity_event_symbols(event), scope_symbol_match),
        ("author", policy.get("allow_author", []), policy.get("deny_author", []), [data.get("author"), data.get("target_user"), data.get("author_id")], scope_text_match),
        ("keyword", policy.get("allow_keyword", []), policy.get("deny_keyword", []), [activity_scope_search_text(event)], scope_text_match),
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
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm)
    return value_norm == pattern_norm


def scope_text_match(value: Any, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm)
    return pattern_norm in value_norm


def scope_domain_match(value: Any, pattern: str) -> bool:
    domain = str(value or "").strip().lower().lstrip("@")
    pattern_norm = str(pattern or "").strip().lower().lstrip("@")
    if not domain or not pattern_norm:
        return False
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(domain, pattern_norm)
    return domain == pattern_norm or domain.endswith(f".{pattern_norm}")


def scope_symbol_match(value: Any, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    normalized_value_symbol = str(normalize_symbol(value_norm) or value_norm).lower()
    normalized_pattern_symbol = str(normalize_symbol(pattern_norm) or pattern_norm).lower()
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm) or fnmatch.fnmatch(normalized_value_symbol, normalized_pattern_symbol)
    return value_norm == pattern_norm or normalized_value_symbol == normalized_pattern_symbol


def activity_event_domain(event: Dict[str, Any]) -> str:
    url = str((event.get("data") or {}).get("url") or "")
    return urlparse(url).netloc.lower()


def activity_event_symbols(event: Dict[str, Any]) -> List[str]:
    data = event.get("data") or {}
    values: List[str] = []
    for key in ("symbol", "portfolio_symbol"):
        if data.get(key):
            values.append(str(data[key]))
    for item in data.get("symbols") or []:
        values.append(str(item))
    for change in data.get("portfolio_changes") or []:
        if isinstance(change, dict) and change.get("symbol"):
            values.append(str(change["symbol"]))
    return values


def activity_scope_search_text(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    values = [
        data.get("activity_type"),
        data.get("source_surface"),
        data.get("source_app"),
        data.get("symbol"),
        *(data.get("symbols") or []),
        data.get("name"),
        data.get("group"),
        data.get("author"),
        data.get("target_user"),
        data.get("portfolio_symbol"),
        data.get("portfolio_name"),
        data.get("content_preview"),
        data.get("url"),
        *(data.get("tags") or []),
        json.dumps(raw, ensure_ascii=False, sort_keys=True) if raw else "",
    ]
    return "\n".join(str(value) for value in values if value not in (None, "", [], {}))


def activity_authorization_scope_boundary(collection_audit: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    audit = collection_audit or {}
    scope = audit.get("xueqiu_activity_scope_policy") or {}
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


def build_evidence(
    events: List[Dict[str, Any]],
    *,
    generated_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = [event for event in events if (event.get("data") or {}).get("activity_type") != "collector_gap"]
    gap_event_count = sum(1 for event in events if (event.get("data") or {}).get("gap"))
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in usable_events)
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
            "xueqiu_is_strong_trade_source": False,
            "activity_counts": dict(sorted(activity_counts.items())),
            "activity_boundary_proof": activity_boundary_proof(events, collection_audit=collection_audit),
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
            "evidence_role": "attention_network_opinion_and_model_portfolio_only",
        },
    }
    return augment_evidence_with_dimensions(evidence, usable_events, INVESTOR_WIKI_SUBDIMENSION_RULES)


def activity_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    activity_events = [event for event in events if (event.get("data") or {}).get("activity_type") != "collector_gap"]
    gap_event_count = sum(1 for event in events if (event.get("data") or {}).get("gap"))
    audit = collection_audit or {}
    if not activity_events:
        scope_policy_filtered_all = bool(audit.get("xueqiu_activity_scope_policy_filtered_all"))
        preflight = audit.get("xueqiu_preflight_diagnosis") if isinstance(audit.get("xueqiu_preflight_diagnosis"), dict) else {}
        preflight_only = bool(preflight)
        return {
            "proof_scope": "preflight_only" if preflight_only else ("scope_policy_excluded_all" if scope_policy_filtered_all else "none"),
            "overall_proof_level": "preflight_diagnosis_only" if preflight_only else ("scope_policy_filtered_all" if scope_policy_filtered_all else "no_authorized_activity_evidence"),
            "complete_xueqiu_activity_boundary_claimed": False,
            "xueqiu_is_broker_trade_source": False,
            "activity_event_count": 0,
            "gap_event_count": gap_event_count,
            "can_enter_xueqiu_activity_lake": False,
            "can_enter_data_quality_lake": gap_event_count > 0,
            "can_feed_investor_wiki_evidence": False,
            "expected_activity_types": list(EXPECTED_ACTIVITY_TYPES),
            "observed_activity_types": [],
            "missing_expected_activity_types": list(EXPECTED_ACTIVITY_TYPES),
            "activity_proofs": [],
            "authorization_scope_boundary": activity_authorization_scope_boundary(audit),
            "pagination_completeness": pagination_completeness_summary(activity_events, audit),
            "preflight_readiness": preflight.get("collection_readiness", {}) if preflight_only else {},
            "missing_global_requirements": (
                ["authorized_xueqiu_activity_collection_not_run"]
                if preflight_only
                else (["scope_policy_retained_records"] if scope_policy_filtered_all else ["authorized_xueqiu_activity_input"])
            ),
        }

    activity_counts = Counter(str((event.get("data") or {}).get("activity_type") or "unknown") for event in activity_events)
    observed = sorted(activity for activity in activity_counts if activity != "unknown")
    missing = [activity for activity in EXPECTED_ACTIVITY_TYPES if activity_counts.get(activity, 0) == 0]
    activity_types = list(EXPECTED_ACTIVITY_TYPES)
    for activity in sorted(activity_counts):
        if activity not in activity_types:
            activity_types.append(activity)
    proofs = [activity_type_proof(activity, activity_events) for activity in activity_types]
    missing_global = []
    if missing:
        missing_global.append("expected_activity_surface_coverage")
    if not any((event.get("data") or {}).get("symbols") for event in activity_events):
        missing_global.append("symbol_or_watchlist_evidence")
    if not any((event.get("data") or {}).get("author") or (event.get("data") or {}).get("target_user") for event in activity_events):
        missing_global.append("information_network_identity")
    if not any((event.get("data") or {}).get("content_preview") for event in activity_events):
        missing_global.append("opinion_or_saved_content_preview")
    pagination = pagination_completeness_summary(activity_events, audit)
    if pagination["completeness_level"] != "paginated_partial_export":
        missing_global.append("validated_pagination")
    return {
        "proof_scope": "partial_authorized_input",
        "overall_proof_level": overall_activity_boundary_level(activity_counts),
        "complete_xueqiu_activity_boundary_claimed": False,
        "xueqiu_is_broker_trade_source": False,
        "activity_event_count": len(activity_events),
        "gap_event_count": gap_event_count,
        "can_enter_xueqiu_activity_lake": len(activity_events) > 0,
        "can_enter_data_quality_lake": gap_event_count > 0,
        "can_feed_investor_wiki_evidence": len(activity_events) > 0,
        "expected_activity_types": list(EXPECTED_ACTIVITY_TYPES),
        "observed_activity_types": observed,
        "missing_expected_activity_types": missing,
        "activity_proof_level_counts": dict(sorted(Counter(proof["proof_level"] for proof in proofs).items())),
        "activity_proofs": proofs,
        "browser_history_boundary": {
            "browser_history_supported": audit.get("browser_history_supported", False),
            "browser_history_domain_filtering": audit.get("browser_history_domain_filtering", False),
            "browser_history_input_count": audit.get("browser_history_input_count", 0),
            "browser_history_event_count": audit.get("browser_history_event_count", 0),
            "browser_history_source_apps": audit.get("browser_history_source_apps", []),
            "unrelated_browser_history_collected": False,
            "complete_account_activity_claimed_from_history": False,
        },
        "authorization_scope_boundary": activity_authorization_scope_boundary(audit),
        "pagination_completeness": pagination,
        "missing_global_requirements": missing_global,
    }


def activity_type_proof(activity_type: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    activity_events = [
        event for event in events
        if str((event.get("data") or {}).get("activity_type") or "unknown") == activity_type
    ]
    field_counts = {
        field: sum(1 for event in activity_events if (event.get("data") or {}).get(field) not in (None, "", [], {}))
        for field in ACTIVITY_REQUIRED_FIELDS.get(activity_type, ())
    }
    present_required = [field for field, count in field_counts.items() if count > 0]
    missing_required = [field for field, count in field_counts.items() if count == 0]
    return {
        "activity_type": activity_type,
        "event_count": len(activity_events),
        "proof_level": activity_proof_level(len(activity_events), present_required, missing_required),
        "required_fields": list(ACTIVITY_REQUIRED_FIELDS.get(activity_type, ())),
        "present_required_fields": present_required,
        "missing_required_fields": missing_required,
        "field_counts": dict(sorted(field_counts.items())),
        "symbol_event_count": sum(1 for event in activity_events if (event.get("data") or {}).get("symbols")),
        "content_event_count": sum(1 for event in activity_events if (event.get("data") or {}).get("content_preview")),
        "url_event_count": sum(1 for event in activity_events if (event.get("data") or {}).get("url")),
    }


def activity_proof_level(event_count: int, present_required: List[str], missing_required: List[str]) -> str:
    if event_count == 0:
        return "missing_activity_evidence"
    if not missing_required:
        return "usable_activity_evidence"
    if present_required:
        return "thin_activity_evidence"
    return "raw_activity_presence_only"


def overall_activity_boundary_level(activity_counts: Counter) -> str:
    observed_expected_count = sum(1 for activity in EXPECTED_ACTIVITY_TYPES if activity_counts.get(activity, 0) > 0)
    if observed_expected_count == len(EXPECTED_ACTIVITY_TYPES):
        return "broad_partial_activity_boundary"
    if observed_expected_count >= 4:
        return "medium_partial_activity_boundary"
    return "narrow_partial_activity_boundary"


def pagination_completeness_summary(events: List[Dict[str, Any]], audit: Dict[str, Any]) -> Dict[str, Any]:
    limit = audit.get("limit")
    pagination_marker_count = int(audit.get("pagination_marker_count") or 0)
    har_used = bool(audit.get("authorized_browser_network_export_used"))
    completeness_level = "no_activity_input"
    if events:
        if isinstance(limit, int) and limit >= 0 and len(events) >= limit:
            completeness_level = "truncated_by_limit"
        elif har_used and pagination_marker_count > 0:
            completeness_level = "paginated_partial_export"
        elif pagination_marker_count > 0:
            completeness_level = "pagination_markers_observed_not_validated"
        elif har_used:
            completeness_level = "single_page_or_unknown_pagination"
        else:
            completeness_level = "no_pagination_evidence"
    missing_requirements = []
    if pagination_marker_count == 0 and events:
        missing_requirements.append("pagination_markers")
    if not har_used and events:
        missing_requirements.append("authorized_browser_network_or_account_export")
    missing_requirements.append("real_account_pagination_validation")
    return {
        "completeness_level": completeness_level,
        "complete_timeline_claimed": False,
        "requires_real_pagination_validation": True,
        "event_count": len(events),
        "limit": limit,
        "pagination_marker_count": pagination_marker_count,
        "pagination_marker_field_counts": dict(sorted((audit.get("pagination_marker_field_counts") or {}).items())),
        "authorized_browser_network_export_used": har_used,
        "browser_history_event_count": int(audit.get("browser_history_event_count") or 0),
        "browser_history_source_apps": list(audit.get("browser_history_source_apps") or []),
        "har_endpoint_counts": dict(sorted((audit.get("har_endpoint_counts") or {}).items())),
        "har_response_record_count": int(audit.get("har_response_record_count") or 0),
        "missing_requirements": missing_requirements,
    }


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def dict_child(record: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def preview(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return redact_sensitive_text(str(value))[:1200]


def redact_sensitive_text(value: str) -> str:
    text = CN_MOBILE_RE.sub(r"\1****\2", value)
    return INLINE_SECRET_RE.sub(r"\1=<redacted>", text)


def number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def int_number(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def browser_transition_type(value: Any) -> Optional[str]:
    raw = int_number(value)
    if raw is None:
        return None
    core = raw & 0xFF
    mapping = {
        0: "link",
        1: "typed",
        2: "auto_bookmark",
        3: "auto_subframe",
        4: "manual_subframe",
        5: "generated",
        6: "auto_toplevel",
        7: "form_submit",
        8: "reload",
        9: "keyword",
        10: "keyword_generated",
    }
    return mapping.get(core, "other")


def normalize_symbol(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    symbol = str(value).strip().upper()
    if re.fullmatch(r"\d{6}", symbol):
        if symbol.startswith(("6", "9")):
            return f"SH{symbol}"
        if symbol.startswith(("0", "2", "3")):
            return f"SZ{symbol}"
        if symbol.startswith(("4", "8")):
            return f"BJ{symbol}"
    return symbol


def symbols_for(record: Dict[str, Any]) -> List[str]:
    symbols: List[str] = []
    for key in ("symbol", "code", "stock_symbol", "stockCode", "股票代码", "证券代码"):
        value = normalize_symbol(first(record, [key]))
        if value:
            symbols.append(value)
    stock = dict_child(record, "stock")
    for key in ("symbol", "code"):
        value = normalize_symbol(first(stock, [key]))
        if value:
            symbols.append(value)
    text = json.dumps(sanitized(record), ensure_ascii=False)
    for match in re.finditer(r"\$[^$()]{1,40}\(((?:SH|SZ|BJ|HK|US)?[A-Z0-9.]{2,12})\)\$", text, flags=re.IGNORECASE):
        symbols.append(normalize_symbol(match.group(1)) or match.group(1).upper())
    for match in re.finditer(r"\b(?:SH|SZ|BJ)\d{6}\b|\bHK\d{5}\b|(?<!\d)[6038]\d{5}(?!\d)", text, flags=re.IGNORECASE):
        value = normalize_symbol(match.group(0))
        if value:
            symbols.append(value)
    return sorted(set(symbols))


def tags_for(record: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for key in ("tags", "tag", "topics", "topic", "行业", "标签", "话题"):
        value = record.get(key)
        if isinstance(value, list):
            tags.extend(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            tags.extend(part.strip() for part in re.split(r"[,，;；\s]+", str(value)) if part.strip())
    return sorted(set(tags))


def metrics_for(record: Dict[str, Any]) -> Dict[str, float]:
    metrics = {
        "comment_count": number(first(record, ["comment_count", "comments_count", "reply_count", "评论数"])),
        "like_count": number(first(record, ["like_count", "liked_count", "赞数", "点赞数"])),
        "favorite_count": number(first(record, ["favorite_count", "fav_count", "收藏数"])),
        "retweet_count": number(first(record, ["retweet_count", "share_count", "转发数"])),
    }
    return {key: value for key, value in metrics.items() if value is not None}


def portfolio_changes_for(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = record.get("rebalancing_histories") or record.get("holdings") or record.get("positions") or record.get("changes")
    if not isinstance(candidates, list):
        return []
    changes: List[Dict[str, Any]] = []
    for item in candidates[:50]:
        if not isinstance(item, dict):
            continue
        stock = dict_child(item, "stock")
        changes.append(
            {
                "symbol": normalize_symbol(first(item, ["stock_symbol", "symbol", "code"]) or first(stock, ["symbol", "code"])),
                "name": first(item, ["stock_name", "name"]) or first(stock, ["name"]),
                "prev_weight": number(first(item, ["prev_weight", "prevWeight", "old_weight", "原仓位"])),
                "target_weight": number(first(item, ["target_weight", "targetWeight", "weight", "目标仓位"])),
                "price": number(first(item, ["price", "成交价", "价格"])),
                "updated_at": first(item, ["updated_at", "created_at", "time", "date"]),
            }
        )
    return [{key: value for key, value in change.items() if value not in (None, "", [], {})} for change in changes]


def build_xueqiu_url(record: Dict[str, Any], user: Dict[str, Any]) -> Optional[str]:
    status_id = first(record, ["id", "status_id"])
    user_id = first(record, ["user_id", "uid"]) or first(user, ["id", "uid"])
    if status_id and user_id:
        return f"https://xueqiu.com/{user_id}/{status_id}"
    return None


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).startswith("_collectorx_"):
                continue
            lowered = str(key).lower()
            normalized_key = normalize_audit_key(key)
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            if normalized_key in LOCAL_PATH_KEYS:
                continue
            cleaned[str(key)] = sanitized(item)
        return cleaned
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        text = safe_url_for_output(value) if re.match(r"^https?://", value.strip(), flags=re.IGNORECASE) else value
        return redact_sensitive_text(text or value)[:2000]
    return value


PAGINATION_KEYS = {
    "count",
    "cursor",
    "last_id",
    "max_id",
    "next",
    "next_cursor",
    "next_max_id",
    "page",
    "page_no",
    "page_size",
    "since_id",
    "total",
}


def record_pagination_markers(record: Dict[str, Any], audit: Dict[str, Any]) -> None:
    seen: set[str] = set()
    for key in record:
        normalized = normalize_audit_key(key)
        if normalized in PAGINATION_KEYS:
            seen.add(normalized)
    if not seen:
        return
    audit["pagination_marker_count"] += 1
    for key in sorted(seen):
        increment_counter(audit, "pagination_marker_field_counts", key)


def normalize_audit_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def increment_counter(audit: Dict[str, Any], key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_audit(audit: Dict[str, Any]) -> None:
    for key in (
        "extension_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "pagination_marker_field_counts",
        "har_skip_reason_counts",
        "har_endpoint_counts",
        "scope_policy_filter_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))
    audit["browser_history_source_apps"] = sorted(set(audit.get("browser_history_source_apps") or []))


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def meta_content(html: str, name: str) -> Optional[str]:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return unescape(match.group(1)).strip()
    return None


def title_tag(html: str) -> Optional[str]:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not match:
        return None
    return html_to_text(match.group(1))[:200]


def canonical_url(html: str) -> Optional[str]:
    match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if match:
        return unescape(match.group(1)).strip()
    return None


def first_url(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return safe_url_for_output(match.group(0)) if match else None


def safe_url_for_output(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    text = str(value)
    parsed = urlparse(text)
    query = str(parsed.query or "")
    fragment = str(parsed.fragment or "")
    if query and any(fragment_key in query.lower() for fragment_key in SECRET_KEY_FRAGMENTS):
        parsed = parsed._replace(query="")
    if fragment and any(fragment_key in fragment.lower() for fragment_key in SECRET_KEY_FRAGMENTS):
        parsed = parsed._replace(fragment="")
    return urlunparse(parsed)


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return path.stem


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
