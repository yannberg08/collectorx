"""Input parsers for investor source evidence."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .classifier import classify_record, should_keep_event
from .events import build_event, build_gap_event
from .profiles import get_profile


TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm", ".eml", ".ics"}
TABLE_EXTENSIONS = {".csv", ".tsv"}
JSON_EXTENSIONS = {".json", ".jsonl", ".ndjson"}
CONTENT_EXTRACT_EXTENSIONS = {".docx", ".pdf", ".xlsx", ".xlsm"}
METADATA_ONLY_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".png", ".jpg", ".jpeg", ".webp"}
RESEARCH_DOCUMENT_EXTENSIONS = (
    TEXT_EXTENSIONS
    | TABLE_EXTENSIONS
    | JSON_EXTENSIONS
    | CONTENT_EXTRACT_EXTENSIONS
    | METADATA_ONLY_EXTENSIONS
    | {".doc", ".ppt", ".key", ".numbers", ".bmp", ".gif", ".heic", ".heif"}
)
MAX_EXTRACTED_CHARS = 20000


class CollectionResult:
    def __init__(self, *, events: List[Dict[str, Any]], audit: Dict[str, Any]) -> None:
        self.events = events
        self.audit = audit


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
    return collect_events_with_audit(
        source_id,
        inputs,
        collected_at=collected_at,
        include_content=include_content,
        limit=limit,
        min_score=min_score,
        include_non_matches=include_non_matches,
    ).events


def collect_events_with_audit(
    source_id: str,
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    include_content: bool = False,
    limit: Optional[int] = None,
    min_score: float = 0.30,
    include_non_matches: bool = False,
) -> CollectionResult:
    get_profile(source_id)
    input_list = list(inputs)
    paths = list(iter_input_paths(input_list))
    audit = initial_collection_audit(
        source_id,
        input_list,
        paths,
        include_content=include_content,
        limit=limit,
        min_score=min_score,
        include_non_matches=include_non_matches,
    )
    if not paths:
        events = [build_gap_event(source_id, collected_at=collected_at)]
        finalize_collection_audit(audit, events, parsed_count=0)
        return CollectionResult(events=events, audit=audit)

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
            audit=audit,
        )
        parsed_count += len(parsed.candidates)
        events.extend(parsed.events)
        if limit is not None and len(events) >= limit:
            events = events[:limit]
            finalize_collection_audit(audit, events, parsed_count=parsed_count)
            return CollectionResult(events=events, audit=audit)
    if not events:
        reason = "no_readable_input" if parsed_count == 0 else "no_investment_evidence_matched"
        events = [build_gap_event(source_id, collected_at=collected_at, reason=reason)]
    finalize_collection_audit(audit, events, parsed_count=parsed_count)
    return CollectionResult(events=events, audit=audit)


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
    audit: Optional[Dict[str, Any]] = None,
) -> "ParseResult":
    suffix = path.suffix.lower()
    if audit is not None:
        audit_counter(audit, "extension_counts")[suffix or "<none>"] += 1
    if source_id == "research-documents" and suffix not in RESEARCH_DOCUMENT_EXTENSIONS:
        if audit is not None:
            audit["skipped_file_count"] += 1
            audit_counter(audit, "skipped_extension_counts")[suffix or "<none>"] += 1
        return ParseResult(candidates=[], events=[])
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
    if include_content and suffix in CONTENT_EXTRACT_EXTENSIONS:
        event = parse_content_file(
            source_id,
            path,
            collected_at=collected_at,
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


def initial_collection_audit(
    source_id: str,
    inputs: List[str],
    paths: List[Path],
    *,
    include_content: bool,
    limit: Optional[int],
    min_score: float,
    include_non_matches: bool,
) -> Dict[str, Any]:
    return {
        "source_id": source_id,
        "input_count": len(inputs),
        "resolved_input_file_count": len(paths),
        "candidate_record_count": 0,
        "matched_event_count": 0,
        "non_matched_event_count": 0,
        "filtered_candidate_count": 0,
        "skipped_file_count": 0,
        "extension_counts": {},
        "skipped_extension_counts": {},
        "parser_counts": {},
        "content_read_event_count": 0,
        "content_extract_status_counts": {},
        "include_content": include_content,
        "include_non_matches": include_non_matches,
        "min_score": min_score,
        "limit": limit,
        "content_extraction_policy": content_extraction_policy(source_id, include_content),
    }


def finalize_collection_audit(audit: Dict[str, Any], events: List[Dict[str, Any]], *, parsed_count: int) -> None:
    usable_events = [event for event in events if (event.get("data") or {}).get("payload", {}).get("signal_type") != "collector_preflight_gap"]
    audit["candidate_record_count"] = parsed_count
    audit["matched_event_count"] = sum(
        1
        for event in usable_events
        if ((event.get("data") or {}).get("classification") or {}).get("is_investment_evidence")
    )
    audit["non_matched_event_count"] = sum(
        1
        for event in usable_events
        if not ((event.get("data") or {}).get("classification") or {}).get("is_investment_evidence")
    )
    audit["filtered_candidate_count"] = max(0, parsed_count - len(usable_events))

    parser_counts: Counter[str] = Counter()
    content_status_counts: Counter[str] = Counter()
    content_read_count = 0
    for event in usable_events:
        raw_ref = event.get("raw_ref") or {}
        payload = (event.get("data") or {}).get("payload") or {}
        parser = raw_ref.get("parser")
        if parser:
            parser_counts[str(parser)] += 1
        if raw_ref.get("content_read"):
            content_read_count += 1
        extract = payload.get("content_extract") if isinstance(payload, dict) else None
        if isinstance(extract, dict):
            status = extract.get("status") or "unknown"
            content_status_counts[str(status)] += 1
    audit["parser_counts"] = dict(sorted(parser_counts.items()))
    audit["content_read_event_count"] = content_read_count
    audit["content_extract_status_counts"] = dict(sorted(content_status_counts.items()))
    audit["extension_counts"] = dict(sorted(audit_counter(audit, "extension_counts").items()))
    audit["skipped_extension_counts"] = dict(sorted(audit_counter(audit, "skipped_extension_counts").items()))


def content_extraction_policy(source_id: str, include_content: bool) -> Dict[str, Any]:
    if source_id != "research-documents":
        return {
            "include_content_enabled": include_content,
            "applies_to": "generic investor-source input parser",
        }
    return {
        "applies_to": "research-documents lens",
        "input_boundary": "user_selected_files_or_folders_only",
        "generic_filesystem_collector": "metadata_only",
        "content_read_requires_explicit_include_content": True,
        "include_content_enabled": include_content,
        "text_files_read_for_preview_extensions": sorted(TEXT_EXTENSIONS),
        "table_files_read_as_rows_extensions": sorted(TABLE_EXTENSIONS),
        "binary_content_extract_extensions": sorted(CONTENT_EXTRACT_EXTENSIONS),
        "binary_metadata_only_extensions_without_include_content": sorted(METADATA_ONLY_EXTENSIONS),
        "screenshots_are_metadata_only_no_ocr": True,
        "unsupported_extensions_are_skipped": True,
        "preview_char_limit": 1200,
        "extracted_text_char_limit": MAX_EXTRACTED_CHARS,
        "collector_writes_wiki_directly": False,
    }


def audit_counter(audit: Dict[str, Any], key: str) -> Counter[str]:
    value = audit.get(key)
    if isinstance(value, Counter):
        return value
    counter: Counter[str] = Counter(value or {})
    audit[key] = counter
    return counter


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


def parse_content_file(
    source_id: str,
    path: Path,
    *,
    collected_at: Optional[str],
    min_score: float,
    include_non_matches: bool,
) -> Optional[Dict[str, Any]]:
    extracted = extract_document_text(path)
    record: Dict[str, Any] = {
        "title": path.stem,
        "path": str(path),
        "extension": path.suffix.lower(),
        "byte_size": path.stat().st_size,
        "metadata_only": False,
        "content_read": extracted["status"] == "extracted",
        "content_extract": {
            "status": extracted["status"],
            "parser": extracted["parser"],
            "text_length": extracted["text_length"],
            "truncated": extracted["truncated"],
        },
    }
    if extracted["text"]:
        record["content_preview"] = extracted["text"][:1200]
        record["content"] = extracted["text"]
    if extracted["error"]:
        record["content_extract"]["error"] = extracted["error"]
    return candidate_to_event(
        source_id=source_id,
        record=record,
        source_label=str(path),
        raw_ref={
            "path": str(path),
            "parser": extracted["parser"],
            "byte_size": path.stat().st_size,
            "content_read": extracted["status"] == "extracted",
            "content_truncated": extracted["truncated"],
        },
        collected_at=collected_at,
        event_kind="file",
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


def extract_document_text(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    parser = suffix.lstrip(".")
    try:
        if suffix == ".pdf":
            text = extract_pdf_text(path)
            parser = "pdfplumber"
        elif suffix == ".docx":
            text = extract_docx_text(path)
            parser = "python-docx"
        elif suffix in {".xlsx", ".xlsm"}:
            text = extract_xlsx_text(path)
            parser = "openpyxl"
        else:
            text = ""
    except Exception as exc:  # pragma: no cover - dependency/runtime specific
        return {
            "status": "extract_failed",
            "parser": parser,
            "text": "",
            "text_length": 0,
            "truncated": False,
            "error": type(exc).__name__,
        }
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    truncated = len(normalized) > MAX_EXTRACTED_CHARS
    return {
        "status": "extracted" if normalized else "empty",
        "parser": parser,
        "text": normalized[:MAX_EXTRACTED_CHARS],
        "text_length": len(normalized),
        "truncated": truncated,
        "error": None,
    }


def extract_pdf_text(path: Path) -> str:
    import pdfplumber  # type: ignore

    parts: List[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages[:20]:
            parts.append(page.extract_text() or "")
            if sum(len(part) for part in parts) > MAX_EXTRACTED_CHARS:
                break
    return "\n".join(parts)


def extract_docx_text(path: Path) -> str:
    import docx  # type: ignore

    document = docx.Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables[:20]:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if values:
                parts.append(" | ".join(values))
    return "\n".join(parts)


def extract_xlsx_text(path: Path) -> str:
    import openpyxl  # type: ignore

    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    parts: List[str] = []
    try:
        for sheet in workbook.worksheets[:10]:
            parts.append(f"# {sheet.title}")
            for row in sheet.iter_rows(max_row=200, values_only=True):
                values = [str(value) for value in row if value not in (None, "")]
                if values:
                    parts.append(" | ".join(values))
                if sum(len(part) for part in parts) > MAX_EXTRACTED_CHARS:
                    break
    finally:
        workbook.close()
    return "\n".join(parts)


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
