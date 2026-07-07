import json
import re
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from typing import List, Dict, Any, Iterable, Optional


SUPPORTED_EXPORT_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm", ".json", ".jsonl", ".ndjson", ".enex"}


def parse_obsidian_vault(vault_path: str, limit: int = None) -> List[Dict[str, Any]]:
    """解析Obsidian笔记"""
    vault = Path(vault_path)
    if not vault.exists():
        return []
    
    notes = []
    md_files = list(vault.rglob("*.md"))
    
    if limit:
        md_files = md_files[:limit]
    
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            note = {
                "source": "obsidian",
                "path": str(md_file.relative_to(vault)),
                "name": md_file.stem,
                "content": content[:5000],
                "mtime": md_file.stat().st_mtime
            }
            notes.append(note)
        except Exception:
            pass
    
    return notes


def parse_notes_export(input_path: str, *, source_app: str = "auto", limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Parse user-authorized notes exports from common local formats."""
    path = Path(input_path).expanduser()
    notes: List[Dict[str, Any]] = []
    for file_path in iter_export_files(path):
        suffix = file_path.suffix.lower()
        try:
            if suffix in {".json", ".jsonl", ".ndjson"}:
                parsed = parse_json_notes(file_path)
            elif suffix == ".enex":
                parsed = parse_enex_notes(file_path)
            else:
                parsed = [parse_text_note(file_path)]
        except Exception:
            parsed = []
        for note in parsed:
            note["source_app"] = normalize_source_app(source_app, file_path, note)
            notes.append(note)
            if limit is not None and len(notes) >= limit:
                return notes[:limit]
    return notes


def iter_export_files(path: Path) -> Iterable[Path]:
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix.lower() in SUPPORTED_EXPORT_EXTENSIONS:
                yield child
    elif path.is_file() and path.suffix.lower() in SUPPORTED_EXPORT_EXTENSIONS:
        yield path


def parse_json_notes(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_note_records(json.loads(text))
    notes = [row if isinstance(row, dict) else {"content": str(row)} for row in rows]
    for index, note in enumerate(notes, start=1):
        note.setdefault("path", f"{path.name}#{index}")
        note.setdefault("title", first(note, ["title", "name", "标题"]) or path.stem)
    return notes


def extract_note_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"content": loaded}]
    for key in ("notes", "items", "records", "pages", "data", "list"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_note_records(value)
            if not (len(nested) == 1 and nested[0] == value):
                return nested
    return [loaded]


def parse_text_note(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    content = html_to_text(text) if path.suffix.lower() in {".html", ".htm"} else text
    return {
        "title": infer_title(path, content),
        "content": content,
        "path": str(path),
        "mtime": path.stat().st_mtime,
    }


def parse_enex_notes(path: Path) -> List[Dict[str, Any]]:
    root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    notes: List[Dict[str, Any]] = []
    for index, node in enumerate(root.findall(".//note"), start=1):
        title = text_of(node, "title") or f"{path.stem}-{index}"
        content = html_to_text(text_of(node, "content") or "")
        tags = [tag.text or "" for tag in node.findall("tag") if tag.text]
        notes.append(
            {
                "source_app": "evernote",
                "title": title,
                "content": content,
                "created": text_of(node, "created"),
                "updated": text_of(node, "updated"),
                "tags": tags,
                "path": f"{path.name}#{index}",
            }
        )
    return notes


def normalize_source_app(source_app: str, path: Path, note: Dict[str, Any]) -> str:
    if source_app != "auto":
        return source_app
    explicit = first(note, ["source_app", "source", "app", "平台"])
    probe = f"{explicit or ''} {path}".lower()
    if "youdao" in probe or "有道" in probe:
        return "youdao"
    if "evernote" in probe or "yinxiang" in probe or "印象" in probe or path.suffix.lower() == ".enex":
        return "evernote"
    if "notion" in probe:
        return "notion"
    if path.suffix.lower() in {".md", ".markdown"}:
        return "markdown"
    return "notes-export"


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def text_of(node: ET.Element, name: str) -> Optional[str]:
    child = node.find(name)
    if child is None or child.text is None:
        return None
    return child.text


def infer_title(path: Path, content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return path.stem


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def parse_notion_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """解析Notion页面"""
    return {
        "source": "notion",
        "id": page["id"],
        "title": _extract_notion_title(page),
        "url": page.get("url", ""),
        "created": page.get("created_time", ""),
        "last_edited": page.get("last_edited_time", "")
    }


def _extract_notion_title(page):
    props = page.get("properties", {})
    for prop_name, prop_value in props.items():
        if prop_value.get("type") == "title":
            title_parts = prop_value.get("title", [])
            return "".join(part.get("plain_text", "") for part in title_parts)
    return page.get("id", "Untitled")
