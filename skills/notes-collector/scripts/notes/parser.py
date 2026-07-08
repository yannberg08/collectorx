import csv
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import List, Dict, Any, Iterable, Optional, Tuple


SUPPORTED_NOTE_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm", ".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".enex"}
SUPPORTED_EXPORT_EXTENSIONS = SUPPORTED_NOTE_EXTENSIONS | {".zip"}
TABLE_TITLE_FIELDS = ("title", "name", "标题", "名称", "Name")
TABLE_CONTENT_FIELDS = ("content", "text", "body", "正文", "内容", "备注", "notes", "note", "description", "Description", "记录", "复盘", "规则")
TABLE_TAG_FIELDS = ("tags", "tag", "标签", "分类")
TABLE_TIME_FIELDS = ("updated", "last_edited", "last_edited_time", "mtime", "created", "created_time", "更新时间", "创建时间", "日期", "时间")
TABLE_URL_FIELDS = ("url", "link", "链接")


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
    notes, _audit = parse_notes_export_with_audit(input_path, source_app=source_app, limit=limit)
    return notes


def parse_notes_export_with_audit(
    input_path: str,
    *,
    source_app: str = "auto",
    limit: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse notes exports and return a source audit suitable for manifest output."""
    path = Path(input_path).expanduser()
    notes: List[Dict[str, Any]] = []
    files = list(iter_authorized_files(path))
    audit: Dict[str, Any] = {
        "source_type": "authorized_notes_export",
        "input": str(path),
        "input_exists": path.exists(),
        "input_kind": input_kind(path),
        "input_count": 1,
        "resolved_input_file_count": 0,
        "supported_extensions": sorted(SUPPORTED_EXPORT_EXTENSIONS),
        "table_import_supported": True,
        "table_file_count": 0,
        "table_row_count": 0,
        "table_note_count": 0,
        "source_app": source_app,
        "limit": limit,
        "limit_reached": False,
        "extension_counts": {},
        "skipped_extension_counts": {},
        "skipped_reason_counts": {},
        "skipped_file_count": 0,
        "archive_count": 0,
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
        "parsed_note_count": 0,
        "path_results": [],
    }
    extension_counts: Counter[str] = Counter()
    skipped_extension_counts: Counter[str] = Counter()
    skipped_reason_counts: Counter[str] = Counter()
    skipped_archive_member_reason_counts: Counter[str] = Counter()
    if not path.exists():
        skipped_reason_counts["input_missing"] += 1
        audit["path_results"].append(path_result(path, status="missing", reason="input_missing"))
    elif not path.is_dir() and not path.is_file():
        skipped_reason_counts["unsupported_input_kind"] += 1
        audit["path_results"].append(path_result(path, status="skipped", reason="unsupported_input_kind"))

    for file_path in files:
        if limit is not None and len(notes) >= limit:
            audit["limit_reached"] = True
            break
        suffix = file_path.suffix.lower()
        extension_counts[suffix or "<none>"] += 1
        if suffix not in SUPPORTED_EXPORT_EXTENSIONS:
            audit["skipped_file_count"] += 1
            skipped_extension_counts[suffix or "<none>"] += 1
            skipped_reason_counts["unsupported_extension"] += 1
            audit["path_results"].append(path_result(file_path, status="skipped", reason="unsupported_extension"))
            continue
        audit["resolved_input_file_count"] += 1
        result = path_result(file_path, status="pending")
        try:
            if suffix == ".zip":
                parsed, archive_audit = parse_zip_notes_with_audit(
                    file_path,
                    source_app=source_app,
                    limit=remaining_limit(limit, notes),
                )
                merge_archive_audit(audit, archive_audit, skipped_archive_member_reason_counts)
                result.update(
                    {
                        "status": "parsed" if parsed else "no_notes_parsed",
                        "parser": "zip",
                        "parsed_note_count": len(parsed),
                        "archive_member_count": archive_audit["archive_member_count"],
                        "skipped_archive_member_count": archive_audit["skipped_archive_member_count"],
                    }
                )
            elif suffix in {".json", ".jsonl", ".ndjson"}:
                parsed = parse_json_notes(file_path)
                result.update({"status": "parsed" if parsed else "no_notes_parsed", "parser": "json", "parsed_note_count": len(parsed)})
            elif suffix == ".enex":
                parsed = parse_enex_notes(file_path)
                result.update({"status": "parsed" if parsed else "no_notes_parsed", "parser": "enex", "parsed_note_count": len(parsed)})
            elif suffix in {".csv", ".tsv"}:
                parsed = parse_table_notes(file_path)
                audit["table_file_count"] += 1
                audit["table_row_count"] += len(parsed)
                audit["table_note_count"] += len(parsed)
                result.update({"status": "parsed" if parsed else "no_notes_parsed", "parser": "table", "parsed_note_count": len(parsed), "table_row_count": len(parsed)})
            else:
                parsed = [parse_text_note(file_path)]
                result.update({"status": "parsed" if parsed else "no_notes_parsed", "parser": "text", "parsed_note_count": len(parsed)})
        except Exception:
            parsed = []
            audit["skipped_file_count"] += 1
            skipped_reason_counts["parse_error"] += 1
            skipped_extension_counts[suffix or "<none>"] += 1
            result.update({"status": "parse_error", "reason": "parse_error", "parsed_note_count": 0})
        audit["path_results"].append(result)
        for note in parsed:
            note["source_app"] = normalize_source_app(source_app, file_path, note)
            notes.append(note)
            if limit is not None and len(notes) >= limit:
                audit["limit_reached"] = True
                break

    audit["parsed_note_count"] = len(notes)
    audit["extension_counts"] = dict(sorted(extension_counts.items()))
    audit["skipped_extension_counts"] = dict(sorted(skipped_extension_counts.items()))
    audit["skipped_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_archive_member_reason_counts.items()))
    audit["unvisited_input_file_count_due_limit"] = max(0, len(files) - len(audit["path_results"]))
    return notes[:limit] if limit is not None else notes, audit


def input_kind(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


def iter_export_files(path: Path) -> Iterable[Path]:
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix.lower() in SUPPORTED_EXPORT_EXTENSIONS:
                yield child
    elif path.is_file() and path.suffix.lower() in SUPPORTED_EXPORT_EXTENSIONS:
        yield path


def iter_authorized_files(path: Path) -> Iterable[Path]:
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                yield child
    elif path.is_file():
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


def parse_table_notes(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_notes_text(text, suffix=path.suffix.lower(), default_title=path.stem, path_label=str(path))


def parse_table_notes_text(text: str, *, suffix: str, default_title: str, path_label: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    notes: List[Dict[str, Any]] = []
    rows = csv.DictReader(text.splitlines(), delimiter=delimiter)
    headers = [header for header in (rows.fieldnames or []) if header]
    for index, row in enumerate(rows, start=1):
        clean_row = {str(key): value for key, value in row.items() if key is not None and value not in (None, "")}
        if not clean_row:
            continue
        content = table_first(clean_row, TABLE_CONTENT_FIELDS)
        title = table_first(clean_row, TABLE_TITLE_FIELDS) or infer_title(f"{default_title}-{index}", content or table_row_to_content(clean_row, exclude=()))
        content = table_content_for_row(clean_row, content=content)
        note = {
            "title": title,
            "content": content,
            "path": f"{path_label}#{index}",
            "updated": table_first(clean_row, TABLE_TIME_FIELDS),
            "url": table_first(clean_row, TABLE_URL_FIELDS),
            "tags": split_table_tags(table_first(clean_row, TABLE_TAG_FIELDS)),
            "table_row": index,
            "table_columns": headers,
        }
        notes.append({key: value for key, value in note.items() if value not in (None, "", [], {})})
    return notes


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def table_content_for_row(row: Dict[str, Any], *, content: Optional[str]) -> str:
    metadata_fields = set(TABLE_TITLE_FIELDS + TABLE_CONTENT_FIELDS + TABLE_TAG_FIELDS + TABLE_TIME_FIELDS + TABLE_URL_FIELDS)
    metadata_keys = {normalize_key(field) for field in metadata_fields}
    extra = table_row_to_content(row, exclude=metadata_keys)
    parts = [part for part in (content, extra) if part]
    return "\n".join(parts)


def table_row_to_content(row: Dict[str, Any], *, exclude: Iterable[str]) -> str:
    exclude_set = set(exclude)
    parts = []
    for key, value in row.items():
        if normalize_key(key) in exclude_set or value in (None, ""):
            continue
        parts.append(f"{key}: {value}")
    return "\n".join(parts)


def table_first(row: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    normalized = {normalize_key(key): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
        value = normalized.get(normalize_key(key))
        if value not in (None, ""):
            return str(value)
    return None


def normalize_key(value: Any) -> str:
    return str(value).strip().lower().replace("_", "").replace("-", "").replace(" ", "")


def split_table_tags(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,，;；\s]+", value) if part.strip()]


def parse_zip_notes(path: Path, *, source_app: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    notes, _audit = parse_zip_notes_with_audit(path, source_app=source_app, limit=limit)
    return notes


def parse_zip_notes_with_audit(
    path: Path,
    *,
    source_app: str,
    limit: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    skipped_reason_counts: Counter[str] = Counter()
    audit: Dict[str, Any] = {
        "archive": str(path),
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "table_member_count": 0,
        "table_row_count": 0,
        "table_note_count": 0,
        "limit_reached": False,
        "member_results": [],
    }
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.infolist(), key=lambda item: normalize_zip_member_name(item.filename))
        for member in members:
            audit["archive_member_count"] += 1
            member_name = normalize_zip_member_name(member.filename)
            skip_reason = zip_member_skip_reason(member)
            if skip_reason:
                audit["skipped_archive_member_count"] += 1
                skipped_reason_counts[skip_reason] += 1
                audit["member_results"].append({"member": member_name, "status": "skipped", "reason": skip_reason})
                continue
            suffix = Path(member_name).suffix.lower()
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            path_label = f"{path}::{member_name}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_notes_text(
                        text,
                        suffix=suffix,
                        default_title=Path(member_name).stem,
                        path_label=path_label,
                    )
                elif suffix == ".enex":
                    parsed = parse_enex_notes_text(text, path_label=path_label)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_notes_text(
                        text,
                        suffix=suffix,
                        default_title=Path(member_name).stem,
                        path_label=path_label,
                    )
                    audit["table_member_count"] += 1
                    audit["table_row_count"] += len(parsed)
                    audit["table_note_count"] += len(parsed)
                else:
                    parsed = [
                        parse_text_note_text(
                            text,
                            suffix=suffix,
                            default_title=Path(member_name).stem,
                            path_label=path_label,
                            mtime=zip_member_mtime(member),
                        )
                    ]
            except Exception:
                parsed = []
                audit["skipped_archive_member_count"] += 1
                skipped_reason_counts["parse_error"] += 1
                audit["member_results"].append({"member": member_name, "status": "parse_error", "reason": "parse_error"})
                continue
            audit["member_results"].append({"member": member_name, "status": "parsed" if parsed else "no_notes_parsed", "parsed_note_count": len(parsed)})
            for note in parsed:
                note.setdefault("source_archive", str(path))
                note.setdefault("archive_member", member_name)
                note["source_app"] = normalize_source_app(source_app, Path(path.name) / member_name, note)
                notes.append(note)
                audit["archive_member_event_count"] += 1
                if limit is not None and len(notes) >= limit:
                    audit["limit_reached"] = True
                    audit["unvisited_archive_member_count_due_limit"] = max(0, len(members) - audit["archive_member_count"])
                    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
                    return notes[:limit], audit
    audit["unvisited_archive_member_count_due_limit"] = 0
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    return notes, audit


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    return zip_member_skip_reason(member) is not None


def zip_member_skip_reason(member: zipfile.ZipInfo) -> Optional[str]:
    member_name = normalize_zip_member_name(member.filename)
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(member.filename)
    if member.is_dir():
        return "directory"
    if member_path.is_absolute() or windows_path.drive or ".." in member_path.parts:
        return "unsafe_path"
    if Path(member_name).suffix.lower() not in SUPPORTED_NOTE_EXTENSIONS:
        return "unsupported_extension"
    return None


def path_result(path: Path, *, status: str, reason: Optional[str] = None) -> Dict[str, Any]:
    result = {
        "path": str(path),
        "extension": path.suffix.lower() or "<none>",
        "status": status,
    }
    if reason:
        result["reason"] = reason
    return result


def merge_archive_audit(audit: Dict[str, Any], archive_audit: Dict[str, Any], skipped_reason_counts: Counter[str]) -> None:
    audit["archive_count"] += 1
    audit["archive_member_count"] += int(archive_audit.get("archive_member_count") or 0)
    audit["archive_member_event_count"] += int(archive_audit.get("archive_member_event_count") or 0)
    audit["skipped_archive_member_count"] += int(archive_audit.get("skipped_archive_member_count") or 0)
    if archive_audit.get("limit_reached"):
        audit["limit_reached"] = True
    audit["table_file_count"] += int(archive_audit.get("table_member_count") or 0)
    audit["table_row_count"] += int(archive_audit.get("table_row_count") or 0)
    audit["table_note_count"] += int(archive_audit.get("table_note_count") or 0)
    for reason, count in (archive_audit.get("skipped_archive_member_reason_counts") or {}).items():
        skipped_reason_counts[str(reason)] += int(count)


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


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
