"""Parse user-authorized social activity exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlparse

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency for runtime installs
    openpyxl = None

COLLECTOR = "social-activity"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".ndjson",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xlsm",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
CONTENT_KEY_FRAGMENTS = ("content", "body", "正文", "全文", "评论", "comment")
SECTION_ACTION_TYPES = {
    "activities": None,
    "history": "watch",
    "watch_history": "watch",
    "favorites": "favorite",
    "collections": "favorite",
    "likes": "like",
    "follows": "follow",
    "following": "follow",
    "comments": "comment",
    "shares": "share",
    "reposts": "share",
}
PLATFORM_DOMAINS = {
    "weibo": ("weibo.com", "weibo.cn"),
    "bilibili": ("bilibili.com", "b23.tv"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "douyin": ("douyin.com", "iesdouyin.com"),
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="social_activity_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events or [gap_event(collected_at=collected_at, reason="social_activity_records_empty")]


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
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path)
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
    context = {
        str(key): value
        for key, value in loaded.items()
        if not isinstance(value, (list, dict)) and value not in (None, "")
    }
    collected: List[Any] = []
    for key in (
        "activities",
        "history",
        "watch_history",
        "favorites",
        "collections",
        "likes",
        "follows",
        "following",
        "comments",
        "shares",
        "reposts",
        "items",
        "records",
        "data",
        "list",
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
    action_type = SECTION_ACTION_TYPES.get(section)
    if not isinstance(item, dict):
        return {"value": item, "source_section": section, "action_type": action_type}
    record = {**context, **item}
    record.setdefault("source_section", section)
    if action_type:
        record.setdefault("action_type", action_type)
    return record


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
                    record.setdefault("source_section", sheet.title)
                    records.append(record)
    finally:
        workbook.close()
    return records


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "action_type": "saved_page",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(path, text),
        "creator": meta_content(html, "author") or meta_content(html, "og:site_name"),
        "url": canonical_url(html) or first_url(html),
        "content": text,
        "path": str(path),
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "action_type": infer_action_type({"content": text}, path),
        "title": infer_title(path, text),
        "url": first_url(text),
        "content": text,
        "path": str(path),
    }


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    action_type = infer_action_type(record, path)
    platform = infer_platform(record, path)
    title = first(record, ["title", "name", "subject", "视频标题", "笔记标题", "微博正文", "标题", "名称"]) or path.stem
    text = first(record, ["text", "content", "body", "summary", "description", "comment", "评论", "正文", "内容", "简介", "备注"]) or ""
    creator = first(record, ["creator", "author", "owner", "uploader", "screen_name", "nickname", "up", "博主", "作者", "发布者", "UP主", "账号"])
    url = first(record, ["url", "link", "href", "链接", "地址"])
    event_time = first(record, ["time", "date", "created_at", "updated_at", "watched_at", "liked_at", "favorited_at", "commented_at", "时间", "日期", "观看时间", "收藏时间", "点赞时间", "评论时间"])
    data = {
        "action_type": action_type,
        "platform": platform,
        "source_section": first(record, ["source_section", "sheet"]),
        "title": title,
        "creator": creator,
        "creator_id": first(record, ["creator_id", "author_id", "uid", "user_id", "up_id", "博主ID", "作者ID", "用户ID"]),
        "creator_url": first(record, ["creator_url", "author_url", "主页", "作者主页"]),
        "url": url,
        "domain": host_for(url),
        "item_id": first(record, ["item_id", "post_id", "video_id", "note_id", "微博ID", "视频ID", "笔记ID"]),
        "tags": tags_for(record),
        "topics": list_values(record, ["topics", "topic", "话题"]),
        "symbols": list_values(record, ["symbols", "codes", "tickers", "证券", "股票", "代码"]),
        "duration_seconds": number(first(record, ["duration_seconds", "duration", "时长"])),
        "progress": first(record, ["progress", "watch_progress", "观看进度"]),
        "like_count": number(first(record, ["like_count", "likes", "点赞数"])),
        "comment_count": number(first(record, ["comment_count", "comments", "评论数"])),
        "share_count": number(first(record, ["share_count", "shares", "分享数", "转发数"])),
        "favorite_count": number(first(record, ["favorite_count", "favorites", "收藏数"])),
        "view_count": number(first(record, ["view_count", "views", "play_count", "播放量", "浏览量"])),
        "follower_count": number(first(record, ["follower_count", "followers", "粉丝数"])),
        "evidence_role": "weak_influence_signal",
        "investment_claim_allowed": False,
        "requires_corroboration": True,
        "comment_preview": text[:800] if action_type == "comment" else None,
        "content_preview": text[:1200],
        "has_content": bool(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, platform, action_type, title, creator, event_time),
        "collector": COLLECTOR,
        "source": "社交平台用户授权活动",
        "owner_scope": "personal",
        "kind": kind_for_action(action_type),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "row": row,
            "platform": platform,
            "action_type": action_type,
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message", "contact"],
        },
        "wiki_targets": ["internal.social.activity"],
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "社交平台用户活动授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "action_type": "collector_gap",
            "gap": reason,
            "message": "No user-authorized Weibo/Bilibili/Xiaohongshu activity export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["personal_message"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def infer_action_type(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["action_type", "activity_type", "action", "event", "type", "动作", "行为", "类型"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path).lower()
    probe = (explicit or text).lower()
    if any(token in probe for token in ("follow", "关注", "订阅")):
        return "follow"
    if any(token in probe for token in ("like", "liked", "点赞", "赞过")):
        return "like"
    if any(token in probe for token in ("favorite", "fav", "collect", "收藏", "稍后再看")):
        return "favorite"
    if any(token in probe for token in ("watch", "view", "history", "观看", "浏览", "播放", "看过")):
        return "watch"
    if any(token in probe for token in ("comment", "reply", "评论", "回复")):
        return "comment"
    if any(token in probe for token in ("share", "repost", "转发", "分享")):
        return "share"
    if any(token in probe for token in ("saved_page", "保存页面")):
        return "saved_page"
    return "activity"


def infer_platform(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["platform", "app", "source_app", "平台", "应用"])
    url_platform = platform_from_url(first(record, ["url", "link", "href", "链接", "地址"]) or "")
    if url_platform:
        return url_platform
    text = (explicit or "") + " " + json.dumps(record, ensure_ascii=False) + " " + str(path)
    lowered = text.lower()
    if "weibo" in lowered or "微博" in text:
        return "weibo"
    if "bilibili" in lowered or "b站" in lowered or "哔哩" in text:
        return "bilibili"
    if "xiaohongshu" in lowered or "xhs" in lowered or "小红书" in text:
        return "xiaohongshu"
    if "douyin" in lowered or "抖音" in text:
        return "douyin"
    return "unknown"


def platform_from_url(url: str) -> Optional[str]:
    host = host_for(url)
    if not host:
        return None
    for platform, domains in PLATFORM_DOMAINS.items():
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


def kind_for_action(action_type: str) -> str:
    if action_type == "follow":
        return "profile"
    if action_type == "comment":
        return "message"
    if action_type in {"like", "favorite", "watch", "share", "saved_page", "activity"}:
        return "note"
    return "other"


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    action_counts = Counter((event.get("data") or {}).get("action_type", "unknown") for event in events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in events)
    gap_only = bool(events) and set(action_counts) == {"collector_gap"}
    return {
        "schema": "collectorx.social_activity.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "collection_readiness": {
            "status": "needs_social_activity_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_influence": False,
            "evidence_strength": "weak_attention",
            "requires_corroboration": True,
            "collector_claims_investment_conclusion": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized social activity export." if gap_only else "Feed events into social-investment-influence lens.",
        },
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
        "# Social Activity Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Generic social activity events are not written to the investor Wiki directly. Use the social-investment-influence lens.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


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
            return split_terms(value)
        if isinstance(value, list):
            return clean_list_items(value)
    return []


def first_raw(record: Dict[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    normalized_key = normalize_key(key)
    for candidate, value in record.items():
        if normalize_key(candidate) == normalized_key:
            return value
    return None


def split_terms(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,，、;；|\n]+", text) if item.strip()]


def clean_list_items(items: List[Any]) -> List[str]:
    cleaned: List[str] = []
    for item in items:
        if isinstance(item, dict):
            value = first(item, ["name", "title", "code", "symbol", "tag", "topic", "名称", "标题"])
        else:
            value = str(item)
        if value and value != "None":
            cleaned.append(value.strip())
    return cleaned


def tags_for(record: Dict[str, Any]) -> List[str]:
    return list_values(record, ["tags", "tag", "labels", "标签"])


def number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    multiplier = 10000 if text.endswith("万") else 1
    text = text.removesuffix("万").strip()
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def sanitized(value: Any, key_hint: str = "") -> Any:
    lowered_hint = key_hint.lower()
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            clean[str(key)] = sanitized(item, str(key))
        return clean
    if isinstance(value, list):
        return [sanitized(item, key_hint) for item in value[:200]]
    if isinstance(value, str):
        cap = 1200 if any(fragment in lowered_hint for fragment in CONTENT_KEY_FRAGMENTS) else 4000
        return value[:cap]
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


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return path.stem


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
