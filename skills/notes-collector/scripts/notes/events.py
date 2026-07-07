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
    data = {
        "source_app": actual_source_app,
        "title": title,
        "path": path,
        "content_preview": content[:1200],
        "has_content": bool(content),
        "tags": tags_for(note, content),
    }
    if include_content:
        data["content"] = content
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    event_time = first(note, ["updated", "last_edited", "last_edited_time", "mtime", "created", "created_time"])
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(actual_source_app, path, title, event_time, content[:120]),
        "collector": COLLECTOR,
        "source": source_label,
        "owner_scope": "personal",
        "kind": "note",
        "time": normalize_time(event_time),
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "source_app": actual_source_app,
            "path": path,
            "id": first(note, ["id"]),
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["work_confidential", "personal_note"],
        },
        "wiki_targets": ["internal.knowledge.notes"],
    }


def build_manifest(events: List[Dict[str, Any]], *, source_app: str, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    return {
        "schema": "collectorx.notes.manifest.v1",
        "collector": COLLECTOR,
        "source_app": source_app,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "collection_readiness": {
            "status": "events_collected" if events else "no_notes_collected",
            "can_enter_finclaw": bool(events),
            "can_claim_investment_notes": False,
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


def write_package(out_dir: Path, events: List[Dict[str, Any]], *, source_app: str, collected_at: Optional[str] = None) -> None:
    write_jsonl(out_dir / "lake" / COLLECTOR / "events.jsonl", events)
    manifest = build_manifest(events, source_app=source_app, collected_at=collected_at)
    write_json(out_dir / "manifest.json", manifest)
    summary = [
        "# Notes Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- source_app: `{source_app}`",
        f"- event_count: {len(events)}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Generic notes are not written to the investor Wiki directly. Use the investment-notes lens.",
    ]
    (out_dir / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")


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


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
