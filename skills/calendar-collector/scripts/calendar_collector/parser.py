"""Parse authorized calendar exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


COLLECTOR = "calendar"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_RECORD_EXTENSIONS = {".ics", ".json", ".jsonl", ".ndjson", ".csv", ".tsv"}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
EXPECTED_P1_CALENDAR_PLATFORMS = (
    "apple_calendar",
    "google_calendar",
    "outlook_calendar",
    "feishu_calendar",
    "dingtalk_calendar",
    "wecom_calendar",
    "tencent_meeting_calendar",
)
GENERIC_CALENDAR_PLATFORMS = {"ics_export", "csv_export", "calendar_export"}
SOURCE_PATH_KEY = "_collectorx_source_path"
SOURCE_PLATFORM_KEY = "_collectorx_source_platform"
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
CALENDAR_RECOMMENDED_FIELDS = (
    "source_platform",
    "title",
    "calendar_name",
    "event_id",
    "start",
    "end",
    "timezone",
    "location",
    "meeting_url",
    "organizer",
    "attendees",
    "recurrence",
    "reminders",
    "time",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_source_platforms: Optional[Sequence[str]] = None,
    deny_source_platforms: Optional[Sequence[str]] = None,
    allow_calendars: Optional[Sequence[str]] = None,
    deny_calendars: Optional[Sequence[str]] = None,
    allow_attendees: Optional[Sequence[str]] = None,
    deny_attendees: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(
        inputs,
        collected_at=collected_at,
        limit=limit,
        allow_source_platforms=allow_source_platforms,
        deny_source_platforms=deny_source_platforms,
        allow_calendars=allow_calendars,
        deny_calendars=deny_calendars,
        allow_attendees=allow_attendees,
        deny_attendees=deny_attendees,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_source_platforms: Optional[Sequence[str]] = None,
    deny_source_platforms: Optional[Sequence[str]] = None,
    allow_calendars: Optional[Sequence[str]] = None,
    deny_calendars: Optional[Sequence[str]] = None,
    allow_attendees: Optional[Sequence[str]] = None,
    deny_attendees: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    paths = list(iter_paths(input_list))
    scope_policy = build_calendar_scope_policy(
        allow_source_platforms=allow_source_platforms,
        deny_source_platforms=deny_source_platforms,
        allow_calendars=allow_calendars,
        deny_calendars=deny_calendars,
        allow_attendees=allow_attendees,
        deny_attendees=deny_attendees,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    audit = new_collection_audit(input_list, paths, limit=limit, scope_policy=scope_policy)
    if not paths:
        events = [gap_event(collected_at=collected_at, reason="calendar_authorized_input_missing")]
        audit["emitted_event_count"] = len(events)
        finalize_audit(audit)
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
        for row, record in enumerate(records, start=1):
            event = record_to_event(record, path=path, row=row, collected_at=collected_at)
            filter_reason = calendar_scope_policy_filter_reason(event, scope_policy)
            if filter_reason:
                path_result["scope_policy_filtered_record_count"] += 1
                audit["calendar_scope_policy"]["filtered_record_count"] += 1
                increment_counter(audit["calendar_scope_policy"], "filter_reason_counts", filter_reason)
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
    return events, audit


def new_collection_audit(
    inputs: List[str],
    paths: List[Path],
    *,
    limit: Optional[int] = None,
    scope_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    calendar_scope_policy = scope_policy or build_calendar_scope_policy()
    return {
        "source_type": "authorized_local_calendar_export",
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
        "calendar_scope_policy": {
            **calendar_scope_policy,
            "filtered_record_count": 0,
            "filter_reason_counts": {},
            "policy_does_not_assert_investment_relevance": True,
        },
        "calendar_scope_policy_filtered_all": False,
        "path_results": [],
    }


def build_calendar_scope_policy(
    *,
    allow_source_platforms: Optional[Sequence[str]] = None,
    deny_source_platforms: Optional[Sequence[str]] = None,
    allow_calendars: Optional[Sequence[str]] = None,
    deny_calendars: Optional[Sequence[str]] = None,
    allow_attendees: Optional[Sequence[str]] = None,
    deny_attendees: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "enabled": False,
        "allow_source_platforms": split_policy_terms(allow_source_platforms),
        "deny_source_platforms": split_policy_terms(deny_source_platforms),
        "allow_calendars": split_policy_terms(allow_calendars),
        "deny_calendars": split_policy_terms(deny_calendars),
        "allow_attendees": split_policy_terms(allow_attendees),
        "deny_attendees": split_policy_terms(deny_attendees),
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


def calendar_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy.get("enabled"):
        return None
    source_platform = str(
        (event.get("data") or {}).get("source_platform") or (event.get("raw_ref") or {}).get("source_platform") or ""
    ).lower()
    calendar_surface = calendar_name_surface(event)
    attendee_surface = calendar_attendee_surface(event)
    keyword_surface = calendar_keyword_surface(event)

    if policy_hit(policy.get("deny_source_platforms", []), source_platform):
        return "source_platform_denied"
    if policy_hit(policy.get("deny_calendars", []), calendar_surface):
        return "calendar_denied"
    if policy_hit(policy.get("deny_attendees", []), attendee_surface):
        return "attendee_denied"
    if policy_hit(policy.get("deny_keywords", []), keyword_surface):
        return "keyword_denied"
    if policy.get("allow_source_platforms") and not policy_hit(policy.get("allow_source_platforms", []), source_platform):
        return "source_platform_not_allowed"
    if policy.get("allow_calendars") and not policy_hit(policy.get("allow_calendars", []), calendar_surface):
        return "calendar_not_allowed"
    if policy.get("allow_attendees") and not policy_hit(policy.get("allow_attendees", []), attendee_surface):
        return "attendee_not_allowed"
    if policy.get("allow_keywords") and not policy_hit(policy.get("allow_keywords", []), keyword_surface):
        return "keyword_not_allowed"
    return None


def calendar_name_surface(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    parts = [
        data.get("calendar_name"),
        data.get("source_platform"),
        raw_ref.get("path"),
        raw_ref.get("archive_member"),
    ]
    return " ".join(str(part) for part in parts if part not in (None, "")).lower()


def calendar_attendee_surface(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    parts: List[str] = []
    organizer = data.get("organizer")
    if organizer:
        parts.append(str(organizer))
    for attendee in data.get("attendees") or []:
        if isinstance(attendee, dict):
            parts.extend(str(value) for value in attendee.values() if value not in (None, ""))
        elif attendee not in (None, ""):
            parts.append(str(attendee))
    return " ".join(parts).lower()


def calendar_keyword_surface(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    parts = [
        data.get("title"),
        data.get("description_preview"),
        data.get("calendar_name"),
        data.get("location"),
        data.get("meeting_url"),
        data.get("source_platform"),
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
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return parse_zip(path, audit=audit)
    if suffix == ".ics":
        return parse_ics(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    return parse_json(path)


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_text(text, suffix=path.suffix.lower())


def parse_table_text(text: str, *, suffix: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    return [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    return parse_json_text(text, suffix=path.suffix.lower())


def parse_json_text(text: str, *, suffix: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_events(json.loads(text))
    return [row if isinstance(row, dict) else {"value": row} for row in rows]


def extract_events(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    for key in ("events", "calendar_events", "items", "records", "data"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_events(value)
            if not (len(nested) == 1 and nested[0] == value):
                return nested
    return [loaded]


def parse_ics(path: Path) -> List[Dict[str, Any]]:
    return parse_ics_text(path.read_text(encoding="utf-8-sig", errors="replace"))


def parse_ics_text(text: str) -> List[Dict[str, Any]]:
    lines = unfold_ics(text.splitlines())
    events: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    in_alarm = False
    for line in lines:
        if line.upper() == "BEGIN:VEVENT":
            current = {"attendees": [], "reminders": []}
            in_alarm = False
            continue
        if line.upper() == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            in_alarm = False
            continue
        if current is None:
            continue
        if line.upper() == "BEGIN:VALARM":
            in_alarm = True
            continue
        if line.upper() == "END:VALARM":
            in_alarm = False
            continue
        name, params, value = parse_ics_line(line)
        if not name:
            continue
        if in_alarm and name == "TRIGGER":
            current.setdefault("reminders", []).append(value)
            continue
        if name == "ATTENDEE":
            current.setdefault("attendees", []).append(parse_attendee(value, params))
            continue
        key = {
            "UID": "uid",
            "SUMMARY": "title",
            "DESCRIPTION": "description",
            "DTSTART": "start",
            "DTEND": "end",
            "DUE": "due",
            "LOCATION": "location",
            "ORGANIZER": "organizer",
            "URL": "meeting_url",
            "RRULE": "recurrence",
        }.get(name)
        if key:
            current[key] = parse_ics_time(value, params) if name in {"DTSTART", "DTEND", "DUE"} else unescape_ics(value)
            if name in {"DTSTART", "DTEND", "DUE"} and params.get("TZID"):
                current[f"{key}_timezone"] = params["TZID"]
            if name == "DTSTART" and "VALUE=DATE" in ";".join(f"{k}={v}" for k, v in params.items()).upper():
                current["is_all_day"] = True
    return events


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
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
                if suffix == ".ics":
                    parsed = parse_ics_text(text)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(text, suffix=suffix)
                else:
                    parsed = parse_json_text(text, suffix=suffix)
            except Exception:
                parsed = []
            path_label = f"{path}::{member_name}"
            for record in parsed:
                if isinstance(record, dict):
                    record[SOURCE_PATH_KEY] = path_label
                    record[SOURCE_PLATFORM_KEY] = infer_source_platform(record, path_label)
                    record[SOURCE_ARCHIVE_KEY] = str(path)
                    record[SOURCE_MEMBER_KEY] = member_name
                    events.append(record)
    return events


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


def unfold_ics(lines: List[str]) -> List[str]:
    unfolded: List[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line.rstrip("\r\n"))
    return unfolded


def parse_ics_line(line: str) -> Tuple[str, Dict[str, str], str]:
    if ":" not in line:
        return "", {}, ""
    left, value = line.split(":", 1)
    parts = left.split(";")
    name = parts[0].upper()
    params: Dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, param_value = part.split("=", 1)
            params[key.upper()] = param_value.strip('"')
    return name, params, value


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    title = first(record, ["title", "summary", "name", "subject", "标题", "日程", "主题"]) or "Untitled calendar event"
    description = first(record, ["description", "content", "body", "notes", "备注", "描述", "内容"]) or ""
    start = first(record, ["start", "start_time", "started_at", "dtstart", "开始时间", "开始"])
    end = first(record, ["end", "end_time", "ended_at", "dtend", "结束时间", "结束"])
    path_label = first(record, [SOURCE_PATH_KEY]) or str(path)
    source_platform = first(record, [SOURCE_PLATFORM_KEY]) or infer_source_platform(record, path_label)
    start_time = normalize_time(start)
    end_time = normalize_time(end)
    is_all_day = bool_value(first(record, ["is_all_day", "all_day", "全天"])) or bool(record.get("is_all_day"))
    time_quality = event_time_quality(start_time, end_time, is_all_day=is_all_day)
    data = {
        "source_platform": source_platform,
        "title": title,
        "description_preview": description[:1000],
        "description_length": len(description),
        "has_description": bool(description),
        "calendar_name": first(record, ["calendar", "calendar_name", "日历", "日历名称"]),
        "event_id": first(record, ["id", "uid", "event_id"]),
        "start": start_time,
        "end": end_time,
        "timezone": first(record, ["timezone", "tz", "start_timezone", "时区"]),
        "is_all_day": is_all_day,
        **time_quality,
        "location": first(record, ["location", "地点"]),
        "meeting_url": first(record, ["meeting_url", "url", "link", "会议链接", "链接"]),
        "organizer": normalize_person(first(record, ["organizer", "组织者"])),
        "attendees": attendees_for(record),
        "recurrence": first(record, ["recurrence", "rrule", "重复规则"]),
        "reminders": reminders_for(record),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}
    raw_ref = {
        "path": path_label,
        "row": row,
        "event_id": data.get("event_id"),
        "source_platform": source_platform,
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [], {})}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, data.get("event_id"), title, start, end),
        "collector": COLLECTOR,
        "source": "用户授权日历事件",
        "owner_scope": "personal",
        "kind": "calendar",
        "time": data.get("start") or data.get("end"),
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {"sensitive": True, "local_only": True, "contains": ["calendar", "work_confidential", "contact"]},
        "wiki_targets": ["internal.calendar.events"],
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "日历授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "gap": reason,
            "message": "No user-authorized calendar export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["calendar"]},
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
    source_platform_counts = Counter(source_platform_for(event) for event in events if source_platform_for(event) != "unknown")
    observed_platforms = sorted(platform for platform, count in source_platform_counts.items() if count)
    observed_expected = [platform for platform in EXPECTED_P1_CALENDAR_PLATFORMS if source_platform_counts.get(platform)]
    missing_expected = [platform for platform in EXPECTED_P1_CALENDAR_PLATFORMS if not source_platform_counts.get(platform)]
    unknown_event_count = sum(
        count
        for platform, count in source_platform_counts.items()
        if platform not in EXPECTED_P1_CALENDAR_PLATFORMS and platform not in GENERIC_CALENDAR_PLATFORMS
    )
    readiness_status = calendar_readiness_status(events, collection_audit, gap_only=gap_only)
    return {
        "schema": "collectorx.calendar.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "source_file_count": len({(event.get("raw_ref") or {}).get("path") for event in events if (event.get("raw_ref") or {}).get("path")}),
        "kind_counts": dict(sorted(kind_counts.items())),
        "platform_coverage": {
            "expected_p1_platforms": list(EXPECTED_P1_CALENDAR_PLATFORMS),
            "observed_platforms": observed_platforms,
            "observed_expected_platforms": observed_expected,
            "missing_expected_platforms": missing_expected,
            "source_platform_counts": dict(sorted(source_platform_counts.items())),
            "unknown_event_count": unknown_event_count,
            "real_account_validation": False,
        },
        "field_coverage": field_coverage(events),
        "time_surface_summary": time_surface_summary(events),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_calendar_classification_done": False,
            "required_lens": "task-calendar-investor",
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": readiness_status,
            "can_enter_finclaw": readiness_status == "events_collected",
            "can_claim_investment_calendar": False,
            "source_collection_scope": calendar_source_collection_scope(readiness_status),
            "platform_coverage_status": platform_coverage_status(events, missing_expected),
            "next_action": calendar_next_action(readiness_status),
        },
    }


def source_platform_for(event: Dict[str, Any]) -> str:
    value = event.get("data", {}).get("source_platform") or event.get("raw_ref", {}).get("source_platform") or "unknown"
    return str(value)


def platform_coverage_status(events: List[Dict[str, Any]], missing_expected: List[str]) -> str:
    if not events or all((event.get("data") or {}).get("gap") for event in events):
        return "no_platform_observed"
    if not missing_expected:
        return "all_expected_platforms_observed"
    return "partial_expected_platforms_observed"


def calendar_readiness_status(
    events: List[Dict[str, Any]],
    collection_audit: Optional[Dict[str, Any]],
    *,
    gap_only: bool,
) -> str:
    if gap_only:
        return "needs_calendar_authorized_input"
    if events:
        return "events_collected"
    if collection_audit and collection_audit.get("calendar_scope_policy_filtered_all"):
        return "scope_policy_filtered_all"
    return "no_calendar_events_collected"


def calendar_next_action(status: str) -> str:
    if status == "needs_calendar_authorized_input":
        return "Provide authorized ICS/JSON/CSV calendar export."
    if status == "scope_policy_filtered_all":
        return "Check calendar source-platform/calendar/attendee/keyword filters or provide a broader authorized calendar export."
    if status == "events_collected":
        return "Feed calendar events into task-calendar-investor lens."
    return "Provide authorized calendar records."


def calendar_source_collection_scope(status: str) -> str:
    if status == "needs_calendar_authorized_input":
        return "none"
    if status == "scope_policy_filtered_all":
        return "authorized_input_filtered_by_scope_policy"
    if status == "events_collected":
        return "partial_authorized_input"
    return "none"


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    calendar_events = [event for event in events if event.get("kind") == "calendar"]
    field_counts = {
        field: sum(1 for event in calendar_events if calendar_field_present(event, field))
        for field in CALENDAR_RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(CALENDAR_RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_description": sum(1 for event in calendar_events if (event.get("data") or {}).get("has_description")),
    }


def calendar_field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    data = event.get("data") or {}
    value = data.get(field)
    if field == "attendees":
        return bool(value)
    return value not in (None, "", [], {})


def time_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    calendar_events = [event for event in events if event.get("kind") == "calendar"]
    durations = [
        int((event.get("data") or {}).get("duration_minutes"))
        for event in calendar_events
        if isinstance((event.get("data") or {}).get("duration_minutes"), int)
    ]
    return {
        "calendar_event_count": len(calendar_events),
        "events_with_start": sum(1 for event in calendar_events if (event.get("data") or {}).get("start")),
        "events_with_end": sum(1 for event in calendar_events if (event.get("data") or {}).get("end")),
        "events_with_time_range": sum(1 for event in calendar_events if (event.get("data") or {}).get("has_time_range") is True),
        "events_without_start": sum(1 for event in calendar_events if not (event.get("data") or {}).get("start")),
        "events_without_end": sum(1 for event in calendar_events if not (event.get("data") or {}).get("end")),
        "all_day_event_count": sum(1 for event in calendar_events if (event.get("data") or {}).get("is_all_day") is True),
        "timed_event_count": sum(1 for event in calendar_events if (event.get("data") or {}).get("is_all_day") is not True),
        "multi_day_event_count": sum(1 for event in calendar_events if (event.get("data") or {}).get("is_multi_day") is True),
        "events_with_invalid_time_range": sum(1 for event in calendar_events if (event.get("data") or {}).get("time_order_valid") is False),
        "events_with_duration_minutes": len(durations),
        "min_duration_minutes": min(durations) if durations else 0,
        "max_duration_minutes": max(durations) if durations else 0,
        "average_duration_minutes": round(sum(durations) / len(durations), 1) if durations else 0,
        "events_with_meeting_url": sum(1 for event in calendar_events if (event.get("data") or {}).get("meeting_url")),
        "events_without_meeting_url": sum(1 for event in calendar_events if not (event.get("data") or {}).get("meeting_url")),
        "events_with_location": sum(1 for event in calendar_events if (event.get("data") or {}).get("location")),
        "events_with_attendees": sum(1 for event in calendar_events if (event.get("data") or {}).get("attendees")),
        "events_with_recurrence": sum(1 for event in calendar_events if (event.get("data") or {}).get("recurrence")),
        "events_with_reminders": sum(1 for event in calendar_events if (event.get("data") or {}).get("reminders")),
        "events_without_reminders": sum(1 for event in calendar_events if not (event.get("data") or {}).get("reminders")),
        "time_conflict_summary": calendar_time_conflict_summary(calendar_events),
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
    scope_policy = audit.get("calendar_scope_policy") or {}
    scope_policy["filter_reason_counts"] = dict(sorted((scope_policy.get("filter_reason_counts") or {}).items()))
    audit["calendar_scope_policy"] = scope_policy
    audit["calendar_scope_policy_filtered_all"] = (
        bool(scope_policy.get("enabled"))
        and int(audit.get("candidate_record_count") or 0) > 0
        and int(audit.get("emitted_event_count") or 0) == 0
    )
    return audit


def infer_source_platform(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["source_platform", "source_app", "calendar_source", "provider", "platform", "app", "来源", "平台"]) or ""
    probe = f"{explicit} {path_label} {first(record, ['calendar', 'calendar_name', '日历', '日历名称']) or ''}".lower()
    if "tencent" in probe or "腾讯会议" in probe:
        return "tencent_meeting_calendar"
    if "wecom" in probe or "work.weixin" in probe or "企业微信" in probe:
        return "wecom_calendar"
    if "dingtalk" in probe or "钉钉" in probe:
        return "dingtalk_calendar"
    if "feishu" in probe or "lark" in probe or "飞书" in probe:
        return "feishu_calendar"
    if "outlook" in probe or "office365" in probe or "microsoft" in probe:
        return "outlook_calendar"
    if "google" in probe or "gmail" in probe:
        return "google_calendar"
    if "apple" in probe or "icloud" in probe or "苹果" in probe:
        return "apple_calendar"
    if ".csv" in probe or ".tsv" in probe:
        return "csv_export"
    if ".ics" in probe:
        return "ics_export"
    return "calendar_export"


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def parse_attendee(value: str, params: Dict[str, str]) -> Dict[str, str]:
    attendee = {"value": unescape_ics(value)}
    if params.get("CN"):
        attendee["name"] = params["CN"]
    if params.get("ROLE"):
        attendee["role"] = params["ROLE"]
    return attendee


def attendees_for(record: Dict[str, Any]) -> List[Any]:
    raw = record.get("attendees") or record.get("participants") or record.get("参与人") or []
    if isinstance(raw, list):
        return [sanitized(item) for item in raw if item not in (None, "")]
    if isinstance(raw, str):
        return [part.strip() for part in re.split(r"[,，;；]", raw) if part.strip()]
    return []


def reminders_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("reminders") or record.get("alarm") or record.get("提醒") or []
    if isinstance(raw, list):
        return [str(item) for item in raw if item not in (None, "")]
    if isinstance(raw, str):
        return [part.strip() for part in re.split(r"[,，;；]", raw) if part.strip()]
    return []


def normalize_person(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return unescape_ics(value).replace("mailto:", "")


def normalize_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value)
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.fullmatch(r"\d{8}T\d{6}Z", text):
        dt = datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds")
    if re.fullmatch(r"\d{8}T\d{6}", text):
        dt = datetime.strptime(text, "%Y%m%dT%H%M%S").replace(tzinfo=CN_TZ)
        return dt.isoformat(timespec="seconds")
    return text


def parse_calendar_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1] + "+00:00")
        if re.fullmatch(r"\d{8}", text):
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=CN_TZ)
        if re.fullmatch(r"\d{8}T\d{6}Z", text):
            return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if re.fullmatch(r"\d{8}T\d{6}", text):
            return datetime.strptime(text, "%Y%m%dT%H%M%S").replace(tzinfo=CN_TZ)
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return datetime.fromisoformat(text + "T00:00:00+08:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=CN_TZ)
        return parsed
    except ValueError:
        return None


def event_time_quality(start: Optional[str], end: Optional[str], *, is_all_day: bool) -> Dict[str, Any]:
    start_dt = parse_calendar_datetime(start)
    end_dt = parse_calendar_datetime(end)
    metadata: Dict[str, Any] = {
        "has_time_range": bool(start and end),
    }
    if start_dt is None or end_dt is None:
        return metadata
    order_valid = end_dt >= start_dt
    metadata["time_order_valid"] = order_valid
    if not order_valid:
        metadata["is_multi_day"] = False
        return metadata
    duration_minutes = int((end_dt - start_dt).total_seconds() // 60)
    metadata["duration_minutes"] = duration_minutes
    if is_all_day:
        metadata["is_multi_day"] = (end_dt.date() - start_dt.date()).days > 1
    else:
        metadata["is_multi_day"] = start_dt.date() != end_dt.date()
    return metadata


def calendar_time_conflict_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, List[Tuple[datetime, datetime, str]]] = {}
    for event in events:
        data = event.get("data") or {}
        if data.get("is_all_day") is True:
            continue
        start_dt = parse_calendar_datetime(data.get("start"))
        end_dt = parse_calendar_datetime(data.get("end"))
        if start_dt is None or end_dt is None or end_dt <= start_dt:
            continue
        group = str(data.get("calendar_name") or data.get("source_platform") or "calendar")
        grouped.setdefault(group, []).append((start_dt, end_dt, str(event.get("id"))))

    checked_event_count = sum(len(items) for items in grouped.values())
    conflict_pair_count = 0
    conflict_event_ids: set[str] = set()
    sample_pairs: List[List[str]] = []
    for items in grouped.values():
        active: List[Tuple[datetime, str]] = []
        for start_dt, end_dt, event_id in sorted(items, key=lambda item: item[0]):
            active = [(active_end, active_id) for active_end, active_id in active if active_end > start_dt]
            for _active_end, active_id in active:
                conflict_pair_count += 1
                conflict_event_ids.update({active_id, event_id})
                if len(sample_pairs) < 10:
                    sample_pairs.append([active_id, event_id])
            active.append((end_dt, event_id))

    return {
        "checked_timed_event_count": checked_event_count,
        "conflict_pair_count": conflict_pair_count,
        "events_with_conflicts": len(conflict_event_ids),
        "sample_conflicting_event_ids": sorted(conflict_event_ids)[:20],
        "sample_conflict_pairs": sample_pairs,
    }


def parse_ics_time(value: str, params: Dict[str, str]) -> str:
    if params.get("VALUE", "").upper() == "DATE":
        return normalize_time(value) or value
    return normalize_time(value) or value


def bool_value(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    return str(value).lower() in {"1", "true", "yes", "y", "全天"}


def unescape_ics(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


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
