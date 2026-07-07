"""Parse authorized calendar exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


COLLECTOR = "calendar"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".ics", ".json", ".jsonl", ".ndjson", ".csv", ".tsv"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="calendar_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events


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
    if suffix == ".ics":
        return parse_ics(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    return parse_json(path)


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
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
    lines = unfold_ics(path.read_text(encoding="utf-8-sig", errors="replace").splitlines())
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
    data = {
        "title": title,
        "description_preview": description[:1000],
        "calendar_name": first(record, ["calendar", "calendar_name", "日历", "日历名称"]),
        "event_id": first(record, ["id", "uid", "event_id"]),
        "start": normalize_time(start),
        "end": normalize_time(end),
        "timezone": first(record, ["timezone", "tz", "start_timezone", "时区"]),
        "is_all_day": bool_value(first(record, ["is_all_day", "all_day", "全天"])) or bool(record.get("is_all_day")),
        "location": first(record, ["location", "地点"]),
        "meeting_url": first(record, ["meeting_url", "url", "link", "会议链接", "链接"]),
        "organizer": normalize_person(first(record, ["organizer", "组织者"])),
        "attendees": attendees_for(record),
        "recurrence": first(record, ["recurrence", "rrule", "重复规则"]),
        "reminders": reminders_for(record),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}
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
        "raw_ref": {"path": str(path), "row": row, "event_id": data.get("event_id")},
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


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    return {
        "schema": "collectorx.calendar.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "source_file_count": len({(event.get("raw_ref") or {}).get("path") for event in events if (event.get("raw_ref") or {}).get("path")}),
        "kind_counts": dict(sorted(kind_counts.items())),
        "collection_readiness": {
            "status": "needs_calendar_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_calendar": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized ICS/JSON/CSV calendar export." if gap_only else "Feed calendar events into task-calendar-investor lens.",
        },
    }


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
