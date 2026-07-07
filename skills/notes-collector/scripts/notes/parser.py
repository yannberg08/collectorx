import json
import re
import xml.etree.ElementTree as ET
import zipfile
from html import unescape
from pathlib import Path
from typing import List, Dict, Any, Iterable, Optional


SUPPORTED_NOTE_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm", ".json", ".jsonl", ".ndjson", ".enex"}
SUPPORTED_EXPORT_EXTENSIONS = SUPPORTED_NOTE_EXTENSIONS | {".zip"}


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
            if suffix == ".zip":
                parsed = parse_zip_notes(file_path, source_app=source_app, limit=remaining_limit(limit, notes))
            elif suffix in {".json", ".jsonl", ".ndjson"}:
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


def remaining_limit(limit: Optional[int], notes: List[Dict[str, Any]]) -> Optional[int]:
    if limit is None:
        return None
    return max(limit - len(notes), 0)


def parse_json_notes(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    return parse_json_notes_text(text, suffix=path.suffix.lower(), default_title=path.stem, path_label=path.name)


def parse_json_notes_text(text: str, *, suffix: str, default_title: str, path_label: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_note_records(json.loads(text))
    notes = [row if isinstance(row, dict) else {"content": str(row)} for row in rows]
    for index, note in enumerate(notes, start=1):
        note.setdefault("path", f"{path_label}#{index}")
        note.setdefault("title", first(note, ["title", "name", "标题"]) or default_title)
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
    return parse_text_note_text(
        text,
        suffix=path.suffix.lower(),
        default_title=path.stem,
        path_label=str(path),
        mtime=path.stat().st_mtime,
    )


def parse_text_note_text(
    text: str,
    *,
    suffix: str,
    default_title: str,
    path_label: str,
    mtime: Optional[float] = None,
) -> Dict[str, Any]:
    content = html_to_text(text) if suffix in {".html", ".htm"} else text
    return {
        "title": infer_title(default_title, content),
        "content": content,
        "path": path_label,
        "mtime": mtime,
    }


def parse_enex_notes(path: Path) -> List[Dict[str, Any]]:
    return parse_enex_notes_text(path.read_text(encoding="utf-8", errors="replace"), path_label=path.name)


def parse_enex_notes_text(text: str, *, path_label: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(text)
    notes: List[Dict[str, Any]] = []
    for index, node in enumerate(root.findall(".//note"), start=1):
        title = text_of(node, "title") or f"{Path(path_label).stem}-{index}"
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
                "path": f"{path_label}#{index}",
            }
        )
    return notes


def parse_zip_notes(path: Path, *, source_app: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            if should_skip_zip_member(member):
                continue
            suffix = Path(member.filename).suffix.lower()
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            path_label = f"{path.name}::{member.filename}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_notes_text(
                        text,
                        suffix=suffix,
                        default_title=Path(member.filename).stem,
                        path_label=path_label,
                    )
                elif suffix == ".enex":
                    parsed = parse_enex_notes_text(text, path_label=path_label)
                else:
                    parsed = [
                        parse_text_note_text(
                            text,
                            suffix=suffix,
                            default_title=Path(member.filename).stem,
                            path_label=path_label,
                            mtime=zip_member_mtime(member),
                        )
                    ]
            except Exception:
                parsed = []
            for note in parsed:
                note.setdefault("source_archive", str(path))
                note.setdefault("archive_member", member.filename)
                note["source_app"] = normalize_source_app(source_app, Path(path.name) / member.filename, note)
                notes.append(note)
                if limit is not None and len(notes) >= limit:
                    return notes[:limit]
    return notes


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    member_path = Path(member.filename)
    if member.is_dir():
        return True
    if member_path.is_absolute() or ".." in member_path.parts:
        return True
    return member_path.suffix.lower() not in SUPPORTED_NOTE_EXTENSIONS


def zip_member_mtime(member: zipfile.ZipInfo) -> float:
    try:
        return datetime_from_zip(member).timestamp()
    except ValueError:
        return 0.0


def datetime_from_zip(member: zipfile.ZipInfo):
    from datetime import datetime

    return datetime(*member.date_time)


def normalize_source_app(source_app: str, path: Path, note: Dict[str, Any]) -> str:
    if source_app != "auto":
        return source_app
    explicit = first(note, ["source_app", "source", "app", "平台"])
    probe = f"{explicit or ''} {path}".lower()
    if "obsidian" in probe:
        return "obsidian"
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


def infer_title(default_title: str, content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return default_title


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
