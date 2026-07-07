#!/usr/bin/env python3
"""Convert authorized TickTick/Dida task exports into CollectorX events."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "ticktick"
CN_TZ = timezone(timedelta(hours=8))


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
                if child.is_file() and child.suffix.lower() in {".json", ".jsonl", ".ndjson"}:
                    yield child
        elif path.is_file():
            yield path


def parse_path(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        rows = extract_tasks(loaded)
    return [row for row in rows if isinstance(row, dict)]


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
    data = {
        "title": title,
        "content_preview": content[:1000],
        "project_id": first(record, ["projectId", "project_id", "清单ID"]),
        "project_name": first(record, ["projectName", "project_name", "清单", "项目"]),
        "task_id": first(record, ["id", "task_id"]),
        "status": status,
        "priority": first(record, ["priority", "优先级"]),
        "start": start,
        "due": due,
        "completed_at": completed,
        "is_completed": is_completed(status, completed),
        "tags": tags_for(record),
        "raw": record,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, data.get("task_id"), title, due, completed),
        "collector": COLLECTOR,
        "source": "滴答清单用户授权任务数据",
        "owner_scope": "personal",
        "kind": "task",
        "time": normalize_time(due or start or completed),
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "task_id": data.get("task_id"),
            "project_id": data.get("project_id"),
        },
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
    return {
        "schema": "collectorx.ticktick.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "collection_readiness": {
            "status": "needs_ticktick_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_tasks": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized TickTick export/API output." if gap_only else "Feed task events into task-calendar-investor lens.",
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
        "# TickTick Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
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
    p_collect = sub.add_parser("collect", help="Parse local TickTick task JSON exports.")
    p_collect.add_argument("--input", action="append", help="Authorized task JSON/JSONL file or folder.")
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


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"


if __name__ == "__main__":
    raise SystemExit(main())
