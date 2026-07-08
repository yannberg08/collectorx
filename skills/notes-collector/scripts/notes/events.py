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
    event_time = normalize_time(first(note, ["updated", "last_edited", "last_edited_time", "mtime", "created", "created_time"]))
    data = {
        "source_app": actual_source_app,
        "title": title,
        "path": path,
        "url": url,
        "content_preview": content[:CONTENT_PREVIEW_MAX_CHARS],
        "has_content": bool(content),
        "content_length": len(content),
        "content_digest": content_digest(content),
        "content_included": include_content,
        "tags": tags_for(note, content),
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
        "collected_at": collected_at or now_iso(),
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
    kind_counts = Counter(event["kind"] for event in events)
    source_app_counts = Counter(source_app_for(event) for event in events)
    observed_platforms = sorted(source for source, count in source_app_counts.items() if count)
    observed_expected = [platform for platform in EXPECTED_P1_NOTE_PLATFORMS if source_app_counts.get(platform)]
    missing_expected = [platform for platform in EXPECTED_P1_NOTE_PLATFORMS if not source_app_counts.get(platform)]
    unknown_event_count = sum(
        count
        for app, count in source_app_counts.items()
        if app not in EXPECTED_P1_NOTE_PLATFORMS and app not in GENERIC_NOTE_SOURCES
    )
    return {
        "schema": "collectorx.notes.manifest.v1",
        "collector": COLLECTOR,
        "source_app": source_app,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
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
        "field_coverage": field_coverage(events),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "content_policy": content_policy(events),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_note_classification_done": False,
            "required_lens": "investment-notes",
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": "events_collected" if events else "no_notes_collected",
            "can_enter_finclaw": bool(events),
            "can_claim_investment_notes": False,
            "platform_coverage_status": platform_coverage_status(events, missing_expected),
            "next_action": "Feed notes events into investment-notes lens for investor-specific routing." if events else "Provide an authorized notes vault/export.",
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
    write_jsonl(out_dir / "lake" / COLLECTOR / "events.jsonl", events)
    manifest = build_manifest(events, source_app=source_app, collected_at=collected_at, collection_audit=collection_audit)
    write_json(out_dir / "manifest.json", manifest)
    summary = [
        "# Notes Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- source_app: `{source_app}`",
        f"- event_count: {len(events)}",
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


def platform_coverage_status(events: List[Dict[str, Any]], missing_expected: List[str]) -> str:
    if not events:
        return "no_platform_observed"
    if not missing_expected:
        return "all_expected_platforms_observed"
    return "partial_expected_platforms_observed"


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
