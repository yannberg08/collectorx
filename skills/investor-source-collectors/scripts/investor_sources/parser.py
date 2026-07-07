"""Input parsers for investor source evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

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
) -> List[Dict[str, Any]]:
    get_profile(source_id)
    paths = list(iter_input_paths(inputs))
    if not paths:
        return [build_gap_event(source_id, collected_at=collected_at)]

    events: List[Dict[str, Any]] = []
    for path in paths:
        events.extend(parse_path(source_id, path, collected_at=collected_at, include_content=include_content))
        if limit is not None and len(events) >= limit:
            return events[:limit]
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
) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in TABLE_EXTENSIONS:
        return parse_table(source_id, path, collected_at=collected_at)
    if suffix in JSON_EXTENSIONS:
        return parse_json_like(source_id, path, collected_at=collected_at)
    if suffix in TEXT_EXTENSIONS:
        return [parse_text_file(source_id, path, collected_at=collected_at, include_content=include_content)]
    return [parse_metadata_file(source_id, path, collected_at=collected_at)]


def parse_table(source_id: str, path: Path, *, collected_at: Optional[str]) -> List[Dict[str, Any]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    text = path.read_text(encoding="utf-8-sig")
    rows = csv.DictReader(text.splitlines(), delimiter=delimiter)
    events: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        record = {str(key): value for key, value in row.items() if key is not None}
        events.append(
            build_event(
                source_id=source_id,
                source_label=str(path),
                record=record,
                raw_ref={"path": str(path), "row": index, "parser": "csv"},
                collected_at=collected_at,
            )
        )
    return events


def parse_json_like(source_id: str, path: Path, *, collected_at: Optional[str]) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
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
    for index, item in enumerate(items, start=1):
        record = item if isinstance(item, dict) else {"value": item}
        events.append(
            build_event(
                source_id=source_id,
                source_label=str(path),
                record=record,
                raw_ref={"path": str(path), "row": index, "parser": "json"},
                collected_at=collected_at,
            )
        )
    return events


def parse_text_file(
    source_id: str,
    path: Path,
    *,
    collected_at: Optional[str],
    include_content: bool,
) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    record: Dict[str, Any] = {
        "title": path.stem,
        "path": str(path),
        "content_preview": text[:1200],
        "byte_size": path.stat().st_size,
    }
    if include_content:
        record["content"] = text
    return build_event(
        source_id=source_id,
        source_label=str(path),
        record=record,
        raw_ref={"path": str(path), "parser": "text", "byte_size": path.stat().st_size},
        collected_at=collected_at,
        event_kind=kind_for_text_source(source_id),
    )


def parse_metadata_file(source_id: str, path: Path, *, collected_at: Optional[str]) -> Dict[str, Any]:
    record = {
        "title": path.stem,
        "path": str(path),
        "extension": path.suffix.lower(),
        "byte_size": path.stat().st_size,
        "metadata_only": True,
    }
    return build_event(
        source_id=source_id,
        source_label=str(path),
        record=record,
        raw_ref={"path": str(path), "parser": "metadata", "byte_size": path.stat().st_size},
        collected_at=collected_at,
        event_kind="file",
    )


def kind_for_text_source(source_id: str) -> str:
    default = get_profile(source_id)["default_kind"]
    if default in {"message", "email", "task", "calendar"}:
        return default
    if source_id in {"research-documents", "wechat-article-favorites"}:
        return "file"
    return "note"
