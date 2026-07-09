"""Parse user-authorized DingTalk/WeCom collaboration exports."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence
from urllib.parse import urlparse


CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_RECORD_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".html", ".htm", ".md", ".markdown", ".txt"}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session", "ticket")
CONTENT_KEY_FRAGMENTS = ("content", "body", "text", "message", "正文", "内容", "消息")
PLATFORMS = {"dingtalk", "wecom"}
SOURCE_PATH_KEY = "_collectorx_source_path"
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
COLLAB_RECOMMENDED_FIELDS = (
    "platform",
    "record_kind",
    "title",
    "chat",
    "sender",
    "time",
    "content_preview",
    "url",
    "file_name",
    "meeting_url",
    "participants",
)
PLATFORM_ALIASES = {
    "dingtalk": ("dingtalk", "dingding", "钉钉"),
    "wecom": ("wecom", "work.weixin", "企业微信", "企微"),
}
SECTION_KINDS = {
    "messages": "message",
    "chats": "chat",
    "contacts": "contact",
    "files": "file",
    "attachments": "file",
    "meetings": "meeting",
    "minutes": "meeting",
    "records": None,
    "items": None,
    "data": None,
    "list": None,
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    platform: str,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_source_platforms: Optional[Iterable[str]] = None,
    deny_source_platforms: Optional[Iterable[str]] = None,
    allow_record_kinds: Optional[Iterable[str]] = None,
    deny_record_kinds: Optional[Iterable[str]] = None,
    allow_chats: Optional[Iterable[str]] = None,
    deny_chats: Optional[Iterable[str]] = None,
    allow_senders: Optional[Iterable[str]] = None,
    deny_senders: Optional[Iterable[str]] = None,
    allow_participants: Optional[Iterable[str]] = None,
    deny_participants: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    platform = normalize_platform(platform)
    events, _audit = collect_from_inputs_with_audit(
        inputs,
        platform=platform,
        collected_at=collected_at,
        limit=limit,
        allow_source_platforms=allow_source_platforms,
        deny_source_platforms=deny_source_platforms,
        allow_record_kinds=allow_record_kinds,
        deny_record_kinds=deny_record_kinds,
        allow_chats=allow_chats,
        deny_chats=deny_chats,
        allow_senders=allow_senders,
        deny_senders=deny_senders,
        allow_participants=allow_participants,
        deny_participants=deny_participants,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    platform: str,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_source_platforms: Optional[Iterable[str]] = None,
    deny_source_platforms: Optional[Iterable[str]] = None,
    allow_record_kinds: Optional[Iterable[str]] = None,
    deny_record_kinds: Optional[Iterable[str]] = None,
    allow_chats: Optional[Iterable[str]] = None,
    deny_chats: Optional[Iterable[str]] = None,
    allow_senders: Optional[Iterable[str]] = None,
    deny_senders: Optional[Iterable[str]] = None,
    allow_participants: Optional[Iterable[str]] = None,
    deny_participants: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    platform = normalize_platform(platform)
    input_list = list(inputs)
    paths = list(iter_paths(input_list))
    collaboration_scope_policy = build_collaboration_scope_policy(
        allow_source_platforms=allow_source_platforms,
        deny_source_platforms=deny_source_platforms,
        allow_record_kinds=allow_record_kinds,
        deny_record_kinds=deny_record_kinds,
        allow_chats=allow_chats,
        deny_chats=deny_chats,
        allow_senders=allow_senders,
        deny_senders=deny_senders,
        allow_participants=allow_participants,
        deny_participants=deny_participants,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    audit = {
        "source_type": f"authorized_local_{platform}_collaboration_export",
        "input_count": len(input_list),
        "resolved_input_file_count": len(paths),
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "skipped_archive_member_reason_counts": {},
        "candidate_record_count": 0,
        "parsed_record_count": 0,
        "emitted_event_count": 0,
        "limit": limit,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "real_account_adapter_used": False,
        "collaboration_scope_policy": collaboration_scope_policy,
        "collaboration_scope_policy_filtered_all": False,
        "path_results": [],
    }
    if not paths:
        finalize_audit(audit)
        events = [gap_event(platform=platform, collected_at=collected_at, reason=f"{platform}_authorized_input_missing", collection_audit=audit)]
        audit["emitted_event_count"] = len(events)
        return events, audit
    events: List[Dict[str, Any]] = []
    for path in paths:
        path_result = {
            "path": str(path),
            "extension": path.suffix.lower() or "<none>",
            "candidate_record_count": 0,
            "parsed_record_count": 0,
            "emitted_event_count": 0,
            "scope_policy_filtered_record_count": 0,
            "status": "parsed",
        }
        audit["path_results"].append(path_result)
        increment_counter(audit, "extension_counts", path_result["extension"])
        records = parse_path(path, audit=audit)
        path_result["candidate_record_count"] = len(records)
        path_result["parsed_record_count"] = len(records)
        audit["candidate_record_count"] += len(records)
        audit["parsed_record_count"] += len(records)
        for row, record in enumerate(records, start=1):
            event = record_to_event(record, path=path, row=row, platform=platform, collected_at=collected_at)
            filter_reason = collaboration_scope_policy_filter_reason(event, collaboration_scope_policy)
            if filter_reason:
                collaboration_scope_policy["filtered_record_count"] += 1
                reason_counts = collaboration_scope_policy.setdefault("filter_reason_counts", {})
                reason_counts[filter_reason] = int(reason_counts.get(filter_reason, 0)) + 1
                path_result["scope_policy_filtered_record_count"] += 1
                continue
            events.append(event)
            path_result["emitted_event_count"] += 1
            if limit is not None and len(events) >= limit:
                audit["emitted_event_count"] = len(events[:limit])
                finalize_audit(audit)
                return events[:limit], audit
        if path_result["candidate_record_count"] and path_result["scope_policy_filtered_record_count"] == path_result["candidate_record_count"]:
            path_result["status"] = "filtered_by_scope_policy"
    if not events and audit["candidate_record_count"] and collaboration_scope_policy.get("enabled"):
        audit["emitted_event_count"] = 0
        finalize_audit(audit)
        events = [gap_event(platform=platform, collected_at=collected_at, reason="collaboration_scope_policy_filtered_all", collection_audit=audit)]
        audit["emitted_event_count"] = len(events)
        return events, audit
    if not events:
        audit["emitted_event_count"] = 0
        finalize_audit(audit)
        events = [gap_event(platform=platform, collected_at=collected_at, reason=f"{platform}_records_empty", collection_audit=audit)]
        audit["emitted_event_count"] = len(events)
        return events, audit
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
    if suffix == ".zip":
        return parse_zip(path, audit=audit)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".html", ".htm"}:
        return [parse_html(path)]
    return [parse_text(path)]


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: normalize_zip_member_name(item.filename)):
            member_name = normalize_zip_member_name(member.filename)
            suffix = Path(member_name).suffix.lower()
            if audit is not None:
                audit["archive_member_count"] += 1
                increment_counter(audit, "archive_member_extension_counts", suffix or "<none>")
            skip_reason = zip_member_skip_reason(member)
            if skip_reason:
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", suffix or "<none>")
                    increment_counter(audit, "skipped_archive_member_reason_counts", skip_reason)
                continue
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            path_label = f"{path}::{member_name}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_text(text, suffix=suffix)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(text, suffix=suffix)
                elif suffix in {".html", ".htm"}:
                    parsed = [parse_html_text(text, path_label=path_label)]
                else:
                    parsed = [parse_text_text(text, path_label=path_label, default_title=Path(member_name).stem)]
            except Exception:
                parsed = []
            for record in parsed:
                if isinstance(record, dict):
                    record[SOURCE_PATH_KEY] = path_label
                    record[SOURCE_ARCHIVE_KEY] = str(path)
                    record[SOURCE_MEMBER_KEY] = member_name
                    records.append(record)
    return records


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    return zip_member_skip_reason(member) != ""


def zip_member_skip_reason(member: zipfile.ZipInfo) -> str:
    member_name = normalize_zip_member_name(member.filename)
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(member.filename)
    if member.is_dir():
        return "directory"
    if member_path.is_absolute() or windows_path.drive or ".." in member_path.parts:
        return "unsafe_path"
    if Path(member_name).suffix.lower() not in SUPPORTED_RECORD_EXTENSIONS:
        return "unsupported_extension"
    return ""


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


def increment_counter(audit: Dict[str, Any], key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_audit(audit: Dict[str, Any]) -> Dict[str, Any]:
    for key in (
        "extension_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "skipped_archive_member_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))
    finalize_collaboration_scope_policy_audit(audit)
    return audit


def split_policy_terms(values: Optional[Iterable[str]]) -> List[str]:
    terms: List[str] = []
    for value in values or []:
        for item in re.split(r"[,，;；|\n]+", str(value)):
            cleaned = item.strip()
            if cleaned:
                terms.append(cleaned)
    return terms


def build_collaboration_scope_policy(
    *,
    allow_source_platforms: Optional[Iterable[str]] = None,
    deny_source_platforms: Optional[Iterable[str]] = None,
    allow_record_kinds: Optional[Iterable[str]] = None,
    deny_record_kinds: Optional[Iterable[str]] = None,
    allow_chats: Optional[Iterable[str]] = None,
    deny_chats: Optional[Iterable[str]] = None,
    allow_senders: Optional[Iterable[str]] = None,
    deny_senders: Optional[Iterable[str]] = None,
    allow_participants: Optional[Iterable[str]] = None,
    deny_participants: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "allow_source_platforms": split_policy_terms(allow_source_platforms),
        "deny_source_platforms": split_policy_terms(deny_source_platforms),
        "allow_record_kinds": split_policy_terms(allow_record_kinds),
        "deny_record_kinds": split_policy_terms(deny_record_kinds),
        "allow_chats": split_policy_terms(allow_chats),
        "deny_chats": split_policy_terms(deny_chats),
        "allow_senders": split_policy_terms(allow_senders),
        "deny_senders": split_policy_terms(deny_senders),
        "allow_participants": split_policy_terms(allow_participants),
        "deny_participants": split_policy_terms(deny_participants),
        "allow_keywords": split_policy_terms(allow_keywords),
        "deny_keywords": split_policy_terms(deny_keywords),
        "filtered_record_count": 0,
        "filter_reason_counts": {},
        "policy_does_not_assert_investment_relevance": True,
    }
    policy["enabled"] = any(
        policy[key]
        for key in (
            "allow_source_platforms",
            "deny_source_platforms",
            "allow_record_kinds",
            "deny_record_kinds",
            "allow_chats",
            "deny_chats",
            "allow_senders",
            "deny_senders",
            "allow_participants",
            "deny_participants",
            "allow_keywords",
            "deny_keywords",
        )
    )
    return policy


def collaboration_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy or not policy.get("enabled"):
        return None
    if policy.get("deny_source_platforms") and policy_hit(policy["deny_source_platforms"], collaboration_platform_surface(event)):
        return "source_platform_denied"
    if policy.get("allow_source_platforms") and not policy_hit(policy["allow_source_platforms"], collaboration_platform_surface(event)):
        return "source_platform_not_allowed"
    if policy.get("deny_record_kinds") and policy_hit(policy["deny_record_kinds"], collaboration_record_kind_surface(event)):
        return "record_kind_denied"
    if policy.get("allow_record_kinds") and not policy_hit(policy["allow_record_kinds"], collaboration_record_kind_surface(event)):
        return "record_kind_not_allowed"
    if policy.get("deny_chats") and policy_hit(policy["deny_chats"], collaboration_chat_surface(event)):
        return "chat_denied"
    if policy.get("allow_chats") and not policy_hit(policy["allow_chats"], collaboration_chat_surface(event)):
        return "chat_not_allowed"
    if policy.get("deny_senders") and policy_hit(policy["deny_senders"], collaboration_sender_surface(event)):
        return "sender_denied"
    if policy.get("allow_senders") and not policy_hit(policy["allow_senders"], collaboration_sender_surface(event)):
        return "sender_not_allowed"
    if policy.get("deny_participants") and policy_hit(policy["deny_participants"], collaboration_participant_surface(event)):
        return "participant_denied"
    if policy.get("allow_participants") and not policy_hit(policy["allow_participants"], collaboration_participant_surface(event)):
        return "participant_not_allowed"
    if policy.get("deny_keywords") and policy_hit(policy["deny_keywords"], collaboration_keyword_surface(event)):
        return "keyword_denied"
    if policy.get("allow_keywords") and not policy_hit(policy["allow_keywords"], collaboration_keyword_surface(event)):
        return "keyword_not_allowed"
    return None


def finalize_collaboration_scope_policy_audit(audit: Dict[str, Any]) -> Dict[str, Any]:
    policy = audit.get("collaboration_scope_policy") or {}
    if policy:
        policy["filter_reason_counts"] = dict(sorted((policy.get("filter_reason_counts") or {}).items()))
    candidate_count = int(audit.get("candidate_record_count") or 0)
    emitted_count = int(audit.get("emitted_event_count") or 0)
    audit["collaboration_scope_policy_filtered_all"] = bool(policy.get("enabled") and candidate_count > 0 and emitted_count == 0)
    return audit


def collaboration_platform_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    return [data.get("platform"), raw_ref.get("platform"), event.get("collector")]


def collaboration_record_kind_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    return [data.get("record_kind"), event.get("kind")]


def collaboration_chat_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    return [data.get("chat"), data.get("chat_id"), data.get("title"), data.get("source_section")]


def collaboration_sender_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    return [data.get("sender"), data.get("sender_id"), data.get("receiver"), data.get("department")]


def collaboration_participant_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    return list(data.get("participants") or [])


def collaboration_keyword_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    surface: List[Any] = [
        data.get("title"),
        data.get("content_preview"),
        data.get("file_name"),
        data.get("file_type"),
        data.get("url"),
        data.get("meeting_url"),
        raw_ref.get("path"),
        raw_ref.get("archive_member"),
    ]
    surface.extend(flatten_policy_surface(data.get("tags")))
    return surface


def flatten_policy_surface(value: Any) -> List[Any]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, dict):
        surface: List[Any] = []
        for item in value.values():
            surface.extend(flatten_policy_surface(item))
        return surface
    if isinstance(value, list):
        surface = []
        for item in value:
            surface.extend(flatten_policy_surface(item))
        return surface
    return [value]


def policy_hit(terms: Sequence[str], surfaces: Iterable[Any]) -> bool:
    haystacks = [str(surface).lower() for surface in surfaces if surface not in (None, "", [], {})]
    for term in terms:
        needle = str(term).lower()
        if needle and any(needle in haystack for haystack in haystacks):
            return True
    return False


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    return parse_json_text(text, suffix=path.suffix.lower())


def parse_json_text(text: str, *, suffix: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
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
    for key in SECTION_KINDS:
        value = loaded.get(key)
        if isinstance(value, list):
            collected.extend(with_section_context(item, key, context) for item in value)
        elif isinstance(value, dict):
            collected.extend(with_section_context(item, key, context) for item in extract_records(value))
    if collected:
        return collected
    return [loaded]


def with_section_context(item: Any, section: str, context: Dict[str, Any]) -> Any:
    kind = SECTION_KINDS.get(section)
    if not isinstance(item, dict):
        return {"value": item, "source_section": section, "record_kind": kind}
    record = {**context, **item}
    record.setdefault("source_section", section)
    if kind:
        record.setdefault("record_kind", kind)
    return record


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_text(text, suffix=path.suffix.lower())


def parse_table_text(text: str, *, suffix: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    return [{str(key): value for key, value in row.items() if key is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_html_text(html, path_label=str(path))


def parse_html_text(html: str, *, path_label: str) -> Dict[str, Any]:
    text = html_to_text(html)
    return {
        "record_kind": infer_kind_from_text(text, Path(path_label)),
        "title": title_tag(html) or infer_title(Path(path_label), text),
        "content": text,
        "url": canonical_url(html) or first_url(html),
        "path": path_label,
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_text_text(text, path_label=str(path), default_title=path.stem)


def parse_text_text(text: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    return {
        "record_kind": infer_kind_from_text(text, Path(path_label)),
        "title": infer_title(Path(default_title), text),
        "content": text,
        "url": first_url(text),
        "path": path_label,
    }


def record_to_event(
    record: Dict[str, Any],
    *,
    path: Path,
    row: int,
    platform: str,
    collected_at: Optional[str],
) -> Dict[str, Any]:
    platform = normalize_platform(first(record, ["platform", "source_app", "app", "平台", "应用"]) or platform)
    kind = normalize_kind(first(record, ["record_kind", "kind", "type", "类型", "消息类型"]) or infer_kind_from_record(record, path))
    text = first(record, ["text", "content", "message", "body", "summary", "正文", "内容", "消息", "备注"]) or ""
    title = first(record, ["title", "name", "subject", "chat", "room", "group", "标题", "名称", "会话", "群名"]) or path.stem
    url = first(record, ["url", "link", "href", "file_url", "meeting_url", "链接", "地址", "会议链接"])
    event_time = first(
        record,
        ["time", "date", "created_at", "updated_at", "sent_at", "start_time", "时间", "日期", "发送时间", "开始时间"],
    )
    path_label = first(record, [SOURCE_PATH_KEY, "path"]) or str(path)
    data = {
        "platform": platform,
        "source_section": first(record, ["source_section", "sheet"]),
        "record_kind": kind,
        "title": title,
        "chat": first(record, ["chat", "chat_name", "room", "group", "conversation", "会话", "群名", "群聊"]),
        "chat_id": first(record, ["chat_id", "conversation_id", "group_id", "群ID", "会话ID"]),
        "sender": first(record, ["sender", "from", "from_name", "user", "sender_name", "发送人", "发信人", "姓名"]),
        "sender_id": first(record, ["sender_id", "from_id", "userid", "user_id", "发送人ID", "用户ID"]),
        "receiver": first(record, ["receiver", "to", "recipient", "接收人", "收件人"]),
        "department": first(record, ["department", "dept", "部门"]),
        "url": url,
        "domain": host_for(url),
        "file_name": first(record, ["file_name", "filename", "attachment", "文件名", "附件"]),
        "file_type": first(record, ["file_type", "mime_type", "文件类型"]),
        "meeting_url": first(record, ["meeting_url", "会议链接"]),
        "participants": list_values(record, ["participants", "attendees", "members", "参会人", "成员"]),
        "tags": list_values(record, ["tags", "labels", "标签"]),
        "content_preview": text[:1500],
        "has_content": bool(text),
        "content_length": len(text),
        "participant_count": len(list_values(record, ["participants", "attendees", "members", "参会人", "成员"])),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "path": path_label,
        "row": row,
        "platform": platform,
        "record_kind": kind,
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
    resolved_collected_at = collected_at or now_iso()
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(platform, path, row, kind, title, event_time, text[:160]),
        "collector": platform,
        "source": f"{display_platform(platform)}用户授权协作导出",
        "owner_scope": "personal",
        "kind": event_kind_for_record(kind),
        "time": event_time or resolved_collected_at,
        "collected_at": resolved_collected_at,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message", "contact", "work_confidential"],
        },
        "wiki_targets": wiki_targets_for_record(kind),
    }


def gap_event(
    *,
    platform: str,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_time = collected_at or now_iso()
    audit = collection_audit or {}
    policy = audit.get("collaboration_scope_policy") if isinstance(audit.get("collaboration_scope_policy"), dict) else {}
    status_by_reason = {
        f"{platform}_authorized_input_missing": f"needs_{platform}_authorized_input",
        f"{platform}_records_empty": "records_empty",
        "collaboration_scope_policy_filtered_all": "scope_policy_filtered_all",
    }
    messages = {
        f"{platform}_authorized_input_missing": f"No user-authorized {platform} collaboration export was provided.",
        f"{platform}_records_empty": f"The authorized {platform} collaboration input did not contain readable records.",
        "collaboration_scope_policy_filtered_all": "All user-authorized collaboration records were excluded by the authorization scope policy.",
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(platform, "gap", reason, event_time),
        "collector": platform,
        "source": f"{display_platform(platform)}授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": event_time,
        "collected_at": event_time,
        "data": {
            "subtype": "collector_gap",
            "action_type": "collector_gap",
            "record_kind": "collector_gap",
            "gap": reason,
            "status": status_by_reason.get(reason, reason),
            "profile_type": "collaboration_collection_gap",
            "message": messages.get(reason, "Collaboration collection produced a traceable gap."),
            "candidate_record_count": int(audit.get("candidate_record_count") or 0),
            "collaboration_event_count": 0,
            "retained_record_count": 0,
            "scope_policy_filtered_record_count": int(policy.get("filtered_record_count") or 0),
            "scope_policy_filter_reason_counts": policy.get("filter_reason_counts") or {},
            "policy_is_user_authorization_scope": bool(policy.get("enabled")),
            "policy_does_not_assert_investment_relevance": True,
            "collaboration_fact_claimed": False,
            "investment_collaboration_fact_claimed": False,
            "investment_conclusion_claimed": False,
            "complete_collaboration_archive_claimed": False,
            "collaboration_service_token_collected": False,
            "collector_writes_investor_wiki_directly": False,
        },
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "scope_policy_enabled": bool(policy.get("enabled")),
        },
        "privacy": {"sensitive": True, "local_only": True, "contains": ["work_confidential", "collection_gap"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    platform: str,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = [
        event for event in events
        if (event.get("data") or {}).get("record_kind") != "collector_gap"
    ]
    gap_event_count = len(events) - len(usable_events)
    kind_counts = Counter(event["kind"] for event in events)
    record_counts = Counter((event.get("data") or {}).get("record_kind", "unknown") for event in events)
    gap_only = bool(events) and set(record_counts) == {"collector_gap"}
    scope_policy_filtered_all = bool((collection_audit or {}).get("collaboration_scope_policy_filtered_all"))
    return {
        "schema": "collectorx.collaboration_exports.manifest.v1",
        "collector": platform,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "collaboration_event_count": len(usable_events),
        "gap_event_count": gap_event_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "record_kind_counts": dict(sorted(record_counts.items())),
        "field_coverage": field_coverage(events),
        "collaboration_surface_summary": collaboration_surface_summary(events),
        "source_audit": source_audit(usable_events, collection_audit=collection_audit),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_collaboration_classification_done": False,
            "required_lenses": ["meeting-minutes", "research-documents"],
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": collaboration_readiness_status(
                events,
                platform=platform,
                gap_only=gap_only,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "can_enter_finclaw": bool(events) and not gap_only and not scope_policy_filtered_all,
            "can_claim_investment_collaboration": False,
            "source_collection_scope": collaboration_source_collection_scope(
                gap_only=gap_only,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "next_action": collaboration_next_action(
                gap_only=gap_only,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
        },
    }


def collaboration_readiness_status(
    events: List[Dict[str, Any]],
    *,
    platform: str,
    gap_only: bool,
    scope_policy_filtered_all: bool,
) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_filtered_all"
    if gap_only:
        return f"needs_{platform}_authorized_input"
    if not events:
        return "records_empty"
    return "events_collected"


def collaboration_source_collection_scope(*, gap_only: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_excluded_all"
    if gap_only:
        return "none"
    return "partial_authorized_input"


def collaboration_next_action(*, gap_only: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "Broaden collaboration scope policy or provide authorized collaboration exports inside the allowed scope."
    if gap_only:
        return "Provide authorized collaboration export."
    return "Feed generic events into relevant investor lenses."


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
        "# Collaboration Export Collector Package",
        "",
        f"- collector: `{manifest['collector']}`",
        f"- event_count: {manifest['event_count']}",
        f"- collaboration_event_count: {manifest.get('collaboration_event_count', 0)}",
        f"- gap_event_count: {manifest.get('gap_event_count', 0)}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
        "",
        "Generic collaboration events are not written to the investor Wiki directly. Use investor lenses for investment filtering.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [
        event for event in events
        if (event.get("data") or {}).get("record_kind") != "collector_gap"
    ]
    field_counts = {
        field: sum(1 for event in usable_events if collaboration_field_present(event, field))
        for field in COLLAB_RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(COLLAB_RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_content": sum(1 for event in usable_events if (event.get("data") or {}).get("has_content")),
    }


def collaboration_field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    data = event.get("data") or {}
    value = data.get(field)
    return value not in (None, "", [], {})


def collaboration_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, int]:
    usable_events = [
        event for event in events
        if (event.get("data") or {}).get("record_kind") != "collector_gap"
    ]
    return {
        "message_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") == "message"),
        "meeting_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") == "meeting"),
        "file_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") == "file"),
        "contact_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") == "contact"),
        "events_with_content": sum(1 for event in usable_events if (event.get("data") or {}).get("has_content")),
        "events_with_meeting_url": sum(1 for event in usable_events if (event.get("data") or {}).get("meeting_url")),
        "events_with_file_name": sum(1 for event in usable_events if (event.get("data") or {}).get("file_name")),
        "events_with_participants": sum(1 for event in usable_events if (event.get("data") or {}).get("participants")),
    }


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    audit = {
        "source_ref_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("path")),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "archive_path_traversal_members_collected": False,
    }
    if collection_audit:
        audit.update(collection_audit)
    return audit


def normalize_platform(value: str) -> str:
    lowered = str(value).lower()
    for platform, aliases in PLATFORM_ALIASES.items():
        if any(alias.lower() in lowered or alias in str(value) for alias in aliases):
            return platform
    if lowered in PLATFORMS:
        return lowered
    raise ValueError(f"Unsupported collaboration platform: {value}")


def display_platform(platform: str) -> str:
    return {"dingtalk": "钉钉", "wecom": "企业微信"}.get(platform, platform)


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
            value = first(item, ["name", "display_name", "username", "user_name", "姓名", "名称"])
        else:
            value = str(item)
        if value and value != "None":
            cleaned.append(value.strip())
    return cleaned


def infer_kind_from_record(record: Dict[str, Any], path: Path) -> str:
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path).lower()
    return infer_kind_from_text(text, path)


def infer_kind_from_text(text: str, path: Path) -> str:
    lowered = (text + " " + str(path)).lower()
    if any(token in lowered for token in ("contact", "member", "通讯录", "联系人", "成员")):
        return "contact"
    if any(token in lowered for token in ("file", "attachment", "文件", "附件")):
        return "file"
    if any(token in lowered for token in ("meeting", "minutes", "会议", "纪要", "参会")):
        return "meeting"
    if any(token in lowered for token in ("chat", "conversation", "group", "会话", "群")):
        return "chat"
    return "message"


def normalize_kind(value: str) -> str:
    lowered = value.lower()
    if lowered == "profile":
        return "contact"
    if lowered == "calendar":
        return "meeting"
    if any(token in lowered for token in ("message", "msg", "消息")):
        return "message"
    if any(token in lowered for token in ("chat", "conversation", "group", "会话", "群")):
        return "chat"
    if any(token in lowered for token in ("contact", "member", "通讯录", "联系人", "成员")):
        return "contact"
    if any(token in lowered for token in ("file", "attachment", "文件", "附件")):
        return "file"
    if any(token in lowered for token in ("meeting", "minutes", "会议", "纪要")):
        return "meeting"
    return value


def event_kind_for_record(record_kind: str) -> str:
    if record_kind == "message":
        return "message"
    if record_kind == "file":
        return "file"
    if record_kind == "meeting":
        return "calendar"
    if record_kind in {"chat", "contact"}:
        return "profile"
    return "note"


def wiki_targets_for_record(record_kind: str) -> List[str]:
    targets = {
        "message": ["internal.collaboration.messages"],
        "chat": ["internal.collaboration.chats"],
        "contact": ["internal.collaboration.contacts"],
        "file": ["internal.collaboration.files"],
        "meeting": ["internal.collaboration.meetings"],
    }
    return targets.get(record_kind, ["internal.collaboration.records"])


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
        cap = 1500 if any(fragment in lowered_hint for fragment in CONTENT_KEY_FRAGMENTS) else 4000
        return value[:cap]
    return value


def host_for(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    return host.split(":", 1)[0] or None


def first_url(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s<>'\")]+", text)
    return match.group(0) if match else None


def canonical_url(html: str) -> Optional[str]:
    match = re.search(r"<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"']([^\"']+)[\"'][^>]*>", html, flags=re.IGNORECASE)
    return unescape(match.group(1)).strip() if match else None


def title_tag(html: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(strip_tags(match.group(1))) if match else None


def html_to_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", html)
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
    return f"{parts[0]}:{digest}"
