#!/usr/bin/env python3
"""Convert authorized TickTick/Dida task exports into CollectorX events."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "ticktick"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".ndjson"}
EXPECTED_P1_TASK_PLATFORMS = ("ticktick", "dida365")
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
SOURCE_PATH_KEY = "_collectorx_source_path"
SOURCE_APP_KEY = "_collectorx_source_app"
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
TASK_RECOMMENDED_FIELDS = (
    "source_app",
    "title",
    "project_name",
    "task_id",
    "status",
    "priority",
    "start",
    "due",
    "completed_at",
    "is_completed",
    "tags",
    "recurrence",
    "reminders",
    "time",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="ticktick_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for record in parse_path(path):
            events.append(task_to_event(record, path=path, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS | {".zip"}:
                    yield child
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS | {".zip"}:
            yield path


def parse_path(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".zip":
        return parse_zip(path)
    text = path.read_text(encoding="utf-8-sig").strip()
    return parse_json_text(text, suffix=path.suffix.lower())


def parse_json_text(text: str, *, suffix: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        rows = extract_tasks(loaded)
    return [row for row in rows if isinstance(row, dict)]


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: normalize_zip_member_name(item.filename)):
            if should_skip_zip_member(member):
                continue
            member_name = normalize_zip_member_name(member.filename)
            suffix = Path(member_name).suffix.lower()
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            try:
                parsed = parse_json_text(text, suffix=suffix)
            except Exception:
                parsed = []
            path_label = f"{path}::{member_name}"
            for record in parsed:
                record[SOURCE_PATH_KEY] = path_label
                record[SOURCE_APP_KEY] = infer_task_source(record, path_label)
                record[SOURCE_ARCHIVE_KEY] = str(path)
                record[SOURCE_MEMBER_KEY] = member_name
                tasks.append(record)
    return tasks


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    member_name = normalize_zip_member_name(member.filename)
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(member.filename)
    if member.is_dir():
        return True
    if member_path.is_absolute() or windows_path.drive or ".." in member_path.parts:
        return True
    return Path(member_name).suffix.lower() not in SUPPORTED_EXTENSIONS


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


def extract_tasks(loaded: Any) -> List[Dict[str, Any]]:
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    for key in ("tasks", "items", "records", "data"):
        value = loaded.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    tasks = []
    for key in ("syncTaskBean", "project"):
        value = loaded.get(key)
        if isinstance(value, dict):
            nested = value.get("tasks")
            if isinstance(nested, list):
                tasks.extend(item for item in nested if isinstance(item, dict))
    return tasks or [loaded]


def task_to_event(record: Dict[str, Any], *, path: Path, collected_at: Optional[str]) -> Dict[str, Any]:
    title = first(record, ["title", "name", "任务", "标题"]) or "Untitled task"
    content = first(record, ["content", "desc", "description", "备注", "内容"]) or ""
    due = first(record, ["dueDate", "due_date", "due", "截止时间", "日期"])
    start = first(record, ["startDate", "start_date", "start", "开始时间"])
    completed = first(record, ["completedTime", "completed_time", "完成时间"])
    status = first(record, ["status", "状态"])
    path_label = first(record, [SOURCE_PATH_KEY]) or str(path)
    source_app = first(record, [SOURCE_APP_KEY]) or infer_task_source(record, path_label)
    recurrence = first(record, ["recurrence", "repeat", "repeatFlag", "rrule", "重复", "重复规则"])
    reminders = reminders_for(record)
    event_time = normalize_time(due or start or completed)
    data = {
        "source_app": source_app,
        "title": title,
        "content_preview": content[:1000],
        "content_length": len(content),
        "project_id": first(record, ["projectId", "project_id", "清单ID"]),
        "project_name": first(record, ["projectName", "project_name", "清单", "项目"]),
        "task_id": first(record, ["id", "task_id"]),
        "status": status,
        "priority": first(record, ["priority", "优先级"]),
        "start": start,
        "due": due,
        "completed_at": completed,
        "is_completed": is_completed(status, completed),
        "is_overdue": is_overdue(due, completed, collected_at),
        "recurrence": recurrence,
        "reminders": reminders,
        "tags": tags_for(record),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "path": path_label,
        "source_app": source_app,
        "task_id": data.get("task_id"),
        "project_id": data.get("project_id"),
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_label, data.get("task_id"), title, due, completed),
        "collector": COLLECTOR,
        "source": "滴答清单用户授权任务数据",
        "owner_scope": "personal",
        "kind": "task",
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["task", "work_confidential"],
        },
        "wiki_targets": ["internal.productivity.tasks"],
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "滴答清单授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "gap": reason,
            "message": "No user-authorized TickTick task export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["task"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    source_app_counts = Counter(source_app_for(event) for event in events if source_app_for(event) != "unknown")
    observed_apps = sorted(app for app, count in source_app_counts.items() if count)
    observed_expected = [app for app in EXPECTED_P1_TASK_PLATFORMS if source_app_counts.get(app)]
    missing_expected = [app for app in EXPECTED_P1_TASK_PLATFORMS if not source_app_counts.get(app)]
    unknown_event_count = sum(count for app, count in source_app_counts.items() if app not in EXPECTED_P1_TASK_PLATFORMS)
    return {
        "schema": "collectorx.ticktick.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "platform_coverage": {
            "expected_p1_platforms": list(EXPECTED_P1_TASK_PLATFORMS),
            "observed_platforms": observed_apps,
            "observed_expected_platforms": observed_expected,
            "missing_expected_platforms": missing_expected,
            "source_app_counts": dict(sorted(source_app_counts.items())),
            "unknown_event_count": unknown_event_count,
            "real_account_validation": False,
        },
        "field_coverage": field_coverage(events),
        "time_status_summary": time_status_summary(events),
        "source_audit": source_audit(events),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_task_classification_done": False,
            "required_lens": "task-calendar-investor",
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": "needs_ticktick_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_tasks": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "platform_coverage_status": platform_coverage_status(events, missing_expected),
            "next_action": "Provide authorized TickTick export/API output." if gap_only else "Feed task events into task-calendar-investor lens.",
        },
    }


def source_app_for(event: Dict[str, Any]) -> str:
    value = event.get("data", {}).get("source_app") or event.get("raw_ref", {}).get("source_app") or "unknown"
    return str(value)


def platform_coverage_status(events: List[Dict[str, Any]], missing_expected: List[str]) -> str:
    if not events or all((event.get("data") or {}).get("gap") for event in events):
        return "no_platform_observed"
    if not missing_expected:
        return "all_expected_platforms_observed"
    return "partial_expected_platforms_observed"


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
        "# TickTick Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- observed_platforms: `{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
        f"- missing_expected_platforms: `{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- overdue_tasks: {manifest['time_status_summary']['overdue_task_count']}",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        "",
        "Generic task events are not written to the investor Wiki directly. Use the task-calendar-investor lens.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events = collect_from_inputs(args.input or [], collected_at=collected_at, limit=args.limit)
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if out_dir:
        write_jsonl(out_dir / "lake" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at)
        write_json(out_dir / "manifest.json", manifest)
        write_summary(out_dir / "SUMMARY.md", manifest)
    print(json.dumps({"collector": COLLECTOR, "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert authorized TickTick task exports to CollectorX events.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect", help="Parse local TickTick/Dida task JSON or ZIP exports.")
    p_collect.add_argument("--input", action="append", help="Authorized task JSON/JSONL/ZIP file or folder.")
    p_collect.add_argument("--out-dir", help="Output package directory.")
    p_collect.add_argument("--event-export", help="Output CollectorX Event JSONL path.")
    p_collect.add_argument("--limit", type=int, help="Maximum events to write.")
    p_collect.add_argument("--collected-at", help="Override collection timestamp.")
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def tags_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("tags") or record.get("标签") or []
    if isinstance(raw, str):
        return [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def reminders_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("reminders") or record.get("reminder") or record.get("alerts") or record.get("提醒") or []
    if isinstance(raw, str):
        return [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def is_completed(status: Optional[str], completed: Optional[str]) -> bool:
    if completed:
        return True
    if status is None:
        return False
    text = str(status).lower()
    return text in {"2", "done", "completed", "complete", "已完成"}


def normalize_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value


def is_overdue(due: Optional[str], completed: Optional[str], collected_at: Optional[str]) -> bool:
    if not due or completed:
        return False
    due_dt = parse_datetime(due)
    collected_dt = parse_datetime(collected_at) if collected_at else datetime.now(CN_TZ)
    if due_dt is None or collected_dt is None:
        return False
    return due_dt < collected_dt


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1] + "+00:00")
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return datetime.fromisoformat(text + "T23:59:59+08:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=CN_TZ)
        return parsed
    except ValueError:
        return None


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    task_events = [event for event in events if event.get("kind") == "task"]
    field_counts = {
        field: sum(1 for event in task_events if task_field_present(event, field))
        for field in TASK_RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(TASK_RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_content": sum(1 for event in task_events if (event.get("data") or {}).get("content_length")),
    }


def task_field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    data = event.get("data") or {}
    value = data.get(field)
    if field in {"is_completed", "is_overdue"}:
        return isinstance(value, bool)
    return value not in (None, "", [], {})


def time_status_summary(events: List[Dict[str, Any]]) -> Dict[str, int]:
    task_events = [event for event in events if event.get("kind") == "task"]
    return {
        "task_event_count": len(task_events),
        "completed_task_count": sum(1 for event in task_events if (event.get("data") or {}).get("is_completed") is True),
        "pending_task_count": sum(1 for event in task_events if (event.get("data") or {}).get("is_completed") is False),
        "overdue_task_count": sum(1 for event in task_events if (event.get("data") or {}).get("is_overdue") is True),
        "events_with_start": sum(1 for event in task_events if (event.get("data") or {}).get("start")),
        "events_with_due": sum(1 for event in task_events if (event.get("data") or {}).get("due")),
        "events_with_completion_time": sum(1 for event in task_events if (event.get("data") or {}).get("completed_at")),
        "events_with_recurrence": sum(1 for event in task_events if (event.get("data") or {}).get("recurrence")),
        "events_with_reminders": sum(1 for event in task_events if (event.get("data") or {}).get("reminders")),
    }


def source_audit(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    return {
        "source_ref_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("path")),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "archive_path_traversal_members_collected": False,
    }


def infer_task_source(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["source_app", "source", "platform", "app", "来源", "平台"]) or ""
    probe = f"{explicit} {path_label}".lower()
    if "dida" in probe or "滴答" in probe:
        return "dida365"
    return "ticktick"


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).startswith("_collectorx_"):
                continue
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            cleaned[str(key)] = sanitized(item)
        return cleaned
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:2000]
    return value


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"


if __name__ == "__main__":
    raise SystemExit(main())
