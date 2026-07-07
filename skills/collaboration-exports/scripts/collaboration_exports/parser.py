"""Parse user-authorized DingTalk/WeCom collaboration exports."""

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


CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".html", ".htm", ".md", ".markdown", ".txt"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session", "ticket")
CONTENT_KEY_FRAGMENTS = ("content", "body", "text", "message", "正文", "内容", "消息")
PLATFORMS = {"dingtalk", "wecom"}
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
) -> List[Dict[str, Any]]:
    platform = normalize_platform(platform)
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(platform=platform, collected_at=collected_at, reason=f"{platform}_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            events.append(record_to_event(record, path=path, row=row, platform=platform, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events or [gap_event(platform=platform, collected_at=collected_at, reason=f"{platform}_records_empty")]


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
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [{str(key): value for key, value in row.items() if key is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "record_kind": infer_kind_from_text(text, path),
        "title": title_tag(html) or infer_title(path, text),
        "content": text,
        "url": canonical_url(html) or first_url(html),
        "path": str(path),
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "record_kind": infer_kind_from_text(text, path),
        "title": infer_title(path, text),
        "content": text,
        "url": first_url(text),
        "path": str(path),
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
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(platform, path, row, kind, title, event_time, text[:160]),
        "collector": platform,
        "source": f"{display_platform(platform)}用户授权协作导出",
        "owner_scope": "personal",
        "kind": event_kind_for_record(kind),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "row": row,
            "platform": platform,
            "record_kind": kind,
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message", "contact", "work_confidential"],
        },
        "wiki_targets": wiki_targets_for_record(kind),
    }


def gap_event(*, platform: str, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(platform, reason),
        "collector": platform,
        "source": f"{display_platform(platform)}授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "record_kind": "collector_gap",
            "gap": reason,
            "message": f"No user-authorized {platform} collaboration export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["work_confidential"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(events: List[Dict[str, Any]], *, platform: str, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    record_counts = Counter((event.get("data") or {}).get("record_kind", "unknown") for event in events)
    gap_only = bool(events) and set(record_counts) == {"collector_gap"}
    return {
        "schema": "collectorx.collaboration_exports.manifest.v1",
        "collector": platform,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "record_kind_counts": dict(sorted(record_counts.items())),
        "collection_readiness": {
            "status": f"needs_{platform}_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_collaboration": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized collaboration export." if gap_only else "Feed generic events into relevant investor lenses.",
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
        "# Collaboration Export Collector Package",
        "",
        f"- collector: `{manifest['collector']}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Generic collaboration events are not written to the investor Wiki directly. Use investor lenses for investment filtering.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


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
