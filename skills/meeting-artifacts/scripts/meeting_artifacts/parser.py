"""Parse local user-authorized meeting artifact files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List


SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".json", ".jsonl", ".ndjson", ".vtt", ".srt"}


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
    if suffix in {".vtt", ".srt"}:
        return [parse_subtitle(path)]
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
    return [loaded]


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "artifact_type": "minutes",
        "title": infer_title(path, text),
        "text": text,
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


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:20]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return path.stem
