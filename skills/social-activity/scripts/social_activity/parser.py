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
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple
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
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
CONTENT_PREVIEW_MAX_CHARS = 1200
COMMENT_PREVIEW_MAX_CHARS = 800
RECOMMENDED_WEAK_SIGNAL_FIELDS = (
    "social_topics",
    "primary_social_topic",
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
SOCIAL_INFLUENCE_TOPIC_ORDER = (
    "macro_policy",
    "market_strategy",
    "industry_theme",
    "company_fundamental",
    "fund_wealth",
    "trading_review",
    "risk_control",
    "portfolio_watch",
    "creator_education",
    "hk_us_market",
    "unclassified_social_topic",
)
SOCIAL_INFLUENCE_TOPIC_TERMS = {
    "macro_policy": {
        "宏观",
        "政策",
        "流动性",
        "利率",
        "汇率",
        "央行",
        "财政",
        "美联储",
    },
    "market_strategy": {
        "策略",
        "主线",
        "配置",
        "仓位",
        "风格",
        "择时",
        "市场观点",
        "市场复盘",
    },
    "industry_theme": {
        "行业",
        "产业链",
        "主题",
        "赛道",
        "半导体",
        "新能源",
        "消费",
        "医药",
        "互联网",
        "AI",
    },
    "company_fundamental": {
        "财报",
        "业绩",
        "基本面",
        "现金流",
        "ROE",
        "利润",
        "毛利率",
        "安全边际",
    },
    "fund_wealth": {
        "基金",
        "定投",
        "ETF",
        "指数基金",
        "理财",
        "固收",
        "债券基金",
    },
    "trading_review": {
        "复盘",
        "实盘",
        "交易",
        "买入",
        "卖出",
        "加仓",
        "减仓",
        "打板",
    },
    "risk_control": {
        "风险",
        "风控",
        "回撤",
        "止损",
        "纪律",
        "风险控制",
        "黑天鹅",
    },
    "portfolio_watch": {
        "自选",
        "组合",
        "持仓",
        "盯盘",
        "观察",
        "跟踪",
        "提醒",
    },
    "creator_education": {
        "财经博主",
        "投教",
        "大V",
        "投研UP主",
        "研究员",
        "基金经理",
    },
    "hk_us_market": {
        "港股",
        "美股",
        "中概股",
        "恒生",
        "纳斯达克",
        "HK",
        "US",
    },
}
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
    audit: Dict[str, Any] = {
        "source_type": "authorized_social_activity_export",
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
            for record in parsed:
                if not isinstance(record, dict):
                    continue
                row += 1
                events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
                if limit is not None and len(events) >= limit:
                    audit["limit_reached"] = True
                    break
        if limit is not None and len(events) >= limit:
            break

    if not events:
        reason = (
            "social_activity_authorized_input_missing"
            if not input_list or (audit["input_missing_count"] and audit["resolved_input_file_count"] == 0)
            else "social_activity_records_empty"
        )
        events = [gap_event(collected_at=collected_at, reason=reason)]
    audit["parsed_record_count"] = len(usable_social_events(events))
    audit["emitted_event_count"] = len(events)
    audit["extension_counts"] = dict(sorted(extension_counts.items()))
    audit["skipped_extension_counts"] = dict(sorted(skipped_extension_counts.items()))
    audit["skipped_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_archive_member_reason_counts.items()))
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
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def extension_label(path: Path) -> str:
    return path.suffix.lower() or "<none>"


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
                elif suffix in {".xlsx", ".xlsm"}:
                    parsed = parse_workbook(io.BytesIO(archive.read(member)), path_label=path_label)
                elif suffix in {".html", ".htm"}:
                    parsed = [parse_html_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member_name).stem)]
                else:
                    parsed = [parse_text_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member_name).stem)]
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
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
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
    if archive_audit.get("limit_reached"):
        audit["limit_reached"] = True
    for reason, count in (archive_audit.get("skipped_archive_member_reason_counts") or {}).items():
        skipped_reason_counts[str(reason)] += int(count)


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    path_label = str(record.get("_source_path") or first(record, ["source_path", "file"]) or path)
    action_type = infer_action_type(record, path_label)
    platform = infer_platform(record, path_label)
    title = first(record, ["title", "name", "subject", "视频标题", "笔记标题", "微博正文", "标题", "名称"]) or Path(path_label).stem
    text = first(record, ["text", "content", "body", "summary", "description", "comment", "评论", "正文", "内容", "简介", "备注"]) or ""
    creator = first(record, ["creator", "author", "owner", "uploader", "screen_name", "nickname", "up", "博主", "作者", "发布者", "UP主", "账号"])
    url = first(record, ["url", "link", "href", "链接", "地址"])
    tags = tags_for(record)
    topics = list_values(record, ["topics", "topic", "话题"])
    symbols = list_values(record, ["symbols", "codes", "tickers", "证券", "股票", "代码"])
    social_topics, social_topic_terms = classify_social_topics(
        record,
        title=title,
        text=text,
        creator=creator,
        tags=tags,
        topics=topics,
        symbols=symbols,
        action_type=action_type,
        platform=platform,
    )
    event_time = first(record, ["time", "date", "created_at", "updated_at", "watched_at", "liked_at", "favorited_at", "commented_at", "时间", "日期", "观看时间", "收藏时间", "点赞时间", "评论时间"])
    data = {
        "action_type": action_type,
        "platform": platform,
        "social_topics": social_topics,
        "primary_social_topic": social_topics[0] if social_topics else "unclassified_social_topic",
        "social_topic_terms": social_topic_terms,
        "source_section": first(record, ["source_section", "sheet"]),
        "title": title,
        "creator": creator,
        "creator_id": first(record, ["creator_id", "author_id", "uid", "user_id", "up_id", "博主ID", "作者ID", "用户ID"]),
        "creator_url": first(record, ["creator_url", "author_url", "主页", "作者主页"]),
        "url": url,
        "domain": host_for(url),
        "item_id": first(record, ["item_id", "post_id", "video_id", "note_id", "微博ID", "视频ID", "笔记ID"]),
        "tags": tags,
        "topics": topics,
        "symbols": symbols,
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
        "comment_preview": text[:COMMENT_PREVIEW_MAX_CHARS] if action_type == "comment" else None,
        "content_preview": text[:CONTENT_PREVIEW_MAX_CHARS],
        "has_content": bool(text),
        "content_length": len(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "path": path_label,
        "row": row,
        "platform": platform,
        "action_type": action_type,
        "source_section": data.get("source_section"),
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
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
        "raw_ref": raw_ref,
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
        "influence_surface_summary": influence_surface_summary(events),
        "social_activity_boundary_proof": social_activity_boundary_proof(events, collection_audit=collection_audit),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "content_policy": {
            "full_platform_scrape": False,
            "full_creator_profile_scrape": False,
            "full_content_included_by_default": False,
            "content_preview_max_chars": CONTENT_PREVIEW_MAX_CHARS,
            "comment_preview_max_chars": COMMENT_PREVIEW_MAX_CHARS,
            "investment_classification_done": False,
        },
        "weak_evidence_policy": {
            "evidence_role": "weak_influence_signal",
            "investment_claim_allowed": False,
            "requires_corroboration": True,
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "lens_required": "social-investment-influence",
            "usable_as_investment_conclusion": False,
            "real_account_validation": False,
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


def usable_social_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [event for event in events if (event.get("data") or {}).get("action_type") != "collector_gap"]


def influence_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_social_events(events)
    social_topic_counts: Counter[str] = Counter()
    primary_topic_counts: Counter[str] = Counter()
    platform_topic_counts: Counter[str] = Counter()
    action_topic_counts: Counter[str] = Counter()
    for event in usable_events:
        data = event.get("data") or {}
        topics = data.get("social_topics") if isinstance(data.get("social_topics"), list) else []
        if not topics:
            topics = ["unclassified_social_topic"]
        for topic in topics:
            topic_value = str(topic)
            social_topic_counts[topic_value] += 1
            platform_topic_counts[f"{data.get('platform', 'unknown')}:{topic_value}"] += 1
            action_topic_counts[f"{data.get('action_type', 'unknown')}:{topic_value}"] += 1
        primary_topic_counts[str(data.get("primary_social_topic") or topics[0])] += 1
    return {
        "weak_signal_event_count": len(usable_events),
        "expected_social_topics": list(SOCIAL_INFLUENCE_TOPIC_ORDER[:-1]),
        "social_topic_counts": ordered_counts(social_topic_counts, SOCIAL_INFLUENCE_TOPIC_ORDER),
        "primary_social_topic_counts": ordered_counts(primary_topic_counts, SOCIAL_INFLUENCE_TOPIC_ORDER),
        "missing_expected_social_topics": [
            topic for topic in SOCIAL_INFLUENCE_TOPIC_ORDER[:-1] if social_topic_counts.get(topic, 0) == 0
        ],
        "platform_topic_counts": dict(sorted(platform_topic_counts.items())),
        "action_topic_counts": dict(sorted(action_topic_counts.items())),
        "events_with_social_topics": sum(1 for event in usable_events if (event.get("data") or {}).get("social_topics")),
        "events_with_creator": sum(1 for event in usable_events if (event.get("data") or {}).get("creator")),
        "events_with_creator_id": sum(1 for event in usable_events if (event.get("data") or {}).get("creator_id")),
        "events_with_creator_url": sum(1 for event in usable_events if (event.get("data") or {}).get("creator_url")),
        "events_with_url": sum(1 for event in usable_events if (event.get("data") or {}).get("url")),
        "events_with_domain": sum(1 for event in usable_events if (event.get("data") or {}).get("domain")),
        "events_with_item_id": sum(1 for event in usable_events if (event.get("data") or {}).get("item_id")),
        "events_with_tags": sum(1 for event in usable_events if (event.get("data") or {}).get("tags")),
        "events_with_topics": sum(1 for event in usable_events if (event.get("data") or {}).get("topics")),
        "events_with_symbols": sum(1 for event in usable_events if (event.get("data") or {}).get("symbols")),
        "events_with_engagement_counts": sum(1 for event in usable_events if has_engagement_count(event)),
        "events_with_comment_preview": sum(1 for event in usable_events if (event.get("data") or {}).get("comment_preview")),
        "events_with_content_preview": sum(1 for event in usable_events if (event.get("data") or {}).get("has_content")),
        "events_with_source_section": sum(1 for event in usable_events if (event.get("data") or {}).get("source_section")),
    }


def social_activity_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = usable_social_events(events)
    action_counts = Counter((event.get("data") or {}).get("action_type", "unknown") for event in usable_events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in usable_events)
    field_counts = Counter(
        field
        for event in usable_events
        for field in RECOMMENDED_WEAK_SIGNAL_FIELDS
        if (event.get("data") or {}).get(field) not in (None, "", [])
    )
    observed_expected_platforms = [platform for platform in EXPECTED_SOCIAL_PLATFORMS if platform_counts.get(platform)]
    missing_expected_platforms = [platform for platform in EXPECTED_SOCIAL_PLATFORMS if not platform_counts.get(platform)]
    observed_expected_actions = [action for action in EXPECTED_SOCIAL_ACTIONS if action_counts.get(action)]
    missing_expected_actions = [action for action in EXPECTED_SOCIAL_ACTIONS if not action_counts.get(action)]
    observed_recommended_fields = [field for field in RECOMMENDED_WEAK_SIGNAL_FIELDS if field_counts.get(field)]
    missing_recommended_fields = [field for field in RECOMMENDED_WEAK_SIGNAL_FIELDS if not field_counts.get(field)]
    surface = influence_surface_summary(events)
    audit = source_audit(events, collection_audit=collection_audit)
    expected_topics = list(SOCIAL_INFLUENCE_TOPIC_ORDER[:-1])
    observed_topics = [topic for topic in expected_topics if surface["social_topic_counts"].get(topic)]
    missing_topics = list(surface["missing_expected_social_topics"])
    all_expected_platforms = bool(observed_expected_platforms) and not missing_expected_platforms
    all_expected_actions = bool(observed_expected_actions) and not missing_expected_actions
    all_recommended_fields = bool(observed_recommended_fields) and not missing_recommended_fields
    all_expected_topics = bool(observed_topics) and not missing_topics
    if not usable_events:
        gap_reason = None
        if events:
            gap_reason = (events[0].get("data") or {}).get("gap")
        proof_level = "no_authorized_social_activity_input" if gap_reason == "social_activity_authorized_input_missing" else "no_usable_social_activity_records"
    elif all_expected_platforms and all_expected_actions and all_recommended_fields and all_expected_topics:
        proof_level = "strong_partial_social_activity_boundary"
    elif len(observed_expected_platforms) >= 2 and len(observed_expected_actions) >= 3 and surface["events_with_social_topics"] > 0:
        proof_level = "medium_partial_social_activity_boundary"
    else:
        proof_level = "weak_partial_social_activity_boundary"
    blockers = []
    if not usable_events:
        blockers.append("authorized_social_activity_export_missing")
    if missing_expected_platforms:
        blockers.append("missing_expected_platforms:" + ",".join(missing_expected_platforms))
    if missing_expected_actions:
        blockers.append("missing_expected_actions:" + ",".join(missing_expected_actions))
    if missing_recommended_fields:
        blockers.append("missing_recommended_weak_signal_fields:" + ",".join(missing_recommended_fields))
    if missing_topics:
        blockers.append("missing_social_topics:" + ",".join(missing_topics))
    if surface["events_with_social_topics"] == 0:
        blockers.append("social_topic_classification_missing")
    if not audit.get("path_results"):
        blockers.append("path_level_source_audit_missing")
    if audit.get("limit_reached"):
        blockers.append("collection_limit_reached")
    blockers.extend(
        [
            "real_weibo_bilibili_xiaohongshu_validation_missing",
            "creator_domain_allowlist_missing",
            "social_topic_false_positive_review_missing",
            "weak_evidence_backtest_missing",
            "strong_source_corroboration_missing",
        ]
    )
    return {
        "proof_level": proof_level,
        "authorized_input_observed": bool(usable_events),
        "generic_social_activity_collector": True,
        "weak_evidence_only": True,
        "requires_social_investment_lens": True,
        "required_lens": "social-investment-influence",
        "can_enter_finclaw_lake": bool(usable_events),
        "can_feed_investor_wiki_directly": False,
        "can_claim_investment_influence": False,
        "observed_event_count": len(usable_events),
        "platform_boundary": {
            "observed_platforms": observed_expected_platforms,
            "missing_expected_platforms": missing_expected_platforms,
            "platform_counts": dict(sorted(platform_counts.items())),
            "real_account_validation": False,
        },
        "action_boundary": {
            "observed_actions": observed_expected_actions,
            "missing_expected_actions": missing_expected_actions,
            "action_counts": dict(sorted(action_counts.items())),
            "complete_activity_history_claimed": False,
        },
        "weak_signal_field_boundary": {
            "observed_recommended_fields": observed_recommended_fields,
            "missing_recommended_fields": missing_recommended_fields,
        },
        "social_topic_boundary": {
            "expected_social_topics": expected_topics,
            "observed_social_topics": observed_topics,
            "missing_expected_social_topics": missing_topics,
            "social_topic_counts": surface["social_topic_counts"],
            "events_with_social_topics": surface["events_with_social_topics"],
            "social_topic_false_positive_reviewed": False,
        },
        "influence_surface_boundary": {
            "events_with_creator": surface["events_with_creator"],
            "events_with_creator_url": surface["events_with_creator_url"],
            "events_with_url": surface["events_with_url"],
            "events_with_domain": surface["events_with_domain"],
            "events_with_item_id": surface["events_with_item_id"],
            "events_with_tags": surface["events_with_tags"],
            "events_with_symbols": surface["events_with_symbols"],
            "events_with_engagement_counts": surface["events_with_engagement_counts"],
            "events_with_comment_preview": surface["events_with_comment_preview"],
            "events_with_content_preview": surface["events_with_content_preview"],
        },
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
        "content_boundary": {
            "full_platform_scrape": False,
            "full_creator_profile_scrape": False,
            "full_content_included_by_default": False,
            "content_preview_max_chars": CONTENT_PREVIEW_MAX_CHARS,
            "comment_preview_max_chars": COMMENT_PREVIEW_MAX_CHARS,
            "credentials_collected": False,
        },
        "wiki_boundary": {
            "event_schema": "collectorx.event.v1",
            "required_flow": [
                "social-activity collector",
                "collectorx.event.v1",
                "social-investment-influence lens",
                "finclaw.investor_wiki_evidence.v1",
                "SoulMirror investor-portrait distill/organize",
            ],
            "collector_writes_wiki_directly": False,
        },
        "false_claims": {
            "investment_conclusion_claimed": False,
            "complete_social_activity_history_claimed": False,
            "real_account_validation_claimed": False,
            "platform_wide_scrape_performed": False,
            "full_creator_profile_scraped": False,
            "full_content_mirrored": False,
            "private_platform_credentials_collected": False,
            "collector_writes_wiki_directly": False,
        },
        "completion_blockers": blockers,
    }


def has_engagement_count(event: Dict[str, Any]) -> bool:
    data = event.get("data") or {}
    return any(
        data.get(field) is not None
        for field in ("like_count", "comment_count", "share_count", "favorite_count", "view_count", "follower_count")
    )


def classify_social_topics(
    record: Dict[str, Any],
    *,
    title: str,
    text: str,
    creator: Optional[str],
    tags: List[str],
    topics: List[str],
    symbols: List[str],
    action_type: str,
    platform: str,
) -> Tuple[List[str], Dict[str, List[str]]]:
    parts: List[str] = [
        title,
        text,
        creator or "",
        action_type,
        platform,
        " ".join(tags),
        " ".join(topics),
        " ".join(symbols),
    ]
    for key in (
        "creator",
        "author",
        "owner",
        "uploader",
        "screen_name",
        "nickname",
        "title",
        "name",
        "subject",
        "summary",
        "description",
        "comment",
        "博主",
        "作者",
        "发布者",
        "UP主",
        "标题",
        "评论",
        "简介",
    ):
        value = first(record, [key])
        if value:
            parts.append(value)
    searchable = "\n".join(parts)
    lowered = searchable.lower()
    matches: Dict[str, List[str]] = {}
    for topic in SOCIAL_INFLUENCE_TOPIC_ORDER[:-1]:
        hits = topic_term_hits(SOCIAL_INFLUENCE_TOPIC_TERMS[topic], searchable, lowered)
        if hits:
            matches[topic] = hits
    if action_type == "follow":
        matches.setdefault("creator_education", []).append("action:follow")
    if any(re.search(r"(\.|\s)(hk|us)\b", symbol.lower()) or " hk " in f" {symbol.lower()} " for symbol in symbols):
        matches.setdefault("hk_us_market", []).append("symbol_market")
    topics_out = [topic for topic in SOCIAL_INFLUENCE_TOPIC_ORDER[:-1] if topic in matches]
    return topics_out, {topic: matches[topic][:8] for topic in topics_out}


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


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    usable_events = usable_social_events(events)
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
        f"- social_activity_boundary_proof: `{manifest['social_activity_boundary_proof']['proof_level']}`",
        f"- investment_claim_allowed: `{manifest['weak_evidence_policy']['investment_claim_allowed']}`",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
        f"- content_policy: `weak-preview-only`",
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
