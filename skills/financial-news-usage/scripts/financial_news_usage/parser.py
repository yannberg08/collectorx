"""Parse user-authorized financial news usage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "financial-news-usage"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".html", ".htm", ".md", ".markdown", ".txt"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")


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
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".html", ".htm"}:
        return [parse_html(path)]
    return [parse_text(path)]


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
    for key in ("usage", "history", "reads", "favorites", "subscriptions", "searches", "alerts", "items", "records", "data", "list"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
    return [loaded]


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [dict(row) for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "action_type": "read",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(path, text),
        "source": meta_content(html, "og:site_name"),
        "url": canonical_url(html) or first_url(html),
        "content": text,
        "path": str(path),
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "action_type": "read",
        "title": infer_title(path, text),
        "url": first_url(text),
        "content": text,
        "path": str(path),
    }


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    action_type = infer_action_type(record, path)
    platform = infer_platform(record, path)
    title = first(record, ["title", "name", "subject", "标题", "文章标题"]) or path.stem
    url = first(record, ["url", "link", "href", "article_url", "链接", "原文链接"])
    text = first(record, ["text", "content", "body", "summary", "abstract", "note", "正文", "内容", "摘要", "备注"]) or ""
    query = first(record, ["query", "keyword", "search", "搜索词", "关键词"])
    event_time = first(record, ["time", "date", "read_at", "saved_at", "favorited_at", "created_at", "updated_at", "时间", "日期", "阅读时间", "收藏时间"])
    data = {
        "action_type": action_type,
        "platform": platform,
        "title": title,
        "url": url,
        "source": first(record, ["source", "source_name", "publisher", "author", "来源", "作者"]),
        "channel": first(record, ["channel", "column", "category", "栏目", "频道", "分类"]),
        "query": query,
        "symbols": symbols_for(record),
        "tags": tags_for(record),
        "text_preview": text[:1200],
        "has_text": bool(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, action_type, platform, title, url, event_time, query),
        "collector": COLLECTOR,
        "source": "财经资讯用户使用痕迹",
        "owner_scope": "personal",
        "kind": kind_for_action(action_type),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "row": row,
            "platform": platform,
            "url": url,
        },
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


def infer_action_type(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["action_type", "activity_type", "action", "event", "type", "动作", "行为", "类型"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path).lower()
    probe = (explicit or text).lower()
    if any(token in probe for token in ("favorite", "fav", "收藏", "星标", "saved")):
        return "favorite"
    if any(token in probe for token in ("subscribe", "subscription", "订阅", "关注栏目", "关注")):
        return "subscribe"
    if any(token in probe for token in ("search", "query", "搜索", "检索")):
        return "search"
    if any(token in probe for token in ("alert", "remind", "提醒", "预警", "自选提醒")):
        return "alert"
    return "read"


def infer_platform(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["platform", "app", "provider", "source_app", "平台", "应用"])
    text = " ".join(str(value) for value in record.values() if value is not None) + " " + str(path)
    lowered = text.lower()
    if explicit:
        low = explicit.lower()
        if "cls" in low or "财联社" in explicit:
            return "cls"
        if "wallstreet" in low or "wscn" in low or "华尔街见闻" in explicit:
            return "wallstreetcn"
        if "gelonghui" in low or "格隆汇" in explicit:
            return "gelonghui"
    if "cls.cn" in lowered or "财联社" in text:
        return "cls"
    if "wallstreetcn" in lowered or "wscn" in lowered or "华尔街见闻" in text:
        return "wallstreetcn"
    if "gelonghui" in lowered or "格隆汇" in text:
        return "gelonghui"
    return "unknown"


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
    return {
        "schema": "financial_news.usage.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "collection_readiness": {
            "status": "needs_financial_news_usage_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_usage_history": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized CLS/WallstreetCN/Gelonghui usage export." if gap_only else "Use as investor information-consumption evidence; continue real app/account validation.",
        },
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
        return [item.strip() for item in raw.replace("，", ",").replace("、", ",").split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item.get("name") if isinstance(item, dict) else item) for item in raw if str(item)]
    return []


def symbols_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("symbols") or record.get("codes") or record.get("stocks") or record.get("证券") or record.get("股票") or []
    if isinstance(raw, str):
        return [item.strip() for item in raw.replace("，", ",").replace("、", ",").split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item.get("symbol") or item.get("code") if isinstance(item, dict) else item) for item in raw if str(item)]
    return []


def sanitized(record: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in record.items():
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
            continue
        clean[key] = value
    return clean


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


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return path.stem


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
