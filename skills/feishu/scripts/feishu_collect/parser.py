"""Parse user-authorized Feishu exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlparse


COLLECTOR = "feishu"
CN_TZ = timezone(timedelta(hours=8))
DATA_QUALITY_TARGET = "collectorx.data_quality.collection_gaps"
SUPPORTED_RECORD_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".html", ".htm", ".md", ".markdown", ".txt"}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SECRET_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "cookie",
    "secret",
    "credential",
    "authorization",
    "session",
    "token",
    "tenant_key",
    "app_secret",
    "refresh_token",
    "access_token",
    "user_token",
)
CONTENT_KEY_FRAGMENTS = ("content", "body", "text", "message", "summary", "正文", "内容", "消息", "纪要")
SOURCE_PATH_KEY = "_collectorx_source_path"
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
FEISHU_RECOMMENDED_FIELDS = (
    "platform",
    "record_kind",
    "title",
    "chat",
    "sender",
    "time",
    "content_preview",
    "url",
    "document_ref",
    "file_name",
    "meeting_url",
    "participants",
)
SECTION_KINDS = {
    "messages": "message",
    "message": "message",
    "chats": "chat",
    "chat": "chat",
    "contacts": "contact",
    "members": "contact",
    "files": "file",
    "attachments": "file",
    "folders": "folder",
    "documents": "document",
    "docs": "document",
    "docx": "document",
    "wiki": "document",
    "recordings": "recording",
    "minutes": "meeting",
    "meetings": "meeting",
    "records": None,
    "items": None,
    "data": None,
    "list": None,
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
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    paths = list(iter_paths(input_list))
    audit = new_collection_audit(input_list, paths, limit=limit)
    if not paths:
        events = [
            gap_event(
                collected_at=collected_at,
                reason="feishu_authorized_input_missing",
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
            "emitted_event_count": 0,
            "status": "parsed",
        }
        audit["path_results"].append(path_result)
        increment_counter(audit, "extension_counts", path_result["extension"])
        try:
            records = parse_path(path, audit=audit)
        except Exception as exc:
            records = []
            path_result["status"] = "parse_error"
            path_result["error_type"] = exc.__class__.__name__
            increment_counter(audit, "skipped_reason_counts", "parse_error")
        path_result["parsed_record_count"] = len(records)
        if not records and path_result["status"] == "parsed":
            path_result["status"] = "parsed_empty"
        audit["parsed_record_count"] += len(records)
        for row, record in enumerate(records, start=1):
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            path_result["emitted_event_count"] += 1
            if limit is not None and len(events) >= limit:
                audit["emitted_event_count"] = len(events[:limit])
                finalize_audit(audit)
                return events[:limit], audit

    if not events:
        events = [
            gap_event(
                collected_at=collected_at,
                reason="feishu_records_empty",
                collection_audit=audit,
            )
        ]
    audit["emitted_event_count"] = len(events)
    finalize_audit(audit)
    return events, audit


def new_collection_audit(inputs: List[str], paths: List[Path], *, limit: Optional[int] = None) -> Dict[str, Any]:
    return {
        "source_type": "authorized_local_feishu_export",
        "input_count": len(inputs),
        "resolved_input_file_count": len(paths),
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "skipped_archive_member_reason_counts": {},
        "skipped_reason_counts": {},
        "parsed_record_count": 0,
        "emitted_event_count": 0,
        "limit": limit,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "real_account_adapter_used": False,
        "path_results": [],
    }


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


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    return zip_member_skip_reason(member) != ""


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


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
    for key, kind in SECTION_KINDS.items():
        value = loaded.get(key)
        if isinstance(value, list):
            collected.extend(with_section_context(item, key, kind, context) for item in value)
        elif isinstance(value, dict):
            collected.extend(with_section_context(item, key, kind, context) for item in extract_records(value))
    if collected:
        return collected
    return [loaded]


def with_section_context(item: Any, section: str, kind: Optional[str], context: Dict[str, Any]) -> Dict[str, Any]:
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


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    resolved_collected_at = collected_at or now_iso()
    kind = normalize_kind(first(record, ["record_kind", "kind", "type", "docs_type", "文件类型", "类型", "消息类型"]) or infer_kind_from_record(record, path))
    text = first(record, ["text", "content", "message", "body", "summary", "description", "transcript", "正文", "内容", "消息", "纪要"]) or ""
    title = first(record, ["title", "name", "subject", "chat", "room", "group", "file_name", "filename", "标题", "名称", "会话", "群名", "文件名"]) or path.stem
    url = first(record, ["url", "link", "href", "file_url", "meeting_url", "web_url", "链接", "地址", "会议链接"])
    source_event_time = first(record, ["time", "date", "created_at", "updated_at", "sent_at", "start_time", "modified_time", "时间", "日期", "发送时间", "开始时间"])
    event_time = source_event_time or resolved_collected_at
    path_label = first(record, [SOURCE_PATH_KEY, "path"]) or str(path)
    participants = list_values(record, ["participants", "attendees", "members", "users", "参会人", "成员"])
    data = {
        "platform": "feishu",
        "source_section": first(record, ["source_section", "sheet"]),
        "record_kind": kind,
        "title": title,
        "chat": first(record, ["chat", "chat_name", "room", "group", "conversation", "会话", "群名", "群聊"]),
        "chat_id": first(record, ["chat_id", "conversation_id", "group_id", "open_chat_id", "群ID", "会话ID"]),
        "sender": first(record, ["sender", "from", "from_name", "user", "sender_name", "发送人", "发信人", "姓名"]),
        "sender_id": first(record, ["sender_id", "from_id", "userid", "user_id", "open_id", "发送人ID", "用户ID"]),
        "receiver": first(record, ["receiver", "to", "recipient", "接收人", "收件人"]),
        "url": url,
        "domain": host_for(url),
        "document_ref": first(record, ["document_id", "doc_id", "docs_token", "doc_token", "obj_token", "wiki_token", "文档ID"]),
        "file_name": first(record, ["file_name", "filename", "attachment", "name", "文件名", "附件"]),
        "file_type": first(record, ["file_type", "mime_type", "docs_type", "type", "文件类型"]),
        "meeting_url": first(record, ["meeting_url", "会议链接"]),
        "participants": participants,
        "tags": list_values(record, ["tags", "labels", "标签"]),
        "content_preview": text[:1500],
        "has_content": bool(text),
        "content_length": len(text),
        "participant_count": len(participants),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "path": path_label,
        "row": row,
        "platform": "feishu",
        "record_kind": kind,
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
        "source_id": first(record, ["id", "message_id", "file_key", "document_id", "doc_id", "docs_token", "doc_token"]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, path_label, row, kind, title, event_time, text[:160]),
        "collector": COLLECTOR,
        "source": "用户授权飞书导出",
        "owner_scope": "personal",
        "kind": event_kind_for_record(kind),
        "time": event_time,
        "collected_at": resolved_collected_at,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message", "contact", "work_confidential", "document"],
        },
        "wiki_targets": wiki_targets_for_record(kind),
    }


def gap_event(
    *,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_time = collected_at or now_iso()
    audit = collection_audit or {}
    status_by_reason = {
        "feishu_authorized_input_missing": "needs_feishu_authorized_input",
        "feishu_records_empty": "records_empty",
    }
    messages = {
        "feishu_authorized_input_missing": "No user-authorized Feishu export was provided.",
        "feishu_records_empty": "The authorized Feishu input did not contain readable records.",
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, "gap", reason, event_time),
        "collector": COLLECTOR,
        "source": "飞书授权状态",
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
            "profile_type": "feishu_collection_gap",
            "message": messages.get(reason, "Feishu collection produced a traceable gap."),
            "candidate_record_count": int(audit.get("parsed_record_count") or 0),
            "parsed_record_count": int(audit.get("parsed_record_count") or 0),
            "feishu_event_count": 0,
            "retained_record_count": 0,
            "business_records_written": False,
            "read_only": True,
            "policy_does_not_assert_investment_relevance": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_feishu_fact_claimed": False,
            "investment_conclusion_claimed": False,
            "complete_feishu_archive_claimed": False,
            "feishu_service_token_collected": False,
        },
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "scope_policy_enabled": False,
        },
        "privacy": {"sensitive": True, "local_only": True, "contains": ["work_confidential", "collection_gap"]},
        "wiki_targets": [DATA_QUALITY_TARGET],
    }


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    gap_event_count = len(events) - len(usable_events)
    kind_counts = Counter(event["kind"] for event in events)
    record_counts = Counter((event.get("data") or {}).get("record_kind", "unknown") for event in events)
    gap_only = bool(events) and all(is_gap_event(event) for event in events)
    surface_summary = feishu_surface_summary(usable_events)
    feishu_event_count = len(usable_events)
    return {
        "schema": "collectorx.feishu.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "usable_event_count": feishu_event_count,
        "feishu_event_count": feishu_event_count,
        "gap_event_count": gap_event_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "record_kind_counts": dict(sorted(record_counts.items())),
        "field_coverage": field_coverage(usable_events),
        "feishu_surface_summary": surface_summary,
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_classification_done": False,
            "required_lenses": ["meeting-minutes", "research-documents", "future-collaboration-dialogue"],
            "real_account_validation": False,
            "read_only_collection": True,
        },
        "collection_readiness": {
            "status": feishu_readiness_status(events, gap_only=gap_only),
            "can_enter_finclaw": feishu_event_count > 0,
            "can_enter_feishu_lake": feishu_event_count > 0,
            "can_enter_data_quality_lake": gap_event_count > 0,
            "can_feed_meeting_minutes_lens": surface_summary["meeting_event_count"] > 0,
            "can_feed_research_documents_lens": surface_summary["document_event_count"] > 0,
            "can_feed_collaboration_dialogue_lens": (
                surface_summary["message_event_count"] + surface_summary["chat_event_count"]
            ) > 0,
            "can_feed_investor_wiki_directly": False,
            "can_claim_investment_evidence": False,
            "usable_event_count": feishu_event_count,
            "feishu_event_count": feishu_event_count,
            "gap_event_count": gap_event_count,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": feishu_next_action(events, gap_only=gap_only),
        },
    }


def is_gap_event(event: Dict[str, Any]) -> bool:
    data = event.get("data") or {}
    return (
        data.get("record_kind") == "collector_gap"
        or data.get("action_type") == "collector_gap"
        or bool(data.get("gap"))
    )


def feishu_readiness_status(events: List[Dict[str, Any]], *, gap_only: bool) -> str:
    if gap_only:
        reason = (events[0].get("data") or {}).get("gap") if events else ""
        if reason == "feishu_records_empty":
            return "records_empty"
        return "needs_feishu_authorized_input"
    if not events:
        return "records_empty"
    return "events_collected"


def feishu_next_action(events: List[Dict[str, Any]], *, gap_only: bool) -> str:
    if gap_only:
        reason = (events[0].get("data") or {}).get("gap") if events else ""
        if reason == "feishu_records_empty":
            return "Provide a Feishu export containing readable records."
        return "Provide authorized Feishu export."
    return "Feed events into relevant investor lenses."


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
        "# Feishu Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- feishu_event_count: {manifest.get('feishu_event_count', 0)}",
        f"- gap_event_count: {manifest.get('gap_event_count', 0)}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- feishu_lake_ready: `{manifest['collection_readiness']['can_enter_feishu_lake']}`",
        f"- data_quality_lake_ready: `{manifest['collection_readiness']['can_enter_data_quality_lake']}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- message_events: {manifest['feishu_surface_summary']['message_event_count']}",
        f"- document_events: {manifest['feishu_surface_summary']['document_event_count']}",
        f"- meeting_events: {manifest['feishu_surface_summary']['meeting_event_count']}",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
        "",
        "Generic Feishu events are not written to the investor Wiki directly. Use investor lenses for investment filtering.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if (event.get("data") or {}).get("record_kind") != "collector_gap"]
    field_counts = {
        field: sum(1 for event in usable_events if field_present(event, field))
        for field in FEISHU_RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(FEISHU_RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_content": sum(1 for event in usable_events if (event.get("data") or {}).get("has_content")),
    }


def field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    value = (event.get("data") or {}).get(field)
    return value not in (None, "", [], {})


def feishu_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, int]:
    usable_events = [event for event in events if (event.get("data") or {}).get("record_kind") != "collector_gap"]
    return {
        "message_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") == "message"),
        "chat_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") == "chat"),
        "document_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") == "document"),
        "file_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") in {"file", "folder"}),
        "meeting_event_count": sum(1 for event in usable_events if (event.get("data") or {}).get("record_kind") in {"meeting", "recording"}),
        "events_with_content": sum(1 for event in usable_events if (event.get("data") or {}).get("has_content")),
        "events_with_url": sum(1 for event in usable_events if (event.get("data") or {}).get("url")),
        "events_with_document_ref": sum(1 for event in usable_events if (event.get("data") or {}).get("document_ref")),
        "events_with_participants": sum(1 for event in usable_events if (event.get("data") or {}).get("participants")),
    }


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    gap_event_count = len(events) - len(usable_events)
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in usable_events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    audit = {
        "source_ref_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("path")),
        "archive_member_event_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "archive_path_traversal_members_collected": False,
        "usable_event_count": len(usable_events),
        "feishu_event_count": len(usable_events),
        "gap_event_count": gap_event_count,
        "business_records_written": bool(usable_events),
        "read_only": True,
    }
    if collection_audit:
        audit.update(collection_audit)
    return audit


def increment_counter(audit: Dict[str, Any], key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_audit(audit: Dict[str, Any]) -> Dict[str, Any]:
    for key in (
        "extension_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "skipped_archive_member_reason_counts",
        "skipped_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))
    return audit


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


def first_raw(record: Dict[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    normalized_key = normalize_key(key)
    for candidate, value in record.items():
        if normalize_key(candidate) == normalized_key:
            return value
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
    if any(token in lowered for token in ("recording", "minutes", "meeting", "录音", "妙记", "会议", "纪要", "参会")):
        return "meeting"
    if any(token in lowered for token in ("docx", "docs", "document", "wiki", "文档", "知识库")):
        return "document"
    if any(token in lowered for token in ("file", "attachment", "folder", "文件", "附件", "文件夹")):
        return "file"
    if any(token in lowered for token in ("chat", "conversation", "group", "会话", "群")):
        return "chat"
    return "message"


def normalize_kind(value: str) -> str:
    lowered = value.lower()
    if any(token in lowered for token in ("message", "msg", "消息")):
        return "message"
    if any(token in lowered for token in ("chat", "conversation", "group", "会话", "群")):
        return "chat"
    if any(token in lowered for token in ("contact", "member", "通讯录", "联系人", "成员")):
        return "contact"
    if any(token in lowered for token in ("folder", "文件夹")):
        return "folder"
    if any(token in lowered for token in ("file", "attachment", "附件", "文件")):
        return "file"
    if any(token in lowered for token in ("recording", "妙记", "录音")):
        return "recording"
    if any(token in lowered for token in ("meeting", "minutes", "会议", "纪要")):
        return "meeting"
    if any(token in lowered for token in ("doc", "wiki", "document", "文档", "知识库")):
        return "document"
    return value


def event_kind_for_record(record_kind: str) -> str:
    if record_kind == "message":
        return "message"
    if record_kind in {"file", "folder"}:
        return "file"
    if record_kind in {"meeting", "recording", "document"}:
        return "note"
    if record_kind in {"chat", "contact"}:
        return "profile"
    return "note"


def wiki_targets_for_record(record_kind: str) -> List[str]:
    targets = {
        "message": ["internal.collaboration.messages"],
        "chat": ["internal.collaboration.chats"],
        "contact": ["internal.collaboration.contacts"],
        "file": ["internal.collaboration.files"],
        "folder": ["internal.collaboration.files"],
        "document": ["internal.documents"],
        "meeting": ["internal.collaboration.meetings"],
        "recording": ["internal.collaboration.meetings"],
    }
    return targets.get(record_kind, ["internal.feishu.records"])


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
