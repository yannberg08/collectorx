"""Parse local user-authorized meeting artifact files."""

from __future__ import annotations

import csv
import json
import re
import zipfile
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional


SUPPORTED_RECORD_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".html",
    ".htm",
    ".json",
    ".jsonl",
    ".ndjson",
    ".csv",
    ".tsv",
    ".vtt",
    ".srt",
}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    paths, _audit = resolve_input_paths(inputs)
    yield from paths


def resolve_input_paths(inputs: Iterable[str]) -> tuple[List[Path], Dict[str, Any]]:
    input_list = list(inputs)
    paths: List[Path] = []
    audit = {
        "requested_inputs": input_list,
        "input_missing_count": 0,
        "skipped_file_count": 0,
        "skipped_reason_counts": {},
        "skipped_extension_counts": {},
        "input_results": [],
        "skipped_file_samples": [],
    }
    for raw in input_list:
        path = Path(raw).expanduser()
        result = {
            "input": raw,
            "path": str(path),
            "status": "pending",
            "resolved_file_count": 0,
            "skipped_file_count": 0,
        }
        audit["input_results"].append(result)
        if not path.exists():
            result["status"] = "missing"
            audit["input_missing_count"] += 1
            continue
        if path.is_dir():
            result["status"] = "directory"
            for child in sorted(path.rglob("*")):
                if not child.is_file():
                    continue
                if child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    paths.append(child)
                    result["resolved_file_count"] += 1
                else:
                    record_skipped_file(audit, result, child, "unsupported_extension")
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            result["status"] = "file"
            paths.append(path)
            result["resolved_file_count"] = 1
            continue
        result["status"] = "unsupported_file"
        record_skipped_file(audit, result, path, "unsupported_extension")
    finalize_input_audit(audit)
    return paths, audit


def record_skipped_file(audit: Dict[str, Any], input_result: Dict[str, Any], path: Path, reason: str) -> None:
    suffix = path.suffix.lower() or "<none>"
    audit["skipped_file_count"] += 1
    input_result["skipped_file_count"] += 1
    increment_counter(audit, "skipped_reason_counts", reason)
    increment_counter(audit, "skipped_extension_counts", suffix)
    if len(audit["skipped_file_samples"]) < 50:
        audit["skipped_file_samples"].append({"path": str(path), "extension": suffix, "reason": reason})


def finalize_input_audit(audit: Dict[str, Any]) -> None:
    audit["skipped_reason_counts"] = dict(sorted((audit.get("skipped_reason_counts") or {}).items()))
    audit["skipped_extension_counts"] = dict(sorted((audit.get("skipped_extension_counts") or {}).items()))


def new_collection_audit(
    inputs: Iterable[str],
    paths: List[Path],
    *,
    limit: Optional[int] = None,
    input_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    input_list = list(inputs)
    audit = {
        "source_type": "authorized_local_meeting_artifacts",
        "input_count": len(input_list),
        "resolved_input_file_count": len(paths),
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "skipped_archive_member_reason_counts": {},
        "parsed_record_count": 0,
        "emitted_event_count": 0,
        "limit": limit,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "real_account_adapter_used": False,
        "path_results": [],
    }
    audit.update(input_audit or {})
    audit["input_count"] = len(input_list)
    audit["resolved_input_file_count"] = len(paths)
    return audit


def parse_path(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if audit is not None:
        increment_counter(audit, "extension_counts", suffix or "<none>")
    if suffix == ".zip":
        return parse_zip(path, audit=audit)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".vtt", ".srt"}:
        return [parse_subtitle(path)]
    if suffix in {".html", ".htm"}:
        return [parse_html(path)]
    return [parse_text(path)]


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    return parse_json_text(text, suffix=path.suffix.lower(), path_label=str(path))


def parse_json_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        rows = extract_records(loaded)
    records = [row if isinstance(row, dict) else {"value": row} for row in rows]
    for record in records:
        record.setdefault("path", path_label)
    return records


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    for key in ("meetings", "minutes", "transcripts", "records", "items", "data"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_records(value)
            if not (len(nested) == 1 and nested[0] == value):
                return nested
    return [loaded]


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_text(text, suffix=path.suffix.lower(), path_label=str(path))


def parse_table_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    records = [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    for record in records:
        record.setdefault("path", path_label)
    return records


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_text_text(text, path_label=str(path), default_title=path.stem)


def parse_text_text(text: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    return {
        "artifact_type": "minutes",
        "title": infer_title(default_title, text),
        "text": text,
        "participants": extract_participants(text),
        "meeting_url": first_url(text),
        "path": path_label,
    }


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_html_text(html, path_label=str(path), default_title=path.stem)


def parse_html_text(html: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    text = html_to_text(html)
    return {
        "artifact_type": "minutes",
        "title": title_tag(html) or infer_title(default_title, text),
        "text": text,
        "participants": extract_participants(text),
        "meeting_url": first_url(html),
        "path": path_label,
    }


def parse_subtitle(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_subtitle_text(text, path_label=str(path), default_title=path.stem)


def parse_subtitle_text(text: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    cleaned = subtitle_text(text)
    return {
        "artifact_type": "transcript",
        "title": default_title,
        "transcript": cleaned,
        "path": path_label,
    }


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
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
            path_label = f"{path}::{member_name}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_text(text, suffix=suffix, path_label=path_label)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(text, suffix=suffix, path_label=path_label)
                elif suffix in {".vtt", ".srt"}:
                    parsed = [parse_subtitle_text(text, path_label=path_label, default_title=Path(member_name).stem)]
                elif suffix in {".html", ".htm"}:
                    parsed = [parse_html_text(text, path_label=path_label, default_title=Path(member_name).stem)]
                else:
                    parsed = [parse_text_text(text, path_label=path_label, default_title=Path(member_name).stem)]
            except Exception:
                parsed = []
            for record in parsed:
                if isinstance(record, dict):
                    record[SOURCE_ARCHIVE_KEY] = str(path)
                    record[SOURCE_MEMBER_KEY] = member_name
            records.extend(parsed)
    return records


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


def increment_counter(audit: Dict[str, Any], key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_collection_audit(audit: Dict[str, Any]) -> Dict[str, Any]:
    for key in (
        "extension_counts",
        "skipped_reason_counts",
        "skipped_extension_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "skipped_archive_member_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))
    return audit


def subtitle_text(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT":
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines)


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    lines = [re.sub(r"[ \t]+", " ", unescape(line)).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def title_tag(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return html_to_text(match.group(1))[:120] if match else ""


def first_url(text: str) -> str:
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return match.group(0) if match else ""


def extract_participants(text: str) -> List[str]:
    for line in text.splitlines()[:40]:
        if any(key in line for key in ("参会人", "参与人", "Attendees", "Participants")):
            _, _, tail = line.partition(":")
            if not tail:
                _, _, tail = line.partition("：")
            return [item.strip() for item in re.split(r"[,，、;；]", tail) if item.strip()]
    return []


def infer_title(default_title: str, text: str) -> str:
    for line in text.splitlines()[:20]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return default_title
