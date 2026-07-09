"""Convert collected notes into CollectorX events."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COLLECTOR = "notes"
CN_TZ = timezone(timedelta(hours=8))
EXPECTED_P1_NOTE_PLATFORMS = ("obsidian", "notion", "youdao", "evernote")
GENERIC_NOTE_SOURCES = {"markdown", "notes-export"}
RECOMMENDED_NOTE_FIELDS = (
    "source_app",
    "note_format",
    "title",
    "path",
    "content_preview",
    "has_content",
    "content_length",
    "tags",
    "url",
    "time",
)
CONTENT_PREVIEW_MAX_CHARS = 1200


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def notes_to_events(
    notes: Iterable[Dict[str, Any]],
    *,
    source_app: str,
    source_label: str,
    collected_at: Optional[str] = None,
    include_content: bool = False,
) -> List[Dict[str, Any]]:
    return [
        note_to_event(
            note,
            source_app=source_app,
            source_label=source_label,
            collected_at=collected_at,
            include_content=include_content,
        )
        for note in notes
    ]


def note_to_event(
    note: Dict[str, Any],
    *,
    source_app: str,
    source_label: str,
    collected_at: Optional[str],
    include_content: bool,
) -> Dict[str, Any]:
    actual_source_app = first(note, ["source_app", "source"]) or source_app
    title = first(note, ["title", "name", "标题"]) or "Untitled"
    content = first(note, ["content", "text", "body", "正文", "内容"]) or ""
    path = first(note, ["path", "file", "url", "id"])
    url = first(note, ["url", "link", "链接"])
    resolved_collected_at = collected_at or now_iso()
    event_time = normalize_time(first(note, ["updated", "last_edited", "last_edited_time", "mtime", "created", "created_time"])) or resolved_collected_at
    data = {
        "source_app": actual_source_app,
        "note_format": first(note, ["note_format", "format"]),
        "title": title,
        "path": path,
        "url": url,
        "content_preview": content[:CONTENT_PREVIEW_MAX_CHARS],
        "has_content": bool(content),
        "content_length": len(content),
        "content_digest": content_digest(content),
        "content_included": include_content,
        "tags": tags_for(note, content),
        "canvas_node_count": int_value(first(note, ["canvas_node_count"])),
        "canvas_edge_count": int_value(first(note, ["canvas_edge_count"])),
        "linked_files": list_value(note.get("linked_files")),
    }
    if include_content:
        data["content"] = content
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "source_app": actual_source_app,
        "path": path,
        "id": first(note, ["id"]),
        "url": url,
        "source_archive": first(note, ["source_archive"]),
        "archive_member": first(note, ["archive_member"]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(actual_source_app, path, title, event_time, content[:120]),
        "collector": COLLECTOR,
        "source": source_label,
        "owner_scope": "personal",
        "kind": "note",
        "time": event_time,
        "collected_at": resolved_collected_at,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["work_confidential", "personal_note"],
        },
        "wiki_targets": ["internal.knowledge.notes"],
    }


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    source_app: str,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = usable_note_events(events)
    note_event_count = len(usable_events)
    gap_event_count = len(events) - note_event_count
    kind_counts = Counter(event["kind"] for event in events)
    source_app_counts = Counter(source_app_for(event) for event in usable_events)
    observed_platforms = sorted(source for source, count in source_app_counts.items() if count)
    observed_expected = [platform for platform in EXPECTED_P1_NOTE_PLATFORMS if source_app_counts.get(platform)]
    missing_expected = [platform for platform in EXPECTED_P1_NOTE_PLATFORMS if not source_app_counts.get(platform)]
    unknown_event_count = sum(
        count
        for app, count in source_app_counts.items()
        if app not in EXPECTED_P1_NOTE_PLATFORMS and app not in GENERIC_NOTE_SOURCES
    )
    readiness_status = notes_readiness_status(events, collection_audit)
    return {
        "schema": "collectorx.notes.manifest.v1",
        "collector": COLLECTOR,
        "source_app": source_app,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "note_event_count": note_event_count,
        "gap_event_count": gap_event_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "platform_coverage": {
            "expected_p1_platforms": list(EXPECTED_P1_NOTE_PLATFORMS),
            "observed_platforms": observed_platforms,
            "observed_expected_platforms": observed_expected,
            "missing_expected_platforms": missing_expected,
            "source_app_counts": dict(sorted(source_app_counts.items())),
            "unknown_event_count": unknown_event_count,
            "real_account_validation": False,
        },
        "field_coverage": field_coverage(usable_events),
        "source_audit": source_audit(usable_events, collection_audit=collection_audit),
        "content_policy": content_policy(usable_events),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_note_classification_done": False,
            "required_lens": "investment-notes",
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": readiness_status,
            "can_enter_finclaw": bool(usable_events),
            "can_claim_investment_notes": False,
            "platform_coverage_status": platform_coverage_status(events, missing_expected),
            "next_action": notes_next_action(readiness_status),
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


def write_package(
    out_dir: Path,
    events: List[Dict[str, Any]],
    *,
    source_app: str,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> None:
    if not events:
        reason = notes_gap_reason(collection_audit)
        events = [gap_event(source_app=source_app, collected_at=collected_at, reason=reason, collection_audit=collection_audit)]
        if collection_audit is not None:
            collection_audit["emitted_event_count"] = len(events)
    write_jsonl(out_dir / "lake" / COLLECTOR / "events.jsonl", events)
    manifest = build_manifest(events, source_app=source_app, collected_at=collected_at, collection_audit=collection_audit)
    write_json(out_dir / "manifest.json", manifest)
    summary = [
        "# Notes Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- source_app: `{source_app}`",
        f"- event_count: {len(events)}",
        f"- note_event_count: {manifest.get('note_event_count', 0)}",
        f"- gap_event_count: {manifest.get('gap_event_count', 0)}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- observed_platforms: `{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
        f"- missing_expected_platforms: `{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
        f"- full_content_events: {manifest['content_policy']['full_content_event_count']}",
        "",
        "Generic notes are not written to the investor Wiki directly. Use the investment-notes lens.",
    ]
    (out_dir / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")


def source_app_for(event: Dict[str, Any]) -> str:
    value = event.get("data", {}).get("source_app") or event.get("raw_ref", {}).get("source_app") or "unknown"
    return str(value)


def is_gap_event(event: Dict[str, Any]) -> bool:
    data = event.get("data") or {}
    return data.get("subtype") == "collector_gap" or data.get("action_type") == "collector_gap"


def usable_note_events(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [event for event in events if not is_gap_event(event)]


def platform_coverage_status(events: List[Dict[str, Any]], missing_expected: List[str]) -> str:
    if not events:
        return "no_platform_observed"
    if not missing_expected:
        return "all_expected_platforms_observed"
    return "partial_expected_platforms_observed"


def notes_readiness_status(events: List[Dict[str, Any]], collection_audit: Optional[Dict[str, Any]]) -> str:
    if usable_note_events(events):
        return "events_collected"
    if collection_audit and collection_audit.get("note_source_policy_filtered_all"):
        return "source_policy_filtered_all"
    if collection_audit and not collection_audit.get("input_exists", True):
        return "needs_authorized_notes_input"
    return "no_notes_collected"


def notes_next_action(status: str) -> str:
    if status == "events_collected":
        return "Feed notes events into investment-notes lens for investor-specific routing."
    if status == "source_policy_filtered_all":
        return "Check note source-app/path/tag allow and deny filters, or provide a broader authorized notes export."
    if status == "needs_authorized_notes_input":
        return "Provide a readable user-authorized notes vault or export path."
    return "Provide an authorized notes vault/export."


def notes_gap_reason(collection_audit: Optional[Dict[str, Any]]) -> str:
    audit = collection_audit or {}
    if audit.get("note_source_policy_filtered_all"):
        return "notes_source_policy_filtered_all"
    if not audit.get("input_exists", True):
        return "notes_authorized_input_missing"
    if int(audit.get("candidate_note_count") or 0) == 0:
        return "notes_no_readable_records"
    return "notes_no_retained_records"


def gap_event(
    *,
    source_app: str,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    event_time = collected_at or now_iso()
    audit = collection_audit or {}
    status_by_reason = {
        "notes_source_policy_filtered_all": "source_policy_filtered_all",
        "notes_authorized_input_missing": "needs_authorized_notes_input",
        "notes_no_readable_records": "no_notes_collected",
        "notes_no_retained_records": "no_notes_collected",
    }
    policy = audit.get("note_source_policy") if isinstance(audit.get("note_source_policy"), dict) else {}
    data = {
        "subtype": "collector_gap",
        "action_type": "collector_gap",
        "gap": reason,
        "status": status_by_reason.get(reason, reason),
        "profile_type": "notes_collection_gap",
        "message": notes_gap_message(reason),
        "source_app": source_app,
        "candidate_note_count": int(audit.get("candidate_note_count") or 0),
        "note_event_count": 0,
        "retained_note_count": 0,
        "source_policy_filtered_note_count": int(policy.get("filtered_note_count") or 0),
        "source_policy_filter_reason_counts": policy.get("filter_reason_counts") or {},
        "policy_is_user_authorization_scope": bool(policy.get("enabled")),
        "policy_does_not_assert_investment_relevance": True,
        "note_fact_claimed": False,
        "investment_note_fact_claimed": False,
        "investment_conclusion_claimed": False,
        "complete_notes_vault_claimed": False,
        "full_content_collected": False,
        "note_service_token_collected": False,
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
        "collector_writes_investor_wiki_directly": False,
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, "gap", reason, event_time),
        "collector": COLLECTOR,
        "source": "Notes collector authorization status",
        "owner_scope": "personal",
        "kind": "profile",
        "time": event_time,
        "collected_at": event_time,
        "data": data,
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "source_policy_enabled": bool(policy.get("enabled")),
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_note", "collection_gap"],
        },
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def notes_gap_message(reason: str) -> str:
    messages = {
        "notes_source_policy_filtered_all": "All user-authorized note records were excluded by the note source authorization policy.",
        "notes_authorized_input_missing": "No readable user-authorized notes vault or export was provided.",
        "notes_no_readable_records": "The authorized notes input did not contain readable note records.",
        "notes_no_retained_records": "The authorized notes input produced no retained note events.",
    }
    return messages.get(reason, "Notes collection produced a traceable gap.")


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    field_counts = {
        field: sum(1 for event in events if note_field_present(event, field))
        for field in RECOMMENDED_NOTE_FIELDS
    }
    return {
        "recommended_fields": list(RECOMMENDED_NOTE_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_content": sum(1 for event in events if event.get("data", {}).get("has_content")),
        "events_with_tags": sum(1 for event in events if event.get("data", {}).get("tags")),
    }


def note_field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    data = event.get("data", {})
    value = data.get(field)
    if field == "content_length":
        return isinstance(value, int) and value > 0
    if field == "has_content":
        return value is True
    return value not in (None, "", [], {})


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    archive_members = [
        event.get("raw_ref", {}).get("archive_member")
        for event in events
        if event.get("raw_ref", {}).get("archive_member")
    ]
    archives = [
        event.get("raw_ref", {}).get("source_archive")
        for event in events
        if event.get("raw_ref", {}).get("source_archive")
    ]
    audit = {
        "source_ref_count": sum(1 for event in events if event.get("raw_ref", {}).get("path") or event.get("raw_ref", {}).get("url")),
        "archive_member_event_count": len(archive_members),
        "archive_count": len(set(archives)),
        "events_with_url": sum(1 for event in events if event.get("data", {}).get("url") or event.get("raw_ref", {}).get("url")),
        "events_with_path": sum(1 for event in events if event.get("data", {}).get("path") or event.get("raw_ref", {}).get("path")),
        "archive_path_traversal_members_collected": False,
    }
    if collection_audit:
        audit.update(collection_audit)
        audit["source_ref_count"] = max(
            int(audit.get("source_ref_count") or 0),
            sum(1 for event in events if event.get("raw_ref", {}).get("path") or event.get("raw_ref", {}).get("url")),
        )
        audit["archive_member_event_count"] = max(
            int(audit.get("archive_member_event_count") or 0),
            len(archive_members),
        )
        audit["archive_path_traversal_members_collected"] = False
        audit["windows_drive_archive_members_collected"] = False
    return audit


def content_policy(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    full_content_event_count = sum(1 for event in events if "content" in event.get("data", {}))
    return {
        "default_full_content_included": False,
        "full_content_event_count": full_content_event_count,
        "preview_only_event_count": max(len(events) - full_content_event_count, 0),
        "content_preview_max_chars": CONTENT_PREVIEW_MAX_CHARS,
        "content_digest_algorithm": "sha256",
        "investment_classification_done": False,
    }


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def tags_for(note: Dict[str, Any], content: str) -> List[str]:
    raw = note.get("tags") or note.get("标签") or []
    tags: List[str]
    if isinstance(raw, str):
        tags = [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
    elif isinstance(raw, list):
        tags = [str(item) for item in raw if str(item)]
    else:
        tags = []
    for token in content.split():
        if token.startswith("#") and len(token) > 1:
            tags.append(token.strip("#,，.;；:："))
    return sorted(set(tags))


def int_value(value: Optional[str]) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def list_value(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value in (None, ""):
        return []
    return [str(value)]


def normalize_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        numeric = float(value)
    except ValueError:
        return value
    if numeric > 10_000_000_000:
        numeric = numeric / 1000
    return datetime.fromtimestamp(numeric, CN_TZ).isoformat(timespec="seconds")


def content_digest(content: str) -> Optional[str]:
    if not content:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
