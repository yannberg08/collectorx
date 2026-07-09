#!/usr/bin/env python3
"""Convert authorized TickTick/Dida task exports into offline CollectorX events.

SoulMirror's live collector path is YAML + AgentRunner + collect_for_soulmirror.py.
This helper is only for local export/package tests and must not write the
SoulMirror lake path directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence


COLLECTOR = "ticktick"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_RECORD_EXTENSIONS = {".json", ".jsonl", ".ndjson"}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
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
    "time_zone",
    "is_all_day",
    "is_completed",
    "tags",
    "recurrence",
    "recurrence_frequency",
    "reminders",
    "checklist_total",
    "checklist_completed",
    "checklist_completion_rate",
    "time",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_source_apps: Optional[Sequence[str]] = None,
    deny_source_apps: Optional[Sequence[str]] = None,
    allow_projects: Optional[Sequence[str]] = None,
    deny_projects: Optional[Sequence[str]] = None,
    allow_tags: Optional[Sequence[str]] = None,
    deny_tags: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(
        inputs,
        collected_at=collected_at,
        limit=limit,
        allow_source_apps=allow_source_apps,
        deny_source_apps=deny_source_apps,
        allow_projects=allow_projects,
        deny_projects=deny_projects,
        allow_tags=allow_tags,
        deny_tags=deny_tags,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_source_apps: Optional[Sequence[str]] = None,
    deny_source_apps: Optional[Sequence[str]] = None,
    allow_projects: Optional[Sequence[str]] = None,
    deny_projects: Optional[Sequence[str]] = None,
    allow_tags: Optional[Sequence[str]] = None,
    deny_tags: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    paths = list(iter_paths(input_list))
    scope_policy = build_task_scope_policy(
        allow_source_apps=allow_source_apps,
        deny_source_apps=deny_source_apps,
        allow_projects=allow_projects,
        deny_projects=deny_projects,
        allow_tags=allow_tags,
        deny_tags=deny_tags,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    audit = new_collection_audit(input_list, paths, limit=limit, scope_policy=scope_policy)
    if not paths:
        finalize_audit(audit)
        events = [gap_event(collected_at=collected_at, reason="ticktick_authorized_input_missing", collection_audit=audit)]
        audit["emitted_event_count"] = len(events)
        return events, audit
    events: List[Dict[str, Any]] = []
    for path in paths:
        path_result = {
            "path": str(path),
            "extension": path.suffix.lower() or "<none>",
            "parsed_record_count": 0,
            "candidate_record_count": 0,
            "emitted_event_count": 0,
            "scope_policy_filtered_record_count": 0,
            "status": "parsed",
        }
        audit["path_results"].append(path_result)
        increment_counter(audit, "extension_counts", path_result["extension"])
        records = parse_path(path, audit=audit)
        path_result["parsed_record_count"] = len(records)
        path_result["candidate_record_count"] = len(records)
        audit["parsed_record_count"] += len(records)
        audit["candidate_record_count"] += len(records)
        for record in records:
            event = task_to_event(record, path=path, collected_at=collected_at)
            filter_reason = task_scope_policy_filter_reason(event, scope_policy)
            if filter_reason:
                path_result["scope_policy_filtered_record_count"] += 1
                audit["task_scope_policy"]["filtered_record_count"] += 1
                increment_counter(audit["task_scope_policy"], "filter_reason_counts", filter_reason)
                continue
            events.append(event)
            path_result["emitted_event_count"] += 1
            if limit is not None and len(events) >= limit:
                audit["emitted_event_count"] = len(events[:limit])
                finalize_audit(audit)
                return events[:limit], audit
        if records and not path_result["emitted_event_count"] and path_result["scope_policy_filtered_record_count"]:
            path_result["status"] = "filtered_by_scope_policy"
    audit["emitted_event_count"] = len(events)
    finalize_audit(audit)
    if not events and audit.get("task_scope_policy_filtered_all"):
        events = [gap_event(collected_at=collected_at, reason="task_scope_policy_filtered_all", collection_audit=audit)]
        audit["emitted_event_count"] = len(events)
    return events, audit


def new_collection_audit(
    inputs: List[str],
    paths: List[Path],
    *,
    limit: Optional[int] = None,
    scope_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task_scope_policy = scope_policy or build_task_scope_policy()
    return {
        "source_type": "authorized_local_ticktick_export",
        "input_count": len(inputs),
        "resolved_input_file_count": len(paths),
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "skipped_archive_member_reason_counts": {},
        "parsed_record_count": 0,
        "candidate_record_count": 0,
        "emitted_event_count": 0,
        "limit": limit,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "real_account_adapter_used": False,
        "task_scope_policy": {
            **task_scope_policy,
            "filtered_record_count": 0,
            "filter_reason_counts": {},
            "policy_does_not_assert_investment_relevance": True,
        },
        "task_scope_policy_filtered_all": False,
        "path_results": [],
    }


def build_task_scope_policy(
    *,
    allow_source_apps: Optional[Sequence[str]] = None,
    deny_source_apps: Optional[Sequence[str]] = None,
    allow_projects: Optional[Sequence[str]] = None,
    deny_projects: Optional[Sequence[str]] = None,
    allow_tags: Optional[Sequence[str]] = None,
    deny_tags: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "enabled": False,
        "allow_source_apps": split_policy_terms(allow_source_apps),
        "deny_source_apps": split_policy_terms(deny_source_apps),
        "allow_projects": split_policy_terms(allow_projects),
        "deny_projects": split_policy_terms(deny_projects),
        "allow_tags": split_policy_terms(allow_tags),
        "deny_tags": split_policy_terms(deny_tags),
        "allow_keywords": split_policy_terms(allow_keywords),
        "deny_keywords": split_policy_terms(deny_keywords),
    }
    policy["enabled"] = any(policy[key] for key in policy if key != "enabled")
    return policy


def split_policy_terms(values: Optional[Sequence[str]]) -> List[str]:
    terms: List[str] = []
    for value in values or []:
        for part in re.split(r"[,，]", str(value)):
            term = part.strip()
            if term:
                terms.append(term)
    return sorted(set(terms))


def task_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy.get("enabled"):
        return None
    source_app = str((event.get("data") or {}).get("source_app") or (event.get("raw_ref") or {}).get("source_app") or "").lower()
    project_surface = task_project_surface(event)
    tag_surface = task_tag_surface(event)
    keyword_surface = task_keyword_surface(event)

    if policy_hit(policy.get("deny_source_apps", []), source_app):
        return "source_app_denied"
    if policy_hit(policy.get("deny_projects", []), project_surface):
        return "project_denied"
    if policy_hit(policy.get("deny_tags", []), tag_surface):
        return "tag_denied"
    if policy_hit(policy.get("deny_keywords", []), keyword_surface):
        return "keyword_denied"
    if policy.get("allow_source_apps") and not policy_hit(policy.get("allow_source_apps", []), source_app):
        return "source_app_not_allowed"
    if policy.get("allow_projects") and not policy_hit(policy.get("allow_projects", []), project_surface):
        return "project_not_allowed"
    if policy.get("allow_tags") and not policy_hit(policy.get("allow_tags", []), tag_surface):
        return "tag_not_allowed"
    if policy.get("allow_keywords") and not policy_hit(policy.get("allow_keywords", []), keyword_surface):
        return "keyword_not_allowed"
    return None


def task_project_surface(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    parts = [
        data.get("project_name"),
        data.get("project_id"),
        raw_ref.get("project_id"),
        raw_ref.get("path"),
        raw_ref.get("archive_member"),
    ]
    return " ".join(str(part) for part in parts if part not in (None, "")).lower()


def task_tag_surface(event: Dict[str, Any]) -> str:
    tags = (event.get("data") or {}).get("tags") or []
    if isinstance(tags, list):
        return " ".join(str(tag) for tag in tags if str(tag)).lower()
    return str(tags).lower()


def task_keyword_surface(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    checklist_titles = []
    for item in data.get("checklist_items") or []:
        if isinstance(item, dict) and item.get("title"):
            checklist_titles.append(str(item["title"]))
    parts = [
        data.get("title"),
        data.get("content_preview"),
        data.get("project_name"),
        " ".join(str(tag) for tag in data.get("tags") or []),
        " ".join(checklist_titles),
        (event.get("raw_ref") or {}).get("path"),
        (event.get("raw_ref") or {}).get("archive_member"),
    ]
    return " ".join(str(part) for part in parts if part not in (None, "")).lower()


def policy_hit(patterns: Sequence[str], surface: str) -> Optional[str]:
    lowered = surface.lower()
    for pattern in patterns:
        probe = str(pattern).strip().lower()
        if probe and probe in lowered:
            return str(pattern)
    return None


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
    if path.suffix.lower() == ".zip":
        return parse_zip(path, audit=audit)
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


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
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
    start_time = normalize_time(start)
    due_time = normalize_time(due)
    completed_time = normalize_time(completed)
    checklist_items = checklist_items_for(record)
    checklist_completed = sum(1 for item in checklist_items if item.get("is_completed") is True)
    checklist_total = len(checklist_items)
    resolved_collected_at = collected_at or now_iso()
    event_time = due_time or start_time or completed_time or resolved_collected_at
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
        "start": start_time,
        "due": due_time,
        "completed_at": completed_time,
        "time_zone": first(record, ["timeZone", "time_zone", "timezone", "tz", "时区"]),
        "is_all_day": bool_value(first(record, ["isAllDay", "is_all_day", "all_day", "全天"])),
        **task_time_quality(start_time, due_time),
        "is_completed": is_completed(status, completed),
        "is_overdue": is_overdue(due, completed, collected_at),
        "recurrence": recurrence,
        "recurrence_frequency": recurrence_frequency(recurrence),
        "reminders": reminders,
        "tags": tags_for(record),
        "checklist_items": checklist_items,
        "checklist_total": checklist_total if checklist_total else None,
        "checklist_completed": checklist_completed if checklist_total else None,
        "checklist_pending": (checklist_total - checklist_completed) if checklist_total else None,
        "checklist_completion_rate": round(checklist_completed / checklist_total, 4) if checklist_total else None,
        "has_checklist": bool(checklist_total),
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
        "collected_at": resolved_collected_at,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["task", "work_confidential"],
        },
        "wiki_targets": ["internal.productivity.tasks"],
    }


def gap_event(
    *,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_time = collected_at or now_iso()
    audit = collection_audit or {}
    policy = audit.get("task_scope_policy") if isinstance(audit.get("task_scope_policy"), dict) else {}
    status_by_reason = {
        "ticktick_authorized_input_missing": "needs_ticktick_authorized_input",
        "task_scope_policy_filtered_all": "scope_policy_filtered_all",
    }
    messages = {
        "ticktick_authorized_input_missing": "No user-authorized TickTick/Dida task export was provided.",
        "task_scope_policy_filtered_all": "All user-authorized task records were excluded by the task authorization scope policy.",
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, "gap", reason, event_time),
        "collector": COLLECTOR,
        "source": "滴答清单授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": event_time,
        "collected_at": event_time,
        "data": {
            "subtype": "collector_gap",
            "action_type": "collector_gap",
            "gap": reason,
            "status": status_by_reason.get(reason, reason),
            "profile_type": "task_collection_gap",
            "message": messages.get(reason, "Task collection produced a traceable gap."),
            "candidate_record_count": int(audit.get("candidate_record_count") or 0),
            "task_event_count": 0,
            "retained_task_count": 0,
            "scope_policy_filtered_record_count": int(policy.get("filtered_record_count") or 0),
            "scope_policy_filter_reason_counts": policy.get("filter_reason_counts") or {},
            "policy_is_user_authorization_scope": bool(policy.get("enabled")),
            "policy_does_not_assert_investment_relevance": True,
            "task_fact_claimed": False,
            "investment_task_fact_claimed": False,
            "investment_conclusion_claimed": False,
            "complete_task_list_claimed": False,
            "task_service_token_collected": False,
            "collector_writes_investor_wiki_directly": False,
        },
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "scope_policy_enabled": bool(policy.get("enabled")),
        },
        "privacy": {"sensitive": True, "local_only": True, "contains": ["task", "collection_gap"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    task_events = [event for event in events if event.get("kind") == "task"]
    gap_event_count = len(events) - len(task_events)
    source_app_counts = Counter(source_app_for(event) for event in events if source_app_for(event) != "unknown")
    observed_apps = sorted(app for app, count in source_app_counts.items() if count)
    observed_expected = [app for app in EXPECTED_P1_TASK_PLATFORMS if source_app_counts.get(app)]
    missing_expected = [app for app in EXPECTED_P1_TASK_PLATFORMS if not source_app_counts.get(app)]
    unknown_event_count = sum(count for app, count in source_app_counts.items() if app not in EXPECTED_P1_TASK_PLATFORMS)
    readiness_status = task_readiness_status(events, collection_audit, gap_only=gap_only)
    return {
        "schema": "collectorx.ticktick.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "task_event_count": len(task_events),
        "gap_event_count": gap_event_count,
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
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_task_classification_done": False,
            "required_lens": "task-calendar-investor",
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": readiness_status,
            "can_enter_finclaw": readiness_status == "events_collected",
            "can_claim_investment_tasks": False,
            "source_collection_scope": task_source_collection_scope(readiness_status),
            "platform_coverage_status": platform_coverage_status(events, missing_expected),
            "next_action": task_next_action(readiness_status),
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


def task_readiness_status(
    events: List[Dict[str, Any]],
    collection_audit: Optional[Dict[str, Any]],
    *,
    gap_only: bool,
) -> str:
    if gap_only:
        if collection_audit and collection_audit.get("task_scope_policy_filtered_all"):
            return "scope_policy_filtered_all"
        return "needs_ticktick_authorized_input"
    if events:
        return "events_collected"
    if collection_audit and collection_audit.get("task_scope_policy_filtered_all"):
        return "scope_policy_filtered_all"
    return "no_task_events_collected"


def task_next_action(status: str) -> str:
    if status == "needs_ticktick_authorized_input":
        return "Provide authorized TickTick export/API output."
    if status == "scope_policy_filtered_all":
        return "Check task source-app/project/tag/keyword filters or provide a broader authorized task export."
    if status == "events_collected":
        return "Feed task events into task-calendar-investor lens."
    return "Provide authorized TickTick/Dida task records."


def task_source_collection_scope(status: str) -> str:
    if status == "needs_ticktick_authorized_input":
        return "none"
    if status == "scope_policy_filtered_all":
        return "authorized_input_filtered_by_scope_policy"
    if status == "events_collected":
        return "partial_authorized_input"
    return "none"


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
        f"- task_event_count: {manifest.get('task_event_count', 0)}",
        f"- gap_event_count: {manifest.get('gap_event_count', 0)}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- observed_platforms: `{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
        f"- missing_expected_platforms: `{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- overdue_tasks: {manifest['time_status_summary']['overdue_task_count']}",
        f"- invalid_time_ranges: {manifest['time_status_summary']['events_with_invalid_time_range']}",
        f"- checklist_tasks: {manifest['time_status_summary']['tasks_with_checklist']}",
        f"- checklist_items: {manifest['time_status_summary']['checklist_item_total']}",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
        "",
        "Generic task events are not written to the investor Wiki directly. Use the task-calendar-investor lens.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events, collection_audit = collect_from_inputs_with_audit(
        args.input or [],
        collected_at=collected_at,
        limit=args.limit,
        allow_source_apps=args.allow_source_app,
        deny_source_apps=args.deny_source_app,
        allow_projects=args.allow_project,
        deny_projects=args.deny_project,
        allow_tags=args.allow_tag,
        deny_tags=args.deny_tag,
        allow_keywords=args.allow_keyword,
        deny_keywords=args.deny_keyword,
    )
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    if out_dir:
        write_jsonl(out_dir / "exports" / COLLECTOR / "events.jsonl", events)
        manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
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
    add_task_scope_policy_args(p_collect)
    p_collect.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


def add_task_scope_policy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-source-app", action="append", help="Only keep tasks from this source app. Repeat or comma-separate.")
    parser.add_argument("--deny-source-app", action="append", help="Drop tasks from this source app. Repeat or comma-separate.")
    parser.add_argument("--allow-project", action="append", help="Only keep tasks whose project/list name contains this text. Repeat or comma-separate.")
    parser.add_argument("--deny-project", action="append", help="Drop tasks whose project/list name contains this text. Repeat or comma-separate.")
    parser.add_argument("--allow-tag", action="append", help="Only keep tasks with this tag. Repeat or comma-separate.")
    parser.add_argument("--deny-tag", action="append", help="Drop tasks with this tag. Repeat or comma-separate.")
    parser.add_argument("--allow-keyword", action="append", help="Only keep tasks whose title/content/checklist contains this text. Repeat or comma-separate.")
    parser.add_argument("--deny-keyword", action="append", help="Drop tasks whose title/content/checklist contains this text. Repeat or comma-separate.")


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


def checklist_items_for(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = (
        record.get("items")
        or record.get("checklist")
        or record.get("checklistItems")
        or record.get("subtasks")
        or record.get("subTasks")
        or record.get("子任务")
        or record.get("清单项")
        or []
    )
    if not isinstance(raw, list):
        return []
    items: List[Dict[str, Any]] = []
    for index, item in enumerate(raw[:200], start=1):
        if isinstance(item, dict):
            title = first(item, ["title", "name", "content", "desc", "任务", "标题", "内容"])
            status = first(item, ["status", "状态"])
            completed_at = normalize_time(first(item, ["completedTime", "completed_time", "完成时间"]))
            normalized = {
                "id": first(item, ["id", "item_id"]),
                "title": title,
                "status": status,
                "completed_at": completed_at,
                "start": normalize_time(first(item, ["startDate", "start_date", "start", "开始时间"])),
                "due": normalize_time(first(item, ["dueDate", "due_date", "due", "截止时间"])),
                "time_zone": first(item, ["timeZone", "time_zone", "timezone", "tz", "时区"]),
                "sort_order": first(item, ["sortOrder", "sort_order", "排序"]),
                "is_completed": checklist_item_completed(status, completed_at),
            }
        else:
            normalized = {
                "id": None,
                "title": str(item),
                "status": None,
                "completed_at": None,
                "start": None,
                "due": None,
                "time_zone": None,
                "sort_order": str(index),
                "is_completed": False,
            }
        items.append({key: value for key, value in normalized.items() if value not in (None, "", [], {})})
    return items


def checklist_item_completed(status: Optional[str], completed_at: Optional[str]) -> bool:
    if completed_at:
        return True
    if status is None:
        return False
    text = str(status).lower()
    return text in {"1", "2", "done", "completed", "complete", "已完成"}


def is_completed(status: Optional[str], completed: Optional[str]) -> bool:
    if completed:
        return True
    if status is None:
        return False
    text = str(status).lower()
    return text in {"2", "done", "completed", "complete", "已完成"}


def bool_value(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "全天"}:
        return True
    if text in {"0", "false", "no", "n", "否"}:
        return False
    return None


def normalize_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is not None:
        return parsed.isoformat(timespec="seconds")
    return str(value)


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
        if text.isdigit() and len(text) >= 13:
            return datetime.fromtimestamp(int(text[:13]) / 1000, tz=CN_TZ)
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1] + "+00:00")
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=CN_TZ)
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return datetime.fromisoformat(text + "T23:59:59+08:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=CN_TZ)
        return parsed
    except ValueError:
        return None


def task_time_quality(start: Optional[str], due: Optional[str]) -> Dict[str, Any]:
    start_dt = parse_datetime(start)
    due_dt = parse_datetime(due)
    metadata: Dict[str, Any] = {"has_time_range": bool(start and due)}
    if start_dt is None or due_dt is None:
        return metadata
    order_valid = due_dt >= start_dt
    metadata["time_order_valid"] = order_valid
    if order_valid:
        metadata["duration_minutes"] = int((due_dt - start_dt).total_seconds() // 60)
    return metadata


def recurrence_frequency(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    match = re.search(r"FREQ=([A-Z]+)", text.upper())
    if match:
        return match.group(1).lower()
    lowered = text.lower()
    for token in ("daily", "weekly", "monthly", "yearly"):
        if token in lowered:
            return token
    for token, label in {"每天": "daily", "每日": "daily", "每周": "weekly", "每月": "monthly", "每年": "yearly"}.items():
        if token in text:
            return label
    return "custom"


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


def time_status_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    task_events = [event for event in events if event.get("kind") == "task"]
    durations = [
        int((event.get("data") or {}).get("duration_minutes"))
        for event in task_events
        if isinstance((event.get("data") or {}).get("duration_minutes"), int)
    ]
    checklist_totals = [
        int((event.get("data") or {}).get("checklist_total"))
        for event in task_events
        if isinstance((event.get("data") or {}).get("checklist_total"), int)
    ]
    checklist_completed = [
        int((event.get("data") or {}).get("checklist_completed"))
        for event in task_events
        if isinstance((event.get("data") or {}).get("checklist_completed"), int)
    ]
    checklist_rates = [
        float((event.get("data") or {}).get("checklist_completion_rate"))
        for event in task_events
        if isinstance((event.get("data") or {}).get("checklist_completion_rate"), (int, float))
    ]
    recurrence_frequency_counts = Counter(
        str((event.get("data") or {}).get("recurrence_frequency"))
        for event in task_events
        if (event.get("data") or {}).get("recurrence_frequency")
    )
    return {
        "task_event_count": len(task_events),
        "completed_task_count": sum(1 for event in task_events if (event.get("data") or {}).get("is_completed") is True),
        "pending_task_count": sum(1 for event in task_events if (event.get("data") or {}).get("is_completed") is False),
        "overdue_task_count": sum(1 for event in task_events if (event.get("data") or {}).get("is_overdue") is True),
        "events_with_start": sum(1 for event in task_events if (event.get("data") or {}).get("start")),
        "events_with_due": sum(1 for event in task_events if (event.get("data") or {}).get("due")),
        "events_with_time_zone": sum(1 for event in task_events if (event.get("data") or {}).get("time_zone")),
        "all_day_task_count": sum(1 for event in task_events if (event.get("data") or {}).get("is_all_day") is True),
        "events_with_time_range": sum(1 for event in task_events if (event.get("data") or {}).get("has_time_range") is True),
        "events_with_invalid_time_range": sum(1 for event in task_events if (event.get("data") or {}).get("time_order_valid") is False),
        "events_with_duration_minutes": len(durations),
        "min_duration_minutes": min(durations) if durations else 0,
        "max_duration_minutes": max(durations) if durations else 0,
        "average_duration_minutes": round(sum(durations) / len(durations), 1) if durations else 0,
        "events_with_completion_time": sum(1 for event in task_events if (event.get("data") or {}).get("completed_at")),
        "events_with_recurrence": sum(1 for event in task_events if (event.get("data") or {}).get("recurrence")),
        "events_with_recurrence_frequency": sum(1 for event in task_events if (event.get("data") or {}).get("recurrence_frequency")),
        "recurrence_frequency_counts": dict(sorted(recurrence_frequency_counts.items())),
        "events_with_reminders": sum(1 for event in task_events if (event.get("data") or {}).get("reminders")),
        "tasks_with_checklist": sum(1 for event in task_events if (event.get("data") or {}).get("has_checklist") is True),
        "tasks_without_checklist": sum(1 for event in task_events if (event.get("data") or {}).get("has_checklist") is not True),
        "tasks_with_complete_checklist": sum(
            1
            for event in task_events
            if (event.get("data") or {}).get("has_checklist") is True
            and (event.get("data") or {}).get("checklist_pending") == 0
        ),
        "tasks_with_incomplete_checklist": sum(
            1
            for event in task_events
            if (event.get("data") or {}).get("has_checklist") is True
            and int((event.get("data") or {}).get("checklist_pending") or 0) > 0
        ),
        "checklist_item_total": sum(checklist_totals),
        "checklist_item_completed_count": sum(checklist_completed),
        "checklist_item_pending_count": sum(checklist_totals) - sum(checklist_completed),
        "average_checklist_completion_rate": round(sum(checklist_rates) / len(checklist_rates), 4) if checklist_rates else 0,
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
    scope_policy = audit.get("task_scope_policy") or {}
    scope_policy["filter_reason_counts"] = dict(sorted((scope_policy.get("filter_reason_counts") or {}).items()))
    audit["task_scope_policy"] = scope_policy
    audit["task_scope_policy_filtered_all"] = (
        bool(scope_policy.get("enabled"))
        and int(audit.get("candidate_record_count") or 0) > 0
        and int(audit.get("emitted_event_count") or 0) == 0
    )
    return audit


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
