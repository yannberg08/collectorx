"""Metadata-only local filesystem scanner."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple


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
FILESYSTEM_SCOPE_POLICY_KEYS = (
    "allow_extensions",
    "deny_extensions",
    "allow_paths",
    "deny_paths",
    "allow_file_names",
    "deny_file_names",
    "allow_directories",
    "deny_directories",
    "allow_keywords",
    "deny_keywords",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def default_roots(home: Optional[Path] = None, *, system_name: Optional[str] = None) -> List[Path]:
    home = home or Path.home()
    roots = [home / "Documents", home / "Desktop", home / "Downloads"]
    system = (system_name or platform.system()).lower()
    if system == "darwin":
        roots.append(home / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    elif system == "windows":
        roots.extend([home / "OneDrive", home / "Documents" / "OneDrive"])
    return [root for root in roots if root.exists()]


def platform_default_root_plan(home: Optional[Path] = None) -> Dict[str, List[str]]:
    home = home or Path.home()
    return {
        "macos": [str(path) for path in default_roots(home, system_name="Darwin")],
        "windows": [str(path) for path in default_roots(home, system_name="Windows")],
        "linux": [str(path) for path in default_roots(home, system_name="Linux")],
    }


def scan_files(
    roots: Iterable[Path],
    *,
    extensions: Optional[Set[str]] = None,
    ignore_dirs: Optional[Set[str]] = None,
    allow_extensions: Optional[Sequence[str]] = None,
    deny_extensions: Optional[Sequence[str]] = None,
    allow_paths: Optional[Sequence[str]] = None,
    deny_paths: Optional[Sequence[str]] = None,
    allow_file_names: Optional[Sequence[str]] = None,
    deny_file_names: Optional[Sequence[str]] = None,
    allow_directories: Optional[Sequence[str]] = None,
    deny_directories: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
    max_size_mb: int = 50,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    events, _audit = scan_files_with_audit(
        roots,
        extensions=extensions,
        ignore_dirs=ignore_dirs,
        allow_extensions=allow_extensions,
        deny_extensions=deny_extensions,
        allow_paths=allow_paths,
        deny_paths=deny_paths,
        allow_file_names=allow_file_names,
        deny_file_names=deny_file_names,
        allow_directories=allow_directories,
        deny_directories=deny_directories,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
        max_size_mb=max_size_mb,
        limit=limit,
    )
    return events


def scan_files_with_audit(
    roots: Iterable[Path],
    *,
    extensions: Optional[Set[str]] = None,
    ignore_dirs: Optional[Set[str]] = None,
    allow_extensions: Optional[Sequence[str]] = None,
    deny_extensions: Optional[Sequence[str]] = None,
    allow_paths: Optional[Sequence[str]] = None,
    deny_paths: Optional[Sequence[str]] = None,
    allow_file_names: Optional[Sequence[str]] = None,
    deny_file_names: Optional[Sequence[str]] = None,
    allow_directories: Optional[Sequence[str]] = None,
    deny_directories: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
    max_size_mb: int = 50,
    limit: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    legacy_allow_extensions = sorted({ext.lower().lstrip(".") for ext in (extensions or set()) if ext})
    scope_policy = build_filesystem_scope_policy(
        allow_extensions=[*legacy_allow_extensions, *list(allow_extensions or [])],
        deny_extensions=deny_extensions,
        allow_paths=allow_paths,
        deny_paths=deny_paths,
        allow_file_names=allow_file_names,
        deny_file_names=deny_file_names,
        allow_directories=allow_directories,
        deny_directories=deny_directories,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    allowed = set(DEFAULT_EXTENSIONS)
    allowed.update(scope_policy.get("allow_extensions", []))
    allowed.update(scope_policy.get("deny_extensions", []))
    ignored = set(DEFAULT_IGNORE_DIRS)
    if ignore_dirs:
        ignored.update(ignore_dirs)
    max_bytes = max_size_mb * 1024 * 1024 if max_size_mb > 0 else 50 * 1024 * 1024
    collected_at = now_iso()

    requested_roots = [Path(root).expanduser() for root in roots]
    extension_counts: Counter[str] = Counter()
    emitted_extension_counts: Counter[str] = Counter()
    skipped_extension_counts: Counter[str] = Counter()
    skipped_reason_counts: Counter[str] = Counter()

    audit: Dict[str, Any] = {
        "source_type": "authorized_local_filesystem_metadata",
        "requested_roots": [str(root) for root in requested_roots],
        "root_count": len(requested_roots),
        "resolved_root_count": 0,
        "missing_root_count": 0,
        "allowed_extensions": sorted(allowed),
        "ignored_dirs": sorted(ignored),
        "max_size_mb": max_size_mb if max_size_mb > 0 else 50,
        "max_size_bytes": max_bytes,
        "limit": limit,
        "metadata_only": True,
        "content_read": False,
        "platform_system": platform.system(),
        "scanned_file_count": 0,
        "emitted_event_count": 0,
        "skipped_file_count": 0,
        "skipped_directory_count": 0,
        "limit_reached": False,
        "root_results": [],
        "filesystem_scope_policy": scope_policy,
    }

    def finish_root(result: Dict[str, Any]) -> None:
        if result["status"] == "pending":
            if result["emitted_event_count"]:
                result["status"] = "events_collected"
            elif result["scanned_file_count"] or result["skipped_directory_count"]:
                result["status"] = "no_matching_files"
            else:
                result["status"] = "empty_or_no_readable_files"
        audit["root_results"].append(result)

    def root_result(root: Path, *, exists: bool, root_type: str, status: str = "pending") -> Dict[str, Any]:
        return {
            "path": str(root),
            "exists": exists,
            "type": root_type,
            "status": status,
            "scanned_file_count": 0,
            "emitted_event_count": 0,
            "skipped_file_count": 0,
            "skipped_directory_count": 0,
        }

    def record_skipped_file(result: Dict[str, Any], reason: str, ext: str) -> None:
        audit["skipped_file_count"] += 1
        result["skipped_file_count"] += 1
        skipped_reason_counts[reason] += 1
        skipped_extension_counts[ext] += 1

    def record_scope_filtered_file(result: Dict[str, Any], reason: str, ext: str) -> None:
        record_skipped_file(result, reason, ext)
        policy = audit["filesystem_scope_policy"]
        policy["filtered_file_count"] = int(policy.get("filtered_file_count") or 0) + 1
        counts = policy.get("filter_reason_counts")
        if not isinstance(counts, Counter):
            counts = Counter(counts or {})
            policy["filter_reason_counts"] = counts
        counts[reason] += 1

    def record_skipped_directory(result: Dict[str, Any], reason: str) -> None:
        audit["skipped_directory_count"] += 1
        result["skipped_directory_count"] += 1
        skipped_reason_counts[reason] += 1

    def record_file(path: Path, result: Dict[str, Any], *, explicit_root: bool = False) -> bool:
        if limit is not None and len(events) >= limit:
            audit["limit_reached"] = True
            return False
        ext = path.suffix.lower().lstrip(".") or "<none>"
        audit["scanned_file_count"] += 1
        result["scanned_file_count"] += 1
        extension_counts[ext] += 1
        if path.name.startswith(".") and not explicit_root:
            record_skipped_file(result, "hidden_file", ext)
            return True
        if ext not in allowed:
            record_skipped_file(result, "unsupported_extension", ext)
            return True
        try:
            stat = path.stat()
        except OSError:
            record_skipped_file(result, "stat_error", ext)
            return True
        if stat.st_size > max_bytes:
            record_skipped_file(result, "over_max_size", ext)
            return True
        policy = audit["filesystem_scope_policy"]
        policy["candidate_file_count"] = int(policy.get("candidate_file_count") or 0) + 1
        policy_allowed, policy_match = filesystem_scope_policy_match(path, ext=ext, source_policy=policy)
        if not policy_allowed:
            record_scope_filtered_file(result, str(policy_match.get("reason") or "scope_policy_filtered"), ext)
            return True
        event = file_event(path, stat, collected_at=collected_at)
        if policy.get("enabled"):
            event["data"]["filesystem_scope_policy"] = policy_match
        events.append(event)
        result["emitted_event_count"] += 1
        emitted_extension_counts[ext] += 1
        return True

    stop = False
    for root in requested_roots:
        if stop:
            break
        if not root.exists():
            audit["missing_root_count"] += 1
            skipped_reason_counts["root_missing"] += 1
            finish_root(root_result(root, exists=False, root_type="missing", status="missing"))
            continue
        if root.is_file():
            audit["resolved_root_count"] += 1
            result = root_result(root, exists=True, root_type="file")
            stop = not record_file(root, result, explicit_root=True)
            finish_root(result)
            continue
        if not root.is_dir():
            skipped_reason_counts["unsupported_root_type"] += 1
            finish_root(root_result(root, exists=True, root_type="other", status="unsupported_root_type"))
            continue

        audit["resolved_root_count"] += 1
        result = root_result(root, exists=True, root_type="directory")
        for current, dirs, files in os.walk(root):
            kept_dirs = []
            for name in sorted(dirs):
                if name in ignored:
                    record_skipped_directory(result, "ignored_directory")
                    continue
                if name.startswith("."):
                    record_skipped_directory(result, "hidden_directory")
                    continue
                kept_dirs.append(name)
            dirs[:] = kept_dirs
            current_path = Path(current)
            for name in sorted(files):
                if not record_file(current_path / name, result):
                    stop = True
                    break
            if stop:
                break
        finish_root(result)

    audit["emitted_event_count"] = len(events)
    audit["extension_counts"] = dict(sorted(extension_counts.items()))
    audit["emitted_extension_counts"] = dict(sorted(emitted_extension_counts.items()))
    audit["skipped_extension_counts"] = dict(sorted(skipped_extension_counts.items()))
    audit["skipped_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    policy = audit["filesystem_scope_policy"]
    if isinstance(policy.get("filter_reason_counts"), Counter):
        policy["filter_reason_counts"] = dict(sorted(policy["filter_reason_counts"].items()))
    policy["retained_event_count"] = len(events)
    policy["filtered_all"] = bool(policy.get("candidate_file_count")) and int(policy.get("filtered_file_count") or 0) >= int(
        policy.get("candidate_file_count") or 0
    )
    audit["filesystem_scope_policy_filtered_all"] = bool(policy.get("filtered_all"))
    audit["unvisited_root_count_due_limit"] = max(
        0,
        audit["root_count"] - len(audit["root_results"]),
    )
    return events, audit


def split_patterns(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return stable_unique(out)


def stable_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def normalize_extension_terms(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for value in split_patterns(values):
        normalized = value.lower().strip().lstrip(".")
        if normalized:
            out.append(normalized)
    return stable_unique(out)


def build_filesystem_scope_policy(
    *,
    allow_extensions: Optional[Sequence[str]],
    deny_extensions: Optional[Sequence[str]],
    allow_paths: Optional[Sequence[str]],
    deny_paths: Optional[Sequence[str]],
    allow_file_names: Optional[Sequence[str]],
    deny_file_names: Optional[Sequence[str]],
    allow_directories: Optional[Sequence[str]],
    deny_directories: Optional[Sequence[str]],
    allow_keywords: Optional[Sequence[str]],
    deny_keywords: Optional[Sequence[str]],
) -> Dict[str, Any]:
    policy = {
        "enabled": False,
        "allow_extensions": normalize_extension_terms(allow_extensions),
        "deny_extensions": normalize_extension_terms(deny_extensions),
        "allow_paths": split_patterns(allow_paths),
        "deny_paths": split_patterns(deny_paths),
        "allow_file_names": split_patterns(allow_file_names),
        "deny_file_names": split_patterns(deny_file_names),
        "allow_directories": split_patterns(allow_directories),
        "deny_directories": split_patterns(deny_directories),
        "allow_keywords": split_patterns(allow_keywords),
        "deny_keywords": split_patterns(deny_keywords),
        "candidate_file_count": 0,
        "retained_event_count": 0,
        "filtered_file_count": 0,
        "filter_reason_counts": {},
        "filtered_all": False,
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "metadata_only": True,
    }
    policy["enabled"] = any(policy.get(key) for key in FILESYSTEM_SCOPE_POLICY_KEYS)
    return policy


def filesystem_scope_policy_match(path: Path, *, ext: str, source_policy: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    if not source_policy.get("enabled"):
        return True, {"enabled": False}

    path_surface = str(path).lower()
    file_name_surface = path.name.lower()
    directory_surface = "\n".join(str(part).lower() for part in path.parent.parts)
    keyword_surface = "\n".join([path_surface, file_name_surface, ext.lower()])

    deny_extension = first_exact_hit(source_policy.get("deny_extensions", []), ext)
    if deny_extension:
        return False, {"enabled": True, "allowed": False, "reason": "deny_extension", "matched_pattern": deny_extension}
    allow_extensions = source_policy.get("allow_extensions", [])
    allow_extension = first_exact_hit(allow_extensions, ext)
    if allow_extensions and not allow_extension:
        return False, {"enabled": True, "allowed": False, "reason": "allow_extension_not_matched"}

    deny_path = first_pattern_hit(source_policy.get("deny_paths", []), path_surface)
    if deny_path:
        return False, {"enabled": True, "allowed": False, "reason": "deny_path", "matched_pattern": deny_path}
    allow_paths = source_policy.get("allow_paths", [])
    allow_path = first_pattern_hit(allow_paths, path_surface)
    if allow_paths and not allow_path:
        return False, {"enabled": True, "allowed": False, "reason": "allow_path_not_matched"}

    deny_file_name = first_pattern_hit(source_policy.get("deny_file_names", []), file_name_surface)
    if deny_file_name:
        return False, {"enabled": True, "allowed": False, "reason": "deny_file_name", "matched_pattern": deny_file_name}
    allow_file_names = source_policy.get("allow_file_names", [])
    allow_file_name = first_pattern_hit(allow_file_names, file_name_surface)
    if allow_file_names and not allow_file_name:
        return False, {"enabled": True, "allowed": False, "reason": "allow_file_name_not_matched"}

    deny_directory = first_pattern_hit(source_policy.get("deny_directories", []), directory_surface)
    if deny_directory:
        return False, {"enabled": True, "allowed": False, "reason": "deny_directory", "matched_pattern": deny_directory}
    allow_directories = source_policy.get("allow_directories", [])
    allow_directory = first_pattern_hit(allow_directories, directory_surface)
    if allow_directories and not allow_directory:
        return False, {"enabled": True, "allowed": False, "reason": "allow_directory_not_matched"}

    deny_keyword = first_pattern_hit(source_policy.get("deny_keywords", []), keyword_surface)
    if deny_keyword:
        return False, {"enabled": True, "allowed": False, "reason": "deny_keyword", "matched_pattern": deny_keyword}
    allow_keywords = source_policy.get("allow_keywords", [])
    allow_keyword = first_pattern_hit(allow_keywords, keyword_surface)
    if allow_keywords and not allow_keyword:
        return False, {"enabled": True, "allowed": False, "reason": "allow_keyword_not_matched"}

    return True, {
        "enabled": True,
        "allowed": True,
        "matched_allow_extension": allow_extension,
        "matched_allow_path": allow_path,
        "matched_allow_file_name": allow_file_name,
        "matched_allow_directory": allow_directory,
        "matched_allow_keyword": allow_keyword,
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "metadata_only": True,
    }


def first_exact_hit(patterns: Iterable[str], value: str) -> Optional[str]:
    normalized = value.lower().strip().lstrip(".")
    for pattern in patterns:
        if pattern.lower().strip().lstrip(".") == normalized:
            return pattern
    return None


def first_pattern_hit(patterns: Iterable[str], surface: str) -> Optional[str]:
    for pattern in patterns:
        if pattern.lower() in surface:
            return pattern
    return None


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
