"""Metadata-only local filesystem scanner."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set


COLLECTOR = "filesystem"
CN_TZ = timezone(timedelta(hours=8))
DEFAULT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "md",
    "markdown",
    "txt",
    "rtf",
    "pages",
    "xlsx",
    "xls",
    "csv",
    "tsv",
    "numbers",
    "pptx",
    "ppt",
    "key",
}
DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "target",
    "DerivedData",
    "Library",
    "Caches",
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def default_roots(home: Optional[Path] = None) -> List[Path]:
    home = home or Path.home()
    roots = [home / "Documents", home / "Desktop", home / "Downloads"]
    system = platform.system().lower()
    if system == "darwin":
        roots.append(home / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    elif system == "windows":
        roots.extend([home / "OneDrive", home / "Documents" / "OneDrive"])
    return [root for root in roots if root.exists()]


def scan_files(
    roots: Iterable[Path],
    *,
    extensions: Optional[Set[str]] = None,
    ignore_dirs: Optional[Set[str]] = None,
    max_size_mb: int = 50,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    allowed = {ext.lower().lstrip(".") for ext in (extensions or DEFAULT_EXTENSIONS)}
    ignored = set(DEFAULT_IGNORE_DIRS)
    if ignore_dirs:
        ignored.update(ignore_dirs)
    max_bytes = max_size_mb * 1024 * 1024 if max_size_mb > 0 else 50 * 1024 * 1024
    collected_at = now_iso()
    for path in iter_files(roots, ignored):
        if limit is not None and len(events) >= limit:
            break
        ext = path.suffix.lower().lstrip(".")
        if ext not in allowed:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size > max_bytes:
            continue
        events.append(file_event(path, stat, collected_at=collected_at))
    return events


def iter_files(roots: Iterable[Path], ignored: Set[str]) -> Iterator[Path]:
    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        if root.is_file():
            yield root
            continue
        for current, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if name not in ignored and not name.startswith(".")]
            current_path = Path(current)
            for name in sorted(files):
                if name.startswith("."):
                    continue
                yield current_path / name


def file_event(path: Path, stat: os.stat_result, *, collected_at: str) -> Dict[str, Any]:
    mtime = datetime.fromtimestamp(stat.st_mtime, CN_TZ).isoformat(timespec="seconds")
    path_str = str(path)
    data = {
        "path": path_str,
        "name": path.name,
        "extension": path.suffix.lower().lstrip("."),
        "size_bytes": stat.st_size,
        "mtime": mtime,
        "path_sha256": hashlib.sha256(path_str.encode("utf-8")).hexdigest(),
        "metadata_only": True,
        "content_read": False,
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_str, stat.st_size, int(stat.st_mtime)),
        "collector": COLLECTOR,
        "source": "本地文件元数据",
        "owner_scope": "personal",
        "kind": "file",
        "time": mtime,
        "collected_at": collected_at,
        "data": data,
        "raw_ref": {
            "path": path_str,
            "metadata_only": True,
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["work_confidential"],
        },
        "wiki_targets": [
            "internal.knowledge.files",
            "external.investor.research_documents",
        ],
    }


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
