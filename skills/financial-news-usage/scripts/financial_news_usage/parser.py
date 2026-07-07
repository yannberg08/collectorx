"""Parse user-authorized financial news usage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlparse


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
SUPPORTED_ZIP_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS - {".sqlite", ".sqlite3", ".db"}
BROWSER_HISTORY_NAMES = {"History", "History.db"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
FINANCIAL_NEWS_DOMAINS = {
    "cls": ("cls.cn", "cailianpress.com"),
    "wallstreetcn": ("wallstreetcn.com", "wscn.com"),
    "gelonghui": ("gelonghui.com", "gelonghui.cn"),
}
EXPECTED_P1_FINANCIAL_NEWS_PLATFORMS = ("cls", "wallstreetcn", "gelonghui")
EXPECTED_FINANCIAL_NEWS_ACTIONS = ("read", "favorite", "search", "subscribe", "alert")
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
TEXT_PREVIEW_MAX_CHARS = 1200
FINANCIAL_NEWS_RECOMMENDED_FIELDS = (
    "action_type",
    "platform",
    "title",
    "url",
    "domain",
    "source_app",
    "source",
    "channel",
    "query",
    "symbols",
    "tags",
    "article_id",
    "text_preview",
    "time",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="financial_news_usage_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events or [gap_event(collected_at=collected_at, reason="financial_news_usage_records_empty")]


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
    query = f"""
        SELECT
            history_visits.id AS visit_id,
            history_items.url AS url,
            history_items.title AS title,
            history_visits.visit_time AS visit_time
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
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: normalize_zip_member_name(item.filename)):
            if should_skip_zip_member(member):
                continue
            member_name = normalize_zip_member_name(member.filename)
            suffix = Path(member_name).suffix.lower()
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            path_label = f"{path}::{member_name}"
            try:
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
            for record in parsed:
                if isinstance(record, dict):
                    record[SOURCE_ARCHIVE_KEY] = str(path)
                    record[SOURCE_MEMBER_KEY] = member_name
            records.extend(parsed)
    return records


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    member_name = normalize_zip_member_name(member.filename)
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(member.filename)
    if member.is_dir():
        return True
    if member_path.is_absolute() or windows_path.drive or ".." in member_path.parts:
        return True
    return Path(member_name).suffix.lower() not in SUPPORTED_ZIP_EXTENSIONS


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    path_label = first(record, ["path", "file", "source_path"]) or str(path)
    action_type = infer_action_type(record, path_label)
    platform = infer_platform(record, path_label)
    title = first(record, ["title", "name", "subject", "标题", "文章标题"]) or Path(path_label).stem
    url = first(record, ["url", "link", "href", "article_url", "链接", "原文链接"])
    domain = host_for(url)
    text = first(record, ["text", "content", "body", "summary", "abstract", "note", "正文", "内容", "摘要", "备注"]) or ""
    query = first(record, ["query", "keyword", "search", "搜索词", "关键词"])
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
        "title": title,
        "url": url,
        "domain": domain,
        "source_app": first(record, ["source_app", "browser", "client", "app", "客户端", "应用"]),
        "source": first(record, ["source", "source_name", "publisher", "author", "来源", "作者"]),
        "channel": first(record, ["channel", "column", "category", "栏目", "频道", "分类"]),
        "query": query,
        "symbols": symbols_for(record),
        "tags": tags_for(record),
        "visit_count": first(record, ["visit_count", "访问次数"]),
        "typed_count": first(record, ["typed_count", "输入访问次数"]),
        "transition": first(record, ["transition", "访问方式"]),
        "article_id": article_id_for(url),
        "text_preview": text[:TEXT_PREVIEW_MAX_CHARS],
        "has_text": bool(text),
        "text_length": len(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
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


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
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
        "source_audit": source_audit(events),
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


def usage_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, int]:
    usage_events = usable_usage_events(events)
    return {
        "usage_event_count": len(usage_events),
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


def source_audit(events: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    return {
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
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    usable_events = 0
    for event in events:
        if (event.get("data") or {}).get("action_type") == "collector_gap":
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
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


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
