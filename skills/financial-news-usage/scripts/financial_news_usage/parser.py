"""Parse user-authorized financial news usage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from collectorx.investor_wiki import augment_evidence_with_dimensions
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution outside repo cwd
    for parent in Path(__file__).resolve().parents:
        if (parent / "collectorx").exists():
            sys.path.insert(0, str(parent))
            break
    from collectorx.investor_wiki import augment_evidence_with_dimensions


COLLECTOR = "financial-news-usage"
CN_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc
SUPPORTED_RECORD_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".ndjson",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
    ".sqlite",
    ".sqlite3",
    ".db",
}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
BROWSER_HISTORY_EXTENSIONS = {".sqlite", ".sqlite3", ".db"}
SUPPORTED_ZIP_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS
BROWSER_HISTORY_NAMES = {"History", "History.db"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
FINANCIAL_NEWS_DOMAINS = {
    "cls": ("cls.cn", "cailianpress.com"),
    "wallstreetcn": ("wallstreetcn.com", "wscn.com"),
    "gelonghui": ("gelonghui.com", "gelonghui.cn"),
}
EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS = ("cls", "wallstreetcn", "gelonghui")
EXPECTED_FINANCIAL_NEWS_ACTIONS = ("read", "favorite", "search", "subscribe", "alert")
INVESTOR_WIKI_SUBDIMENSION_RULES = {
    "inv-market-view": {
        "support_level": "weak",
        "route_targets": ["investor.information_sources.news_consumption", "investor.capability_circle.attention_universe"],
        "signals": ["阅读、收藏、搜索和订阅主题可作为市场关注线索。"],
        "gaps": ["资讯消费不等于市场观，必须避免把公共新闻当成用户结论。"],
    },
    "inv-risk-view": {
        "support_level": "weak",
        "data_matches": {"usage_topics": ["risk_event"]},
        "signals": ["风险事件阅读和提醒可提示用户关注的风险类型。"],
        "gaps": ["阅读风险新闻不等于用户风险红线，需要组合和复盘交叉验证。"],
    },
    "inv-industry-circle": {
        "support_level": "weak",
        "data_matches": {"usage_topics": ["industry_theme", "company_fundamental"]},
        "signals": ["行业、公司基本面阅读痕迹可侧写关注行业。"],
        "gaps": ["关注行业不等于能力圈，需研究笔记/终端/交易记录验证。"],
    },
    "inv-information-learning-style": {
        "support_level": "medium",
        "route_targets": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "signals": ["阅读、收藏、搜索、订阅和提醒动作可刻画信息摄入方式。"],
        "gaps": ["仍缺少用户如何筛选、吸收和纠错的过程证据。"],
    },
    "inv-rules-library": {
        "support_level": "weak",
        "route_targets": ["investor.decision_framework.monitoring_rules", "investor.execution.watchlist_alerts"],
        "signals": ["资讯提醒和订阅栏目可作为监控规则候选。"],
        "gaps": ["需要确认提醒是用户主动配置，而非平台默认推送。"],
    },
    "inv-execution-discipline": {
        "support_level": "weak",
        "route_targets": ["investor.execution.watchlist_alerts", "investor.decision_framework.monitoring_rules"],
        "signals": ["自选提醒和事件提醒可作为执行前监控线索。"],
        "gaps": ["资讯提醒不是下单执行，需券商委托/成交验证。"],
    },
    "inv-information-source": {
        "support_level": "medium",
        "route_targets": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "signals": ["财联社、华尔街见闻、格隆汇的阅读和订阅可明确个人信息源。"],
        "gaps": ["只采个人使用痕迹，不把公共新闻全文写入个人 Wiki。"],
    },
}
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
TEXT_PREVIEW_MAX_CHARS = 1200
FINANCIAL_NEWS_RECOMMENDED_FIELDS = (
    "action_type",
    "platform",
    "usage_topics",
    "primary_usage_topic",
    "title",
    "url",
    "domain",
    "source_app",
    "source",
    "channel",
    "query",
    "query_terms",
    "subscription_target",
    "alert_condition",
    "notification_channel",
    "trigger_source",
    "referrer",
    "session_id",
    "dwell_seconds",
    "symbols",
    "tags",
    "article_id",
    "text_preview",
    "time",
)
FINANCIAL_NEWS_TOPIC_ORDER = (
    "macro_policy",
    "market_strategy",
    "industry_theme",
    "company_fundamental",
    "hk_us_market",
    "risk_event",
    "trading_opportunity",
    "portfolio_alert",
    "unclassified_usage_topic",
)
FINANCIAL_NEWS_TOPIC_TERMS = {
    "macro_policy": {
        "宏观",
        "政策",
        "利率",
        "央行",
        "流动性",
        "财政",
        "美联储",
        "降息",
        "加息",
    },
    "market_strategy": {
        "策略",
        "A股",
        "市场",
        "仓位",
        "风格",
        "配置",
        "择时",
        "风险偏好",
    },
    "industry_theme": {
        "行业",
        "产业链",
        "景气",
        "主题",
        "半导体",
        "新能源",
        "医药",
        "创新药",
        "AI",
    },
    "company_fundamental": {
        "财报",
        "业绩",
        "订单",
        "现金流",
        "ROE",
        "毛利率",
        "基本面",
        "公司",
    },
    "hk_us_market": {
        "港股",
        "美股",
        "中概股",
        "恒生",
        "纳斯达克",
        "海外",
        "HK",
        "US",
    },
    "risk_event": {
        "预警",
        "风险预警",
        "下跌",
        "回撤",
        "违约",
        "黑天鹅",
        "监管",
    },
    "trading_opportunity": {
        "机会",
        "异动",
        "突破",
        "催化",
        "快讯",
        "交易机会",
    },
    "portfolio_alert": {
        "自选",
        "提醒",
        "盯盘",
        "推送",
        "alert",
        "watchlist",
    },
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(inputs, collected_at=collected_at, limit=limit)
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    events: List[Dict[str, Any]] = []
    extension_counts: Counter[str] = Counter()
    skipped_extension_counts: Counter[str] = Counter()
    skipped_reason_counts: Counter[str] = Counter()
    skipped_archive_member_reason_counts: Counter[str] = Counter()
    browser_history_source_apps: set[str] = set()
    browser_history_source_app_counts: Counter[str] = Counter()
    audit: Dict[str, Any] = {
        "source_type": "authorized_financial_news_usage_export",
        "input_count": len(input_list),
        "requested_inputs": [str(Path(raw).expanduser()) for raw in input_list],
        "resolved_input_file_count": 0,
        "input_missing_count": 0,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "supported_browser_history_names": sorted(BROWSER_HISTORY_NAMES),
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
        "browser_history_input_count": 0,
        "browser_history_event_count": 0,
        "browser_history_source_apps": [],
        "browser_history_source_app_counts": {},
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
                    parsed, archive_audit = parse_zip_with_audit(path, limit=remaining_limit(limit, events))
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
                    parser = parser_name_for_path(path)
                    result.update(
                        {
                            "status": "parsed" if parsed else "no_records_parsed",
                            "parser": parser,
                            "parsed_record_count": len(parsed),
                        }
                    )
                    if parser == "browser_history":
                        audit["browser_history_input_count"] += 1
            except Exception:
                parsed = []
                audit["skipped_file_count"] += 1
                skipped_extension_counts[ext] += 1
                skipped_reason_counts["parse_error"] += 1
                result.update({"status": "parse_error", "reason": "parse_error", "parsed_record_count": 0})
            audit["path_results"].append(result)
            row = 0
            for record in parsed:
                if not isinstance(record, dict):
                    continue
                row += 1
                event = record_to_event(record, path=path, row=row, collected_at=collected_at)
                events.append(event)
                source_app = str((event.get("data") or {}).get("source_app") or "")
                if source_app.endswith("_history"):
                    browser_history_source_apps.add(source_app)
                    browser_history_source_app_counts[source_app] += 1
                if limit is not None and len(events) >= limit:
                    audit["limit_reached"] = True
                    break
        if limit is not None and len(events) >= limit:
            break

    if not events:
        reason = "financial_news_usage_authorized_input_missing" if not input_list or audit["input_missing_count"] else "financial_news_usage_records_empty"
        events = [gap_event(collected_at=collected_at, reason=reason)]
    audit["parsed_record_count"] = len(usable_usage_events(events))
    audit["emitted_event_count"] = len(events)
    audit["extension_counts"] = dict(sorted(extension_counts.items()))
    audit["skipped_extension_counts"] = dict(sorted(skipped_extension_counts.items()))
    audit["skipped_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_archive_member_reason_counts.items()))
    audit["browser_history_event_count"] = sum(
        1 for event in usable_usage_events(events) if str((event.get("data") or {}).get("source_app", "")).endswith("_history")
    )
    audit["browser_history_source_apps"] = sorted(browser_history_source_apps)
    audit["browser_history_source_app_counts"] = dict(sorted(browser_history_source_app_counts.items()))
    return events, audit


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
    return path.suffix.lower() in SUPPORTED_EXTENSIONS or path.name in BROWSER_HISTORY_NAMES


def extension_label(path: Path) -> str:
    if path.name in BROWSER_HISTORY_NAMES:
        return "<browser_history>"
    return path.suffix.lower() or "<none>"


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return parse_zip(path)
    if suffix in {".sqlite", ".sqlite3", ".db"} or path.name in BROWSER_HISTORY_NAMES:
        return parse_browser_history(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".html", ".htm"}:
        return [parse_html(path)]
    return [parse_text(path)]


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    return parse_json_text(text, suffix=path.suffix.lower(), path_label=str(path))


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


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    for key in ("usage", "history", "reads", "favorites", "subscriptions", "searches", "alerts", "items", "records", "data", "list"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
    return [loaded]


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_text(text, suffix=path.suffix.lower(), path_label=str(path))


def parse_table_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    records = [dict(row) for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    for record in records:
        record.setdefault("path", path_label)
    return records


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_browser_history(path: Path) -> List[Dict[str, Any]]:
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        conn.row_factory = sqlite3.Row
        tables = table_names(conn)
        if {"urls", "visits"}.issubset(tables):
            return parse_chromium_history(conn, path)
        if {"history_items", "history_visits"}.issubset(tables):
            return parse_safari_history(conn, path)
        return []
    finally:
        conn.close()


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def parse_chromium_history(conn: sqlite3.Connection, path: Path) -> List[Dict[str, Any]]:
    where_sql, params = financial_domain_where("urls.url")
    query = f"""
        SELECT
            visits.id AS visit_id,
            urls.url AS url,
            urls.title AS title,
            urls.visit_count AS visit_count,
            urls.typed_count AS typed_count,
            visits.visit_time AS visit_time,
            visits.transition AS transition
        FROM visits
        JOIN urls ON visits.url = urls.id
        WHERE {where_sql}
        ORDER BY visits.visit_time DESC
    """
    rows = conn.execute(query, params).fetchall()
    return [
        browser_history_record(
            path=path,
            browser="chromium",
            url=str(row["url"] or ""),
            title=str(row["title"] or ""),
            event_time=chromium_time_to_iso(row["visit_time"]),
            visit_id=row["visit_id"],
            visit_count=row["visit_count"],
            typed_count=row["typed_count"],
            transition=row["transition"],
        )
        for row in rows
        if platform_from_url(str(row["url"] or ""))
    ]


def parse_safari_history(conn: sqlite3.Connection, path: Path) -> List[Dict[str, Any]]:
    where_sql, params = financial_domain_where("history_items.url")
    item_columns = table_columns(conn, "history_items")
    visit_columns = table_columns(conn, "history_visits")
    visit_count_sql = "history_items.visit_count" if "visit_count" in item_columns else "NULL"
    load_successful_sql = "history_visits.load_successful" if "load_successful" in visit_columns else "NULL"
    query = f"""
        SELECT
            history_visits.id AS visit_id,
            history_items.url AS url,
            history_items.title AS title,
            {visit_count_sql} AS visit_count,
            history_visits.visit_time AS visit_time,
            {load_successful_sql} AS load_successful
        FROM history_visits
        JOIN history_items ON history_visits.history_item = history_items.id
        WHERE {where_sql}
        ORDER BY history_visits.visit_time DESC
    """
    rows = conn.execute(query, params).fetchall()
    return [
        browser_history_record(
            path=path,
            browser="safari",
            url=str(row["url"] or ""),
            title=str(row["title"] or ""),
            event_time=safari_time_to_iso(row["visit_time"]),
            visit_id=row["visit_id"],
            visit_count=row["visit_count"],
            transition=row["load_successful"],
            transition_type=safari_load_success_type(row["load_successful"]),
        )
        for row in rows
        if platform_from_url(str(row["url"] or ""))
    ]


def financial_domain_where(column: str) -> tuple[str, List[str]]:
    clauses: List[str] = []
    params: List[str] = []
    for domains in FINANCIAL_NEWS_DOMAINS.values():
        for domain in domains:
            clauses.append(f"LOWER({column}) LIKE ?")
            params.append(f"%{domain}%")
    return " OR ".join(clauses), params


def browser_history_record(
    *,
    path: Path,
    browser: str,
    url: str,
    title: str,
    event_time: Optional[str],
    visit_id: Any,
    visit_count: Any = None,
    typed_count: Any = None,
    transition: Any = None,
    transition_type: Any = None,
) -> Dict[str, Any]:
    return {
        "action_type": "read",
        "platform": platform_from_url(url) or "unknown",
        "source_app": f"{browser}_history",
        "title": title or url,
        "url": url,
        "time": event_time,
        "visit_id": visit_id,
        "visit_count": visit_count,
        "typed_count": typed_count,
        "transition": transition,
        "transition_type": transition_type,
        "path": str(path),
    }


def chromium_time_to_iso(value: Any) -> Optional[str]:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    moment = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=timestamp)
    return moment.astimezone(CN_TZ).isoformat(timespec="seconds")


def safari_time_to_iso(value: Any) -> Optional[str]:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    moment = datetime(2001, 1, 1, tzinfo=UTC) + timedelta(seconds=timestamp)
    return moment.astimezone(CN_TZ).isoformat(timespec="seconds")


def safari_load_success_type(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        status = int(value)
    except (TypeError, ValueError):
        return str(value)
    if status == 1:
        return "load_successful"
    if status == 0:
        return "load_failed"
    return f"load_status_{status}"


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_html_text(html, path_label=str(path), default_title=path.stem)


def parse_html_text(html: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    text = html_to_text(html)
    return {
        "action_type": "read",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(default_title, text),
        "source": meta_content(html, "og:site_name"),
        "url": canonical_url(html) or first_url(html),
        "content": text,
        "path": path_label,
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_text_text(text, path_label=str(path), default_title=path.stem)


def parse_text_text(text: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    return {
        "action_type": "read",
        "title": infer_title(default_title, text),
        "url": first_url(text),
        "content": text,
        "path": path_label,
    }


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    records, _audit = parse_zip_with_audit(path)
    return records


def parse_zip_with_audit(path: Path, *, limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    skipped_reason_counts: Counter[str] = Counter()
    browser_history_source_app_counts: Counter[str] = Counter()
    audit: Dict[str, Any] = {
        "archive": str(path),
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "browser_history_input_count": 0,
        "browser_history_event_count": 0,
        "browser_history_source_apps": [],
        "browser_history_source_app_counts": {},
        "limit_reached": False,
        "member_results": [],
    }
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-financial-news-history-") as tmp_dir:
        tmp_root = Path(tmp_dir)
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
            parser = "browser_history" if is_browser_history_archive_member(member_name) else parser_name_for_zip_member(member_name)
            try:
                if parser == "browser_history":
                    temp_member_path = tmp_root.joinpath(*PurePosixPath(member_name).parts)
                    temp_member_path.parent.mkdir(parents=True, exist_ok=True)
                    temp_member_path.write_bytes(archive.read(member))
                    parsed = parse_browser_history(temp_member_path)
                    audit["browser_history_input_count"] += 1
                    for record in parsed:
                        if isinstance(record, dict):
                            record["path"] = path_label
                else:
                    text = archive.read(member).decode("utf-8-sig", errors="replace")
                    if suffix in {".json", ".jsonl", ".ndjson"}:
                        parsed = parse_json_text(text, suffix=suffix, path_label=path_label)
                    elif suffix in {".csv", ".tsv"}:
                        parsed = parse_table_text(text, suffix=suffix, path_label=path_label)
                    elif suffix in {".html", ".htm"}:
                        parsed = [parse_html_text(text, path_label=path_label, default_title=Path(member_name).stem)]
                    else:
                        parsed = [parse_text_text(text, path_label=path_label, default_title=Path(member_name).stem)]
            except Exception:
                parsed = []
                audit["skipped_archive_member_count"] += 1
                skipped_reason_counts["parse_error"] += 1
                audit["member_results"].append({"member": member_name, "status": "parse_error", "reason": "parse_error", "parser": parser})
                continue
            remaining = None if limit is None else max(limit - len(records), 0)
            emittable = parsed if remaining is None else parsed[:remaining]
            audit["member_results"].append(
                {
                    "member": member_name,
                    "status": "parsed" if parsed else "no_records_parsed",
                    "parser": parser,
                    "parsed_record_count": len(parsed),
                    "emitted_record_count": len(emittable),
                }
            )
            for record in emittable:
                if isinstance(record, dict):
                    record[SOURCE_ARCHIVE_KEY] = str(path)
                    record[SOURCE_MEMBER_KEY] = member_name
                    audit["archive_member_event_count"] += 1
                    source_app = str(record.get("source_app") or "")
                    if source_app.endswith("_history"):
                        browser_history_source_app_counts[source_app] += 1
                        audit["browser_history_event_count"] += 1
            records.extend(emittable)
            if limit is not None and len(records) >= limit:
                audit["limit_reached"] = True
                audit["unvisited_archive_member_count_due_limit"] = max(0, len(members) - audit["archive_member_count"])
                audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
                audit["browser_history_source_app_counts"] = dict(sorted(browser_history_source_app_counts.items()))
                audit["browser_history_source_apps"] = sorted(browser_history_source_app_counts)
                return records, audit
    audit["unvisited_archive_member_count_due_limit"] = 0
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    audit["browser_history_source_app_counts"] = dict(sorted(browser_history_source_app_counts.items()))
    audit["browser_history_source_apps"] = sorted(browser_history_source_app_counts)
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
    if Path(member_name).suffix.lower() not in SUPPORTED_ZIP_EXTENSIONS and not is_browser_history_archive_member(member_name):
        return "unsupported_extension"
    return None


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


def is_browser_history_archive_member(member_name: str) -> bool:
    normalized = normalize_zip_member_name(member_name)
    name = PurePosixPath(normalized).name
    return name in BROWSER_HISTORY_NAMES or Path(name).suffix.lower() in BROWSER_HISTORY_EXTENSIONS


def parser_name_for_zip_member(member_name: str) -> str:
    suffix = Path(member_name).suffix.lower()
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
    if suffix in {".csv", ".tsv"}:
        return "table"
    if suffix in {".html", ".htm"}:
        return "html"
    return "text"


def remaining_limit(limit: Optional[int], events: List[Dict[str, Any]]) -> Optional[int]:
    if limit is None:
        return None
    return max(limit - len(events), 0)


def parser_name_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix in {".sqlite", ".sqlite3", ".db"} or path.name in BROWSER_HISTORY_NAMES:
        return "browser_history"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
    if suffix in {".csv", ".tsv"}:
        return "table"
    if suffix in {".html", ".htm"}:
        return "html"
    return "text"


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
    audit["browser_history_input_count"] += int(archive_audit.get("browser_history_input_count") or 0)
    audit["browser_history_event_count"] += int(archive_audit.get("browser_history_event_count") or 0)
    app_counts = dict(audit.get("browser_history_source_app_counts") or {})
    for app, count in (archive_audit.get("browser_history_source_app_counts") or {}).items():
        app_counts[str(app)] = int(app_counts.get(str(app), 0)) + int(count)
    audit["browser_history_source_app_counts"] = dict(sorted(app_counts.items()))
    audit["browser_history_source_apps"] = sorted(set(audit.get("browser_history_source_apps") or []) | set(app_counts))
    if archive_audit.get("limit_reached"):
        audit["limit_reached"] = True
    for reason, count in (archive_audit.get("skipped_archive_member_reason_counts") or {}).items():
        skipped_reason_counts[str(reason)] += int(count)


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    path_label = first(record, ["path", "file", "source_path"]) or str(path)
    action_type = infer_action_type(record, path_label)
    platform = infer_platform(record, path_label)
    title = first(record, ["title", "name", "subject", "标题", "文章标题"]) or Path(path_label).stem
    url = first(record, ["url", "link", "href", "article_url", "链接", "原文链接"])
    domain = host_for(url)
    text = first(record, ["text", "content", "body", "summary", "abstract", "note", "正文", "内容", "摘要", "备注"]) or ""
    query = first(record, ["query", "keyword", "search", "搜索词", "关键词"])
    query_terms = query_terms_for(query, record)
    tags = tags_for(record)
    symbols = symbols_for(record)
    source_app = first(record, ["source_app", "browser", "client", "app", "客户端", "应用"])
    channel = first(record, ["channel", "column", "category", "栏目", "频道", "分类"])
    subscription_target = first(record, ["subscription_target", "subscribe_target", "topic", "subject", "订阅对象", "关注栏目", "订阅栏目"]) or (
        channel if action_type == "subscribe" else None
    )
    alert_condition = first(record, ["alert_condition", "condition", "trigger", "alert_rule", "提醒条件", "预警条件", "触发条件"])
    notification_channel = first(record, ["notification_channel", "push_channel", "notify_channel", "通知渠道", "推送渠道"])
    referrer = first(record, ["referrer", "referer", "from_url", "source_url", "来源页面", "前序页面"])
    session_id = first(record, ["session_id", "visit_id", "trace_id", "会话ID", "访问ID"])
    dwell_seconds = int_value(first(record, ["dwell_seconds", "read_duration_seconds", "duration_seconds", "stay_seconds", "停留秒数", "阅读秒数", "停留时长", "阅读时长"]))
    visit_count = int_value(first(record, ["visit_count", "访问次数"]))
    typed_count = int_value(first(record, ["typed_count", "输入访问次数"]))
    transition = first(record, ["transition", "访问方式"])
    transition_type = first(record, ["transition_type", "访问方式类型"]) or browser_transition_type(transition)
    usage_topics, usage_topic_terms = classify_usage_topics(
        record,
        title=title,
        text=text,
        query=query,
        tags=tags,
        symbols=symbols,
    )
    event_time = first(
        record,
        [
            "time",
            "date",
            "read_at",
            "saved_at",
            "favorited_at",
            "created_at",
            "updated_at",
            "last_visit_time",
            "时间",
            "日期",
            "阅读时间",
            "收藏时间",
        ],
    )
    data = {
        "action_type": action_type,
        "platform": platform,
        "usage_topics": usage_topics,
        "primary_usage_topic": usage_topics[0] if usage_topics else "unclassified_usage_topic",
        "usage_topic_terms": usage_topic_terms,
        "title": title,
        "url": url,
        "domain": domain,
        "source_app": source_app,
        "source": first(record, ["source", "source_name", "publisher", "author", "来源", "作者"]),
        "channel": channel,
        "query": query,
        "query_terms": query_terms,
        "subscription_target": subscription_target,
        "alert_condition": alert_condition,
        "notification_channel": notification_channel,
        "trigger_source": trigger_source_for(record, path_label=path_label, source_app=source_app),
        "referrer": referrer,
        "session_id": session_id,
        "dwell_seconds": dwell_seconds,
        "symbols": symbols,
        "tags": tags,
        "visit_count": visit_count,
        "typed_count": typed_count,
        "transition": transition,
        "transition_type": transition_type,
        "article_id": article_id_for(url),
        "text_preview": text[:TEXT_PREVIEW_MAX_CHARS],
        "has_text": bool(text),
        "text_length": len(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}
    raw_ref = {
        "path": path_label,
        "row": row,
        "platform": platform,
        "url": url,
        "source_app": data.get("source_app"),
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_label, row, action_type, platform, title, url, event_time, query),
        "collector": COLLECTOR,
        "source": "财经资讯用户使用痕迹",
        "owner_scope": "personal",
        "kind": kind_for_action(action_type),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["none"],
        },
        "wiki_targets": wiki_targets_for_action(action_type),
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "财经资讯使用痕迹授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "action_type": "collector_gap",
            "gap": reason,
            "message": "No user-authorized financial news usage export or local input was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["none"]},
        "wiki_targets": ["investor.data_quality.collection_gaps"],
    }


def infer_action_type(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["action_type", "activity_type", "action", "event", "type", "动作", "行为", "类型"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path_label).lower()
    probe = (explicit or text).lower()
    if any(token in probe for token in ("favorite", "fav", "bookmark", "收藏", "星标", "saved")):
        return "favorite"
    if any(token in probe for token in ("subscribe", "subscription", "订阅", "关注栏目", "关注")):
        return "subscribe"
    if any(token in probe for token in ("search", "query", "搜索", "检索")):
        return "search"
    if any(token in probe for token in ("alert", "remind", "提醒", "预警", "自选提醒")):
        return "alert"
    if any(token in probe for token in ("read", "view", "visit", "browse", "阅读", "浏览", "查看", "访问")):
        return "read"
    return "read"


def infer_platform(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["platform", "app", "provider", "source_app", "平台", "应用"])
    explicit_match = platform_from_text(explicit or "")
    if explicit_match:
        return explicit_match
    url_match = platform_from_url(first(record, ["url", "link", "href", "article_url", "链接", "原文链接"]) or "")
    if url_match:
        return url_match
    text = " ".join(str(value) for value in record.values() if value is not None) + " " + str(path_label)
    text_match = platform_from_text(text)
    return text_match or "unknown"


def platform_from_text(text: str) -> Optional[str]:
    lowered = text.lower()
    if "cls" in lowered or "cailianpress" in lowered or "财联社" in text:
        return "cls"
    if "wallstreetcn" in lowered or "wallstreet" in lowered or "wscn" in lowered or "华尔街见闻" in text:
        return "wallstreetcn"
    if "gelonghui" in lowered or "格隆汇" in text:
        return "gelonghui"
    return None


def platform_from_url(url: str) -> Optional[str]:
    host = host_for(url)
    if not host:
        return None
    for platform, domains in FINANCIAL_NEWS_DOMAINS.items():
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            return platform
    return None


def host_for(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    return host.split(":", 1)[0] or None


def article_id_for(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    return path_parts[-1] if path_parts else None


def kind_for_action(action_type: str) -> str:
    if action_type in {"read", "favorite"}:
        return "note"
    if action_type == "subscribe":
        return "profile"
    if action_type == "alert":
        return "watchlist"
    return "other"


def wiki_targets_for_action(action_type: str) -> List[str]:
    targets = {
        "read": ["investor.information_sources.news_consumption", "investor.capability_circle.attention_universe"],
        "favorite": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "subscribe": ["investor.information_sources.news_consumption", "investor.capability_circle.attention_universe"],
        "search": ["investor.research_consumption.workflow", "investor.capability_circle.attention_universe"],
        "alert": ["investor.decision_framework.monitoring_rules", "investor.execution.watchlist_alerts"],
    }
    return targets.get(action_type, ["investor.data_quality.collection_gaps"])


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    action_counts = Counter((event.get("data") or {}).get("action_type", "unknown") for event in events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in events)
    gap_only = bool(events) and set(action_counts) == {"collector_gap"}
    observed_platforms = sorted(platform for platform, count in platform_counts.items() if count and platform != "unknown")
    observed_expected_platforms = [platform for platform in EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS if platform_counts.get(platform)]
    missing_expected_platforms = [platform for platform in EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS if not platform_counts.get(platform)]
    unknown_platform_count = sum(count for platform, count in platform_counts.items() if platform not in EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS)
    observed_actions = sorted(action for action, count in action_counts.items() if count and action not in {"collector_gap", "unknown"})
    observed_expected_actions = [action for action in EXPECTED_FINANCIAL_NEWS_ACTIONS if action_counts.get(action)]
    missing_expected_actions = [action for action in EXPECTED_FINANCIAL_NEWS_ACTIONS if not action_counts.get(action)]
    unknown_action_count = sum(count for action, count in action_counts.items() if action not in EXPECTED_FINANCIAL_NEWS_ACTIONS and action != "collector_gap")
    return {
        "schema": "financial_news.usage.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "platform_coverage": {
            "expected_p1_platforms": list(EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS),
            "observed_platforms": observed_platforms,
            "observed_expected_platforms": observed_expected_platforms,
            "missing_expected_platforms": missing_expected_platforms,
            "platform_counts": dict(sorted(platform_counts.items())),
            "unknown_platform_count": unknown_platform_count,
            "real_account_validation": False,
        },
        "action_coverage": {
            "expected_p1_actions": list(EXPECTED_FINANCIAL_NEWS_ACTIONS),
            "observed_actions": observed_actions,
            "observed_expected_actions": observed_expected_actions,
            "missing_expected_actions": missing_expected_actions,
            "action_counts": dict(sorted(action_counts.items())),
            "unknown_action_count": unknown_action_count,
            "real_account_validation": False,
        },
        "field_coverage": field_coverage(events),
        "usage_surface_summary": usage_surface_summary(events),
        "usage_behavior_summary": usage_behavior_summary(events),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "usage_boundary_proof": build_usage_boundary_proof(
            events,
            collection_audit=collection_audit,
            missing_expected_platforms=missing_expected_platforms,
            missing_expected_actions=missing_expected_actions,
            gap_only=gap_only,
        ),
        "content_policy": {
            "full_public_news_crawl": False,
            "full_article_content_included_by_default": False,
            "text_preview_max_chars": TEXT_PREVIEW_MAX_CHARS,
            "browser_history_domain_filtering": True,
            "public_news_as_personal_fact": False,
        },
        "evidence_policy": {
            "vertical_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "source_is_public_news_crawler": False,
            "personal_usage_only": True,
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": "needs_financial_news_usage_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_usage_history": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "platform_coverage_status": coverage_status(events, missing_expected_platforms, "platform"),
            "action_coverage_status": coverage_status(events, missing_expected_actions, "action"),
            "next_action": "Provide authorized CLS/WallstreetCN/Gelonghui usage export." if gap_only else "Use as investor information-consumption evidence; continue real app/account validation.",
        },
    }


def build_usage_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    collection_audit: Optional[Dict[str, Any]],
    missing_expected_platforms: List[str],
    missing_expected_actions: List[str],
    gap_only: bool,
) -> Dict[str, Any]:
    usage_events = usable_usage_events(events)
    action_counts = Counter((event.get("data") or {}).get("action_type", "unknown") for event in usage_events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in usage_events)
    observed_expected_platforms = [platform for platform in EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS if platform_counts.get(platform)]
    observed_expected_actions = [action for action in EXPECTED_FINANCIAL_NEWS_ACTIONS if action_counts.get(action)]
    audit = source_audit(events, collection_audit=collection_audit)
    surface = usage_surface_summary(events)
    return {
        "source_type": "authorized_financial_news_usage_export_or_browser_history_copy",
        "proof_level": usage_boundary_proof_level(
            usage_events,
            audit=audit,
            surface=surface,
            missing_expected_platforms=missing_expected_platforms,
            missing_expected_actions=missing_expected_actions,
            gap_only=gap_only,
        ),
        "event_count": len(usage_events),
        "parsed_record_count": audit.get("parsed_record_count", len(usage_events)),
        "emitted_event_count": audit.get("emitted_event_count", len(events)),
        "input_boundary": {
            "input_count": audit.get("input_count", 0),
            "requested_inputs": audit.get("requested_inputs", []),
            "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
            "input_missing_count": audit.get("input_missing_count", 0),
            "skipped_file_count": audit.get("skipped_file_count", 0),
            "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
            "limit": audit.get("limit"),
            "limit_reached": audit.get("limit_reached", False),
        },
        "platform_action_boundary": {
            "expected_platforms": list(EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS),
            "observed_expected_platforms": observed_expected_platforms,
            "missing_expected_platforms": missing_expected_platforms,
            "platform_counts": dict(sorted(platform_counts.items())),
            "expected_actions": list(EXPECTED_FINANCIAL_NEWS_ACTIONS),
            "observed_expected_actions": observed_expected_actions,
            "missing_expected_actions": missing_expected_actions,
            "action_counts": dict(sorted(action_counts.items())),
        },
        "usage_topic_boundary": {
            "expected_usage_topics": surface.get("expected_usage_topics", []),
            "usage_topic_counts": surface.get("usage_topic_counts", {}),
            "missing_expected_usage_topics": surface.get("missing_expected_usage_topics", []),
            "events_with_usage_topics": surface.get("events_with_usage_topics", 0),
            "platform_topic_counts": surface.get("platform_topic_counts", {}),
        },
        "source_artifact_boundary": {
            "source_ref_count": audit.get("source_ref_count", 0),
            "archive_count": audit.get("archive_count", 0),
            "archive_member_count": audit.get("archive_member_count", 0),
            "archive_member_event_count": audit.get("archive_member_event_count", 0),
            "skipped_archive_member_count": audit.get("skipped_archive_member_count", 0),
            "skipped_archive_member_reason_counts": audit.get("skipped_archive_member_reason_counts", {}),
            "browser_history_input_count": audit.get("browser_history_input_count", 0),
            "browser_history_event_count": audit.get("browser_history_event_count", 0),
            "browser_history_source_apps": audit.get("browser_history_source_apps", []),
            "browser_history_source_app_counts": audit.get("browser_history_source_app_counts", {}),
            "archive_path_traversal_members_collected": audit.get("archive_path_traversal_members_collected", False),
            "windows_drive_archive_members_collected": audit.get("windows_drive_archive_members_collected", False),
        },
        "content_pointer_boundary": {
            "events_with_url": surface.get("events_with_url", 0),
            "events_with_domain": surface.get("events_with_domain", 0),
            "events_with_source_app": surface.get("events_with_source_app", 0),
            "events_with_source_or_channel": surface.get("events_with_source_or_channel", 0),
            "events_with_query": surface.get("events_with_query", 0),
            "events_with_symbols": surface.get("events_with_symbols", 0),
            "events_with_tags": surface.get("events_with_tags", 0),
            "events_with_text": surface.get("events_with_text", 0),
            "alert_event_count": surface.get("alert_event_count", 0),
            "subscription_event_count": surface.get("subscription_event_count", 0),
        },
        "usage_behavior_boundary": usage_behavior_summary(events),
        "complete_usage_history_claimed": False,
        "complete_account_boundary_claimed": False,
        "public_news_full_crawl_claimed": False,
        "public_article_body_mirrored": False,
        "platform_wide_data_claimed": False,
        "unrelated_browser_history_collected": False,
        "browser_history_domain_filtering": True,
        "direct_app_or_account_reconnect": False,
        "collector_writes_wiki_directly": False,
        "personal_usage_only": True,
        "can_enter_finclaw": bool(usage_events) and not gap_only,
    }


def usage_boundary_proof_level(
    usage_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    surface: Dict[str, Any],
    missing_expected_platforms: List[str],
    missing_expected_actions: List[str],
    gap_only: bool,
) -> str:
    if not usage_events or gap_only:
        if int(audit.get("input_missing_count") or 0) > 0 or int(audit.get("input_count") or 0) == 0:
            return "no_authorized_financial_news_usage_input"
        return "no_usable_financial_news_usage_records"
    if int(surface.get("browser_history_event_count") or 0) > 0:
        return "authorized_financial_news_usage_with_browser_history"
    behavior = usage_behavior_summary(usage_events)
    if any(
        int(behavior.get(key) or 0) > 0
        for key in (
            "events_with_alert_condition",
            "events_with_subscription_target",
            "events_with_query_terms",
            "events_with_dwell_seconds",
            "events_with_referrer",
            "events_with_notification_channel",
            "events_with_session_id",
        )
    ):
        return "authorized_financial_news_usage_with_behavior_surface"
    if not missing_expected_platforms and not missing_expected_actions and not surface.get("missing_expected_usage_topics"):
        return "authorized_financial_news_usage_with_platform_action_topic_coverage"
    return "authorized_financial_news_usage_partial_coverage"


def coverage_status(events: List[Dict[str, Any]], missing_expected: List[str], noun: str) -> str:
    if not events or all((event.get("data") or {}).get("action_type") == "collector_gap" for event in events):
        return f"no_{noun}_observed"
    if not missing_expected:
        return f"all_expected_{noun}s_observed"
    return f"partial_expected_{noun}s_observed"


def usable_usage_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [event for event in events if (event.get("data") or {}).get("action_type") != "collector_gap"]


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usage_events = usable_usage_events(events)
    field_counts = {
        field: sum(1 for event in usage_events if usage_field_present(event, field))
        for field in FINANCIAL_NEWS_RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(FINANCIAL_NEWS_RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_text": sum(1 for event in usage_events if (event.get("data") or {}).get("has_text")),
    }


def usage_field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    value = (event.get("data") or {}).get(field)
    return value not in (None, "", [], {})


def usage_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usage_events = usable_usage_events(events)
    usage_topic_counts: Counter[str] = Counter()
    primary_topic_counts: Counter[str] = Counter()
    platform_topic_counts: Counter[str] = Counter()
    for event in usage_events:
        data = event.get("data") or {}
        topics = data.get("usage_topics") if isinstance(data.get("usage_topics"), list) else []
        if not topics:
            topics = ["unclassified_usage_topic"]
        for topic in topics:
            usage_topic_counts[str(topic)] += 1
            platform_topic_counts[f"{data.get('platform', 'unknown')}:{topic}"] += 1
        primary_topic_counts[str(data.get("primary_usage_topic") or topics[0])] += 1
    return {
        "usage_event_count": len(usage_events),
        "expected_usage_topics": list(FINANCIAL_NEWS_TOPIC_ORDER[:-1]),
        "usage_topic_counts": ordered_counts(usage_topic_counts, FINANCIAL_NEWS_TOPIC_ORDER),
        "primary_usage_topic_counts": ordered_counts(primary_topic_counts, FINANCIAL_NEWS_TOPIC_ORDER),
        "missing_expected_usage_topics": [
            topic for topic in FINANCIAL_NEWS_TOPIC_ORDER[:-1] if usage_topic_counts.get(topic, 0) == 0
        ],
        "platform_topic_counts": dict(sorted(platform_topic_counts.items())),
        "events_with_usage_topics": sum(1 for event in usage_events if (event.get("data") or {}).get("usage_topics")),
        "events_with_url": sum(1 for event in usage_events if (event.get("data") or {}).get("url")),
        "events_with_domain": sum(1 for event in usage_events if (event.get("data") or {}).get("domain")),
        "events_with_source_app": sum(1 for event in usage_events if (event.get("data") or {}).get("source_app")),
        "events_with_source_or_channel": sum(
            1
            for event in usage_events
            if (event.get("data") or {}).get("source") or (event.get("data") or {}).get("channel")
        ),
        "events_with_query": sum(1 for event in usage_events if (event.get("data") or {}).get("query")),
        "events_with_symbols": sum(1 for event in usage_events if (event.get("data") or {}).get("symbols")),
        "events_with_tags": sum(1 for event in usage_events if (event.get("data") or {}).get("tags")),
        "events_with_text": sum(1 for event in usage_events if (event.get("data") or {}).get("has_text")),
        "browser_history_event_count": sum(
            1
            for event in usage_events
            if str((event.get("data") or {}).get("source_app", "")).endswith("_history")
        ),
        "alert_event_count": sum(1 for event in usage_events if (event.get("data") or {}).get("action_type") == "alert"),
        "subscription_event_count": sum(
            1 for event in usage_events if (event.get("data") or {}).get("action_type") == "subscribe"
        ),
    }


def usage_behavior_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usage_events = usable_usage_events(events)
    trigger_source_counts: Counter[str] = Counter()
    transition_type_counts: Counter[str] = Counter()
    query_terms = set()
    subscription_targets = set()
    alert_conditions = set()
    dwell_values: List[int] = []
    visit_values: List[int] = []
    typed_values: List[int] = []
    for event in usage_events:
        data = event.get("data") or {}
        if data.get("trigger_source"):
            trigger_source_counts[str(data["trigger_source"])] += 1
        if data.get("transition_type"):
            transition_type_counts[str(data["transition_type"])] += 1
        for term in data.get("query_terms") or []:
            if term:
                query_terms.add(str(term))
        if data.get("subscription_target"):
            subscription_targets.add(str(data["subscription_target"]))
        if data.get("alert_condition"):
            alert_conditions.add(str(data["alert_condition"]))
        dwell = int_value(data.get("dwell_seconds"))
        if dwell is not None:
            dwell_values.append(dwell)
        visit_count = int_value(data.get("visit_count"))
        if visit_count is not None:
            visit_values.append(visit_count)
        typed_count = int_value(data.get("typed_count"))
        if typed_count is not None:
            typed_values.append(typed_count)
    return {
        "events_with_trigger_source": sum(1 for event in usage_events if (event.get("data") or {}).get("trigger_source")),
        "events_with_query_terms": sum(1 for event in usage_events if (event.get("data") or {}).get("query_terms")),
        "query_term_count": len(query_terms),
        "events_with_subscription_target": sum(1 for event in usage_events if (event.get("data") or {}).get("subscription_target")),
        "subscription_target_count": len(subscription_targets),
        "events_with_alert_condition": sum(1 for event in usage_events if (event.get("data") or {}).get("alert_condition")),
        "alert_condition_count": len(alert_conditions),
        "events_with_notification_channel": sum(1 for event in usage_events if (event.get("data") or {}).get("notification_channel")),
        "events_with_referrer": sum(1 for event in usage_events if (event.get("data") or {}).get("referrer")),
        "events_with_session_id": sum(1 for event in usage_events if (event.get("data") or {}).get("session_id")),
        "events_with_dwell_seconds": len(dwell_values),
        "average_dwell_seconds": round(sum(dwell_values) / len(dwell_values), 2) if dwell_values else None,
        "events_with_visit_count": len(visit_values),
        "total_visit_count": sum(visit_values) if visit_values else 0,
        "events_with_typed_count": len(typed_values),
        "total_typed_count": sum(typed_values) if typed_values else 0,
        "trigger_source_counts": dict(sorted(trigger_source_counts.items())),
        "transition_type_counts": dict(sorted(transition_type_counts.items())),
    }


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    usage_events = usable_usage_events(events)
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in usage_events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    browser_history_apps = sorted(
        {
            str((event.get("data") or {}).get("source_app"))
            for event in usage_events
            if str((event.get("data") or {}).get("source_app", "")).endswith("_history")
        }
    )
    browser_history_app_counts = Counter(
        str((event.get("data") or {}).get("source_app"))
        for event in usage_events
        if str((event.get("data") or {}).get("source_app", "")).endswith("_history")
    )
    audit = {
        "source_ref_count": sum(
            1
            for event in usage_events
            if (event.get("raw_ref") or {}).get("path") or (event.get("raw_ref") or {}).get("url")
        ),
        "archive_member_event_count": sum(1 for event in usage_events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "browser_history_event_count": len(
            [
                event
                for event in usage_events
                if str((event.get("data") or {}).get("source_app", "")).endswith("_history")
            ]
        ),
        "browser_history_source_apps": browser_history_apps,
        "browser_history_source_app_counts": dict(sorted(browser_history_app_counts.items())),
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
    }
    if collection_audit:
        audit.update(collection_audit)
        audit["source_ref_count"] = max(
            int(audit.get("source_ref_count") or 0),
            sum(1 for event in usage_events if (event.get("raw_ref") or {}).get("path") or (event.get("raw_ref") or {}).get("url")),
        )
        audit["archive_member_event_count"] = max(
            int(audit.get("archive_member_event_count") or 0),
            sum(1 for event in usage_events if (event.get("raw_ref") or {}).get("archive_member")),
        )
        audit["browser_history_event_count"] = max(
            int(audit.get("browser_history_event_count") or 0),
            len([event for event in usage_events if str((event.get("data") or {}).get("source_app", "")).endswith("_history")]),
        )
        audit["browser_history_source_apps"] = sorted(set(audit.get("browser_history_source_apps") or []) | set(browser_history_apps))
        if browser_history_app_counts:
            audit["browser_history_source_app_counts"] = dict(sorted(browser_history_app_counts.items()))
        audit["archive_path_traversal_members_collected"] = False
        audit["windows_drive_archive_members_collected"] = False
    return audit


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    usable_events = 0
    for event in events:
        if (event.get("data") or {}).get("action_type") == "collector_gap":
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
            "source_is_public_news_crawler": False,
            "personal_usage_only": True,
            "public_news_content_mirror": False,
            "usable_event_count": usable_events,
            "source_platforms": sorted(
                {
                    str((event.get("data") or {}).get("platform"))
                    for event in events
                    if (event.get("data") or {}).get("platform")
                }
            ),
            "source_actions": sorted(
                {
                    str((event.get("data") or {}).get("action_type"))
                    for event in events
                    if (event.get("data") or {}).get("action_type") not in (None, "collector_gap")
                }
            ),
            "usage_surface_summary": usage_surface_summary(events),
            "usage_behavior_summary": usage_behavior_summary(events),
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }
    return augment_evidence_with_dimensions(evidence, events, INVESTOR_WIKI_SUBDIMENSION_RULES)


def classify_usage_topics(
    record: Dict[str, Any],
    *,
    title: str,
    text: str,
    query: Optional[str],
    tags: List[str],
    symbols: List[str],
) -> Tuple[List[str], Dict[str, List[str]]]:
    parts: List[str] = [title, text, query or "", " ".join(tags), " ".join(symbols)]
    for key in ("source", "source_name", "publisher", "author", "来源", "作者", "channel", "column", "category", "栏目", "频道", "分类"):
        value = record.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    searchable = "\n".join(parts)
    lowered = searchable.lower()
    matches: Dict[str, List[str]] = {}
    for topic in FINANCIAL_NEWS_TOPIC_ORDER[:-1]:
        hits = topic_term_hits(FINANCIAL_NEWS_TOPIC_TERMS[topic], searchable, lowered)
        if hits:
            matches[topic] = hits
    topics = [topic for topic in FINANCIAL_NEWS_TOPIC_ORDER[:-1] if topic in matches]
    return topics, {topic: matches[topic][:8] for topic in topics}


def topic_term_hits(terms: Iterable[str], text: str, lowered: str) -> List[str]:
    hits: List[str] = []
    for term in sorted(terms):
        if term.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", lowered):
                hits.append(term)
        elif term in text:
            hits.append(term)
    return hits


def ordered_counts(counts: Counter[str], order: Iterable[str]) -> Dict[str, int]:
    result = {key: counts[key] for key in order if counts.get(key)}
    for key, value in sorted(counts.items()):
        if key not in result:
            result[key] = value
    return result


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def int_value(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    number = float(match.group(0))
    text = str(value).lower()
    if "小时" in text or "hour" in text:
        number *= 3600
    elif "分钟" in text or "min" in text:
        number *= 60
    return max(0, int(round(number)))


def query_terms_for(query: Optional[str], record: Dict[str, Any]) -> List[str]:
    raw = record.get("query_terms") or record.get("keywords") or record.get("搜索词列表") or query or []
    if isinstance(raw, str):
        return split_terms(raw)
    if isinstance(raw, list):
        return clean_list_items(raw, ["term", "keyword", "name", "搜索词", "关键词"])
    return []


def trigger_source_for(record: Dict[str, Any], *, path_label: str, source_app: Optional[str]) -> str:
    explicit = first(record, ["trigger_source", "entry_point", "origin", "入口", "触发来源"])
    if explicit:
        return explicit
    source_text = (source_app or "").lower()
    path_text = path_label.lower()
    if source_text.endswith("_history"):
        return "browser_history"
    if "alert" in path_text or "提醒" in path_label or "预警" in path_label:
        return "alert_export"
    if source_app:
        return "app_export"
    if "::" in path_label:
        return "archive_export"
    if path_text.endswith((".html", ".htm", ".md", ".markdown", ".txt")):
        return "saved_page"
    return "authorized_export"


def browser_transition_type(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        transition = int(str(value))
    except ValueError:
        return str(value)
    core = transition & 0xFF
    return {
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
    }.get(core, "unknown")


def tags_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("tags") or record.get("labels") or record.get("标签") or []
    if isinstance(raw, str):
        return split_terms(raw)
    if isinstance(raw, list):
        return clean_list_items(raw, ["name", "title", "标签", "名称"])
    return []


def symbols_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("symbols") or record.get("codes") or record.get("stocks") or record.get("证券") or record.get("股票") or []
    if isinstance(raw, str):
        return split_terms(raw)
    if isinstance(raw, list):
        return clean_list_items(raw, ["symbol", "code", "name", "证券代码", "股票代码", "名称"])
    return []


def split_terms(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,，、;；|\n]+", text) if item.strip()]


def clean_list_items(items: List[Any], keys: List[str]) -> List[str]:
    cleaned: List[str] = []
    for item in items:
        if isinstance(item, dict):
            value = first(item, keys)
        else:
            value = str(item)
        if value and value != "None":
            cleaned.append(value.strip())
    return cleaned


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


def title_tag(html: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(strip_tags(match.group(1))) if match else None


def meta_content(html: str, name: str) -> Optional[str]:
    pattern = (
        r"<meta[^>]+(?:name|property)=[\"']"
        + re.escape(name)
        + r"[\"'][^>]+content=[\"']([^\"']+)[\"'][^>]*>"
    )
    match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(unescape(match.group(1))) if match else None


def canonical_url(html: str) -> Optional[str]:
    match = re.search(r"<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"']([^\"']+)[\"'][^>]*>", html, flags=re.IGNORECASE)
    return unescape(match.group(1)).strip() if match else None


def first_url(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s<>'\")]+", text)
    return match.group(0) if match else None


def html_to_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(strip_tags(html))


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(value))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def infer_title(default_title: str, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return default_title


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
