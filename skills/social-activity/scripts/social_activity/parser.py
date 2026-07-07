"""Parse user-authorized social activity exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
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
SUPPORTED_RECORD_EXTENSIONS = {
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
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SUPPORTED_ZIP_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
CONTENT_KEY_FRAGMENTS = ("content", "body", "正文", "全文", "评论", "comment")
EXPECTED_SOCIAL_PLATFORMS = ("weibo", "bilibili", "xiaohongshu")
EXPECTED_SOCIAL_ACTIONS = ("follow", "like", "favorite", "watch", "comment", "share")
RECOMMENDED_WEAK_SIGNAL_FIELDS = (
    "creator",
    "creator_id",
    "creator_url",
    "title",
    "url",
    "domain",
    "item_id",
    "tags",
    "topics",
    "symbols",
    "duration_seconds",
    "progress",
    "like_count",
    "comment_count",
    "share_count",
    "favorite_count",
    "view_count",
    "follower_count",
    "comment_preview",
    "content_preview",
)
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
                if child.is_file() and is_supported_path(child):
                    yield child
        elif path.is_file() and is_supported_path(path):
            yield path


def is_supported_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return parse_zip(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path, path_label=str(path))
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
        record.setdefault("_source_path", path_label)
    return records


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
    return parse_table_text(text, suffix=path.suffix.lower(), path_label=str(path))


def parse_table_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    records = [dict(row) for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    for record in records:
        record.setdefault("_source_path", path_label)
    return records


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_workbook(path_or_stream: Any, *, path_label: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    if path_label:
                        record.setdefault("_source_path", path_label)
                    record.setdefault("source_section", sheet.title)
                    records.append(record)
    finally:
        workbook.close()
    return records


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_html_text(html, path_label=str(path), default_title=path.stem)


def parse_html_text(html: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    text = html_to_text(html)
    return {
        "action_type": "saved_page",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(default_title, text),
        "creator": meta_content(html, "author") or meta_content(html, "og:site_name"),
        "url": canonical_url(html) or first_url(html),
        "content": text,
        "_source_path": path_label,
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_text_text(text, path_label=str(path), default_title=path.stem)


def parse_text_text(text: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    return {
        "action_type": infer_action_type({"content": text}, path_label),
        "title": infer_title(default_title, text),
        "url": first_url(text),
        "content": text,
        "_source_path": path_label,
    }


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            if should_skip_zip_member(member):
                continue
            suffix = Path(member.filename).suffix.lower()
            path_label = f"{path.name}::{member.filename}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".xlsx", ".xlsm"}:
                    parsed = parse_workbook(io.BytesIO(archive.read(member)), path_label=path_label)
                elif suffix in {".html", ".htm"}:
                    parsed = [parse_html_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member.filename).stem)]
                else:
                    parsed = [parse_text_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member.filename).stem)]
            except Exception:
                parsed = []
            records.extend(parsed)
    return records


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    member_path = Path(member.filename)
    if member.is_dir():
        return True
    if member_path.is_absolute() or ".." in member_path.parts:
        return True
    return member_path.suffix.lower() not in SUPPORTED_ZIP_EXTENSIONS


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    path_label = str(record.get("_source_path") or first(record, ["source_path", "file"]) or path)
    action_type = infer_action_type(record, path_label)
    platform = infer_platform(record, path_label)
    title = first(record, ["title", "name", "subject", "视频标题", "笔记标题", "微博正文", "标题", "名称"]) or Path(path_label).stem
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
        "id": stable_id(path_label, row, platform, action_type, title, creator, event_time),
        "collector": COLLECTOR,
        "source": "社交平台用户授权活动",
        "owner_scope": "personal",
        "kind": kind_for_action(action_type),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": path_label,
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


def infer_action_type(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["action_type", "activity_type", "action", "event", "type", "动作", "行为", "类型"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path_label).lower()
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


def infer_platform(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["platform", "app", "source_app", "平台", "应用"])
    url_platform = platform_from_url(first(record, ["url", "link", "href", "链接", "地址"]) or "")
    if url_platform:
        return url_platform
    text = (explicit or "") + " " + json.dumps(record, ensure_ascii=False) + " " + str(path_label)
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
    observed_platforms = sorted(platform for platform, count in platform_counts.items() if count and platform != "unknown")
    observed_expected_platforms = [platform for platform in EXPECTED_SOCIAL_PLATFORMS if platform_counts.get(platform)]
    missing_expected_platforms = [platform for platform in EXPECTED_SOCIAL_PLATFORMS if not platform_counts.get(platform)]
    unknown_platform_count = sum(count for platform, count in platform_counts.items() if platform not in EXPECTED_SOCIAL_PLATFORMS)
    observed_actions = sorted(action for action, count in action_counts.items() if count and action not in {"collector_gap", "unknown"})
    observed_expected_actions = [action for action in EXPECTED_SOCIAL_ACTIONS if action_counts.get(action)]
    missing_expected_actions = [action for action in EXPECTED_SOCIAL_ACTIONS if not action_counts.get(action)]
    unknown_action_count = sum(count for action, count in action_counts.items() if action not in EXPECTED_SOCIAL_ACTIONS and action != "collector_gap")
    field_counts = Counter(
        field
        for event in events
        for field in RECOMMENDED_WEAK_SIGNAL_FIELDS
        if (event.get("data") or {}).get(field) not in (None, "", [])
    )
    observed_recommended_fields = [field for field in RECOMMENDED_WEAK_SIGNAL_FIELDS if field_counts.get(field)]
    missing_recommended_fields = [field for field in RECOMMENDED_WEAK_SIGNAL_FIELDS if not field_counts.get(field)]
    return {
        "schema": "collectorx.social_activity.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "platform_coverage": {
            "expected_p2_platforms": list(EXPECTED_SOCIAL_PLATFORMS),
            "observed_platforms": observed_platforms,
            "observed_expected_platforms": observed_expected_platforms,
            "missing_expected_platforms": missing_expected_platforms,
            "platform_counts": dict(sorted(platform_counts.items())),
            "unknown_platform_count": unknown_platform_count,
            "real_account_validation": False,
        },
        "action_coverage": {
            "expected_actions": list(EXPECTED_SOCIAL_ACTIONS),
            "observed_actions": observed_actions,
            "observed_expected_actions": observed_expected_actions,
            "missing_expected_actions": missing_expected_actions,
            "action_counts": dict(sorted(action_counts.items())),
            "unknown_action_count": unknown_action_count,
            "real_account_validation": False,
        },
        "weak_signal_field_coverage": {
            "recommended_weak_signal_fields": list(RECOMMENDED_WEAK_SIGNAL_FIELDS),
            "observed_recommended_fields": observed_recommended_fields,
            "missing_recommended_fields": missing_recommended_fields,
            "field_counts": dict(sorted(field_counts.items())),
            "real_account_validation": False,
        },
        "weak_evidence_policy": {
            "evidence_role": "weak_influence_signal",
            "investment_claim_allowed": False,
            "requires_corroboration": True,
            "collector_writes_investor_wiki_directly": False,
            "lens_required": "social-investment-influence",
            "usable_as_investment_conclusion": False,
        },
        "collection_readiness": {
            "status": "needs_social_activity_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_influence": False,
            "evidence_strength": "weak_attention",
            "requires_corroboration": True,
            "collector_claims_investment_conclusion": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "platform_coverage_status": coverage_status(events, missing_expected_platforms, "platform"),
            "action_coverage_status": coverage_status(events, missing_expected_actions, "action"),
            "weak_signal_field_coverage_status": coverage_status(events, missing_recommended_fields, "weak_signal_field"),
            "next_action": "Provide authorized social activity export." if gap_only else "Feed events into social-investment-influence lens.",
        },
    }


def coverage_status(events: List[Dict[str, Any]], missing_expected: List[str], noun: str) -> str:
    if not events or all((event.get("data") or {}).get("action_type") == "collector_gap" for event in events):
        return f"no_{noun}_observed"
    if not missing_expected:
        return f"all_expected_{noun}s_observed"
    return f"partial_expected_{noun}s_observed"


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
        f"- observed_platforms: `{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
        f"- missing_expected_platforms: `{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
        f"- observed_actions: `{', '.join(manifest['action_coverage']['observed_actions']) or 'none'}`",
        f"- missing_actions: `{', '.join(manifest['action_coverage']['missing_expected_actions']) or 'none'}`",
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


def infer_title(default_title: str, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return default_title


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
