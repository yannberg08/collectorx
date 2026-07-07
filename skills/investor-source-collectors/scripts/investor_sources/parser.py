"""Input parsers for investor source evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .classifier import classify_record, should_keep_event
from .events import build_event, build_gap_event
from .profiles import get_profile


TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm", ".eml", ".ics"}
TABLE_EXTENSIONS = {".csv", ".tsv"}
JSON_EXTENSIONS = {".json", ".jsonl", ".ndjson"}
METADATA_ONLY_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".png", ".jpg", ".jpeg", ".webp"}


def collect_events(
    source_id: str,
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    include_content: bool = False,
    limit: Optional[int] = None,
    min_score: float = 0.30,
    include_non_matches: bool = False,
) -> List[Dict[str, Any]]:
    get_profile(source_id)
    paths = list(iter_input_paths(inputs))
    if not paths:
        return [build_gap_event(source_id, collected_at=collected_at)]

    events: List[Dict[str, Any]] = []
    parsed_count = 0
    for path in paths:
        parsed = parse_path(
            source_id,
            path,
            collected_at=collected_at,
            include_content=include_content,
            min_score=min_score,
            include_non_matches=include_non_matches,
        )
        parsed_count += len(parsed.candidates)
        events.extend(parsed.events)
        if limit is not None and len(events) >= limit:
            return events[:limit]
    if not events:
        reason = "no_readable_input" if parsed_count == 0 else "no_investment_evidence_matched"
        return [build_gap_event(source_id, collected_at=collected_at, reason=reason)]
    return events


def iter_input_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and not child.name.startswith("."):
                    yield child
        elif path.is_file():
            yield path


def parse_path(
    source_id: str,
    path: Path,
    *,
    collected_at: Optional[str],
    include_content: bool,
    min_score: float,
    include_non_matches: bool,
) -> "ParseResult":
    suffix = path.suffix.lower()
    if suffix in TABLE_EXTENSIONS:
        return parse_table(
            source_id,
            path,
            collected_at=collected_at,
            min_score=min_score,
            include_non_matches=include_non_matches,
        )
    if suffix in JSON_EXTENSIONS:
        return parse_json_like(
            source_id,
            path,
            collected_at=collected_at,
            min_score=min_score,
            include_non_matches=include_non_matches,
        )
    if suffix in TEXT_EXTENSIONS:
        event = parse_text_file(
            source_id,
            path,
            collected_at=collected_at,
            include_content=include_content,
            min_score=min_score,
            include_non_matches=include_non_matches,
        )
        return ParseResult(candidates=[path], events=[event] if event else [])
    event = parse_metadata_file(
        source_id,
        path,
        collected_at=collected_at,
        min_score=min_score,
        include_non_matches=include_non_matches,
    )
    return ParseResult(candidates=[path], events=[event] if event else [])


class ParseResult:
    def __init__(self, *, candidates: List[Any], events: List[Dict[str, Any]]) -> None:
        self.candidates = candidates
        self.events = events


def parse_table(
    source_id: str,
    path: Path,
    *,
    collected_at: Optional[str],
    min_score: float,
    include_non_matches: bool,
) -> ParseResult:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    text = path.read_text(encoding="utf-8-sig")
    rows = csv.DictReader(text.splitlines(), delimiter=delimiter)
    events: List[Dict[str, Any]] = []
    candidates: List[Any] = []
    for index, row in enumerate(rows, start=1):
        record = {str(key): value for key, value in row.items() if key is not None}
        candidates.append(record)
        event = candidate_to_event(
            source_id,
            record,
            source_label=str(path),
            raw_ref={"path": str(path), "row": index, "parser": "csv"},
            collected_at=collected_at,
            min_score=min_score,
            include_non_matches=include_non_matches,
        )
        if event:
            events.append(event)
    return ParseResult(candidates=candidates, events=events)


def parse_json_like(
    source_id: str,
    path: Path,
    *,
    collected_at: Optional[str],
    min_score: float,
    include_non_matches: bool,
) -> ParseResult:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return ParseResult(candidates=[], events=[])
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        items = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        if isinstance(loaded, list):
            items = loaded
        elif isinstance(loaded, dict):
            for key in ("events", "items", "records", "data", "messages"):
                if isinstance(loaded.get(key), list):
                    items = loaded[key]
                    break
            else:
                items = [loaded]
        else:
            items = [{"value": loaded}]

    events: List[Dict[str, Any]] = []
    candidates: List[Any] = []
    for index, item in enumerate(items, start=1):
        record, source_label, raw_ref, event_kind, event_time = normalize_json_candidate(item, path, index)
        candidates.append(record)
        event = candidate_to_event(
            source_id,
            record,
            source_label=source_label,
            raw_ref=raw_ref,
            collected_at=collected_at,
            event_kind=event_kind,
            event_time=event_time,
            min_score=min_score,
            include_non_matches=include_non_matches,
        )
        if event:
            events.append(event)
    return ParseResult(candidates=candidates, events=events)


def parse_text_file(
    source_id: str,
    path: Path,
    *,
    collected_at: Optional[str],
    include_content: bool,
    min_score: float,
    include_non_matches: bool,
) -> Optional[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    record: Dict[str, Any] = {
        "title": path.stem,
        "path": str(path),
        "content_preview": text[:1200],
        "byte_size": path.stat().st_size,
    }
    if include_content:
        record["content"] = text
    return candidate_to_event(
        source_id=source_id,
        record=record,
        source_label=str(path),
        raw_ref={"path": str(path), "parser": "text", "byte_size": path.stat().st_size},
        collected_at=collected_at,
        event_kind=kind_for_text_source(source_id),
        min_score=min_score,
        include_non_matches=include_non_matches,
    )


def parse_metadata_file(
    source_id: str,
    path: Path,
    *,
    collected_at: Optional[str],
    min_score: float,
    include_non_matches: bool,
) -> Optional[Dict[str, Any]]:
    record = {
        "title": path.stem,
        "path": str(path),
        "extension": path.suffix.lower(),
        "byte_size": path.stat().st_size,
        "metadata_only": True,
    }
    return candidate_to_event(
        source_id=source_id,
        record=record,
        source_label=str(path),
        raw_ref={"path": str(path), "parser": "metadata", "byte_size": path.stat().st_size},
        collected_at=collected_at,
        event_kind="file",
        min_score=min_score,
        include_non_matches=include_non_matches,
    )


def normalize_json_candidate(item: Any, path: Path, index: int) -> tuple[Dict[str, Any], str, Dict[str, Any], Optional[str], Optional[str]]:
    if not isinstance(item, dict):
        return {"value": item}, str(path), {"path": str(path), "row": index, "parser": "json"}, None, None

    if item.get("schema") == "collectorx.event.v1":
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        record = {
            **data,
            "upstream_collector": item.get("collector"),
            "upstream_kind": item.get("kind"),
            "upstream_source": item.get("source"),
            "upstream_time": item.get("time"),
        }
        return (
            record,
            str(item.get("source") or path),
            {
                "path": str(path),
                "row": index,
                "parser": "collectorx.event.v1",
                "upstream_event_id": item.get("id"),
                "upstream_raw_ref": item.get("raw_ref") or {},
            },
            item.get("kind"),
            item.get("time"),
        )

    if "data" in item and isinstance(item["data"], dict) and set(item) <= {"id", "source", "data"}:
        record = item["data"]
        source_label = str(item.get("source") or path)
        raw_ref = {"path": str(path), "row": index, "parser": "wechat_collect", "upstream_event_id": item.get("id")}
        return record, source_label, raw_ref, "message", record.get("time")

    return item, str(path), {"path": str(path), "row": index, "parser": "json"}, None, None


def candidate_to_event(
    source_id: str,
    record: Dict[str, Any],
    *,
    source_label: str,
    raw_ref: Dict[str, Any],
    collected_at: Optional[str],
    min_score: float,
    include_non_matches: bool,
    event_kind: Optional[str] = None,
    event_time: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    classification = classify_record(source_id, record)
    if not should_keep_event(source_id, classification, min_score=min_score, include_non_matches=include_non_matches):
        return None
    return build_event(
        source_id=source_id,
        source_label=source_label,
        record=record,
        raw_ref=raw_ref,
        collected_at=collected_at,
        event_kind=event_kind,
        event_time=event_time,
        classification=classification,
    )


def kind_for_text_source(source_id: str) -> str:
    default = get_profile(source_id)["default_kind"]
    if default in {"message", "email", "task", "calendar"}:
        return default
    if source_id in {"research-documents", "wechat-article-favorites"}:
        return "file"
    return "note"
