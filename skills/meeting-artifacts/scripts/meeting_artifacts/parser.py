"""Parse local user-authorized meeting artifact files."""

from __future__ import annotations

import csv
import json
import re
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List


SUPPORTED_EXTENSIONS = {
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
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        loaded = json.loads(text)
        rows = extract_records(loaded)
    return [row if isinstance(row, dict) else {"value": row} for row in rows]


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
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "artifact_type": "minutes",
        "title": infer_title(path, text),
        "text": text,
        "participants": extract_participants(text),
        "meeting_url": first_url(text),
        "path": str(path),
    }


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "artifact_type": "minutes",
        "title": title_tag(html) or infer_title(path, text),
        "text": text,
        "participants": extract_participants(text),
        "meeting_url": first_url(html),
        "path": str(path),
    }


def parse_subtitle(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    cleaned = subtitle_text(text)
    return {
        "artifact_type": "transcript",
        "title": path.stem,
        "transcript": cleaned,
        "path": str(path),
    }


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


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:20]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return path.stem
