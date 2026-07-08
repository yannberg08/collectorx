"""Parse user-authorized Tonghuashun watchlist exports."""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency for runtime installs
    openpyxl = None

try:
    from collectorx.investor_wiki import augment_evidence_with_dimensions
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution outside repo cwd
    for parent in Path(__file__).resolve().parents:
        if (parent / "collectorx").exists():
            sys.path.insert(0, str(parent))
            break
    from collectorx.investor_wiki import augment_evidence_with_dimensions


COLLECTOR = "ths-watchlist"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".xlsx",
    ".xlsm",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".markdown",
    ".zip",
}
ARCHIVE_MEMBER_EXTENSIONS = SUPPORTED_EXTENSIONS - {".zip"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
SUPPORTED_LOCAL_SCAN_PLATFORMS = {"auto", "mac", "windows", "linux", "generic"}
DEFAULT_MAC_SCAN_ROOTS = (
    Path.home() / "Library" / "Containers" / "cn.com.10jqka.macstockPro" / "Data",
    Path.home() / "Library" / "Application Support" / "同花顺",
    Path.home() / "Library" / "Application Support" / "10jqka",
)
DEFAULT_WINDOWS_SCAN_ROOTS = (
    Path.home() / "AppData" / "Roaming" / "10jqka",
    Path.home() / "AppData" / "Local" / "10jqka",
    Path.home() / "Documents" / "同花顺",
)
DEFAULT_LINUX_SCAN_ROOTS = (
    Path.home() / ".config" / "10jqka",
    Path.home() / ".local" / "share" / "10jqka",
    Path.home() / "Documents" / "同花顺",
)
LOCAL_SCAN_FILENAME_HINTS = (
    "自选",
    "自选股",
    "watchlist",
    "watch_list",
    "zixuan",
    "zxg",
    "my_stock",
    "mystock",
    "stockblock",
    "portfolio",
)
LOCAL_SCAN_MAX_FILES = 20000
INVESTOR_WIKI_SUBDIMENSION_RULES = {
    "inv-market-view": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist", "investor.capability_circle.attention_universe"],
        "signals": ["同花顺自选股能反映用户正在观察的市场机会。"],
        "gaps": ["自选不是持仓，也不能证明用户的市场信念。"],
    },
    "inv-value-preference": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist"],
        "signals": ["自选分组、备注和标签可作为资产偏好侧影。"],
        "gaps": ["偏好原因需要研究笔记、聊天或复盘补充。"],
    },
    "inv-industry-circle": {
        "support_level": "medium",
        "route_targets": ["investor.capability_circle.attention_universe"],
        "signals": ["自选列表中的行业、板块和标的可形成关注宇宙。"],
        "gaps": ["关注宇宙不等于能力圈，需要研究产物和交易复盘验证。"],
    },
    "inv-information-learning-style": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist", "investor.capability_circle.attention_universe"],
        "signals": ["分组和自选管理方式能提示用户组织投资信息的习惯。"],
        "gaps": ["仍缺少信息筛选、学习和验证过程。"],
    },
    "inv-style-profile": {
        "support_level": "weak",
        "route_targets": ["investor.opportunity_watchlist.watchlist"],
        "signals": ["自选池结构可作为风格画像的弱线索。"],
        "gaps": ["自选不等于真实交易风格。"],
    },
    "inv-information-source": {
        "support_level": "weak",
        "route_targets": ["investor.capability_circle.attention_universe"],
        "signals": ["同花顺自选源可记录用户的信息入口之一。"],
        "gaps": ["需要与交易、阅读、讨论和研究材料交叉验证。"],
    },
}

THS_WATCHLIST_SCOPE_POLICY_KEYS = (
    "allow_symbol",
    "deny_symbol",
    "allow_market",
    "deny_market",
    "allow_group",
    "deny_group",
    "allow_industry",
    "deny_industry",
    "allow_tag",
    "deny_tag",
    "allow_keyword",
    "deny_keyword",
    "allow_source",
    "deny_source",
    "allow_source_platform",
    "deny_source_platform",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(inputs, collected_at=collected_at, limit=limit)
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    local_scan: bool = False,
    platform: str = "auto",
    container_root: Optional[str] = None,
    scope_policy: Optional[Dict[str, Any]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    normalized_scope_policy = normalize_ths_watchlist_scope_policy(scope_policy)
    scope_policy_configured = ths_watchlist_scope_policy_configured(normalized_scope_policy)
    limit_during_parse = limit is not None and not scope_policy_configured
    local_scan_paths = find_local_watchlist_files(container_root=container_root, platform=platform) if local_scan else []
    local_scan_report = build_local_scan_report(
        platform=platform,
        container_root=container_root,
        files=local_scan_paths,
    ) if local_scan else None
    local_scan_meta = {
        path_key(path): {
            "local_scan": True,
            "source_platform": (local_scan_report or {}).get("platform", {}).get("resolved"),
            "source_path_label": local_file_label(path),
        }
        for path in local_scan_paths
    }
    input_resolution = resolve_input_paths([*input_list, *(str(path) for path in local_scan_paths)])
    paths = input_resolution["paths"]
    audit = {
        "source_type": "authorized_local_ths_watchlist_export_or_local_scan" if local_scan else "authorized_local_ths_watchlist_export",
        "input_count": len(input_list),
        "requested_inputs": requested_input_labels(input_list, local_scan_paths),
        "resolved_input_file_count": len(paths),
        "input_missing_count": input_resolution["input_missing_count"],
        "skipped_file_count": input_resolution["skipped_file_count"],
        "skipped_reason_counts": input_resolution["skipped_reason_counts"],
        "extension_counts": {},
        "skipped_extension_counts": input_resolution["skipped_extension_counts"],
        "archive_count": 0,
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "archive_member_imported_record_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "skipped_archive_member_reason_counts": {},
        "parsed_record_count": 0,
        "filtered_record_count": 0,
        "emitted_event_count": 0,
        "limit": limit,
        "limit_reached": False,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "archive_member_supported_extensions": sorted(ARCHIVE_MEMBER_EXTENSIONS),
        "local_scan_requested": local_scan,
        "local_scan_platform": (local_scan_report or {}).get("platform"),
        "local_scan_roots": (local_scan_report or {}).get("scan_roots", []),
        "local_scan_candidate_file_count": len(local_scan_paths),
        "local_scan_candidate_files": [local_file_label(path) for path in local_scan_paths],
        "local_scan_candidate_selection": (local_scan_report or {}).get("candidate_selection", {}),
        "local_scan_event_count": 0,
        "real_account_adapter_used": False,
        "broker_trade_source": False,
        "path_results": list(input_resolution["path_results"]),
        "archive_member_results": [],
    }
    if not paths:
        _unused, scope_audit = apply_ths_watchlist_scope_policy([], normalized_scope_policy)
        attach_ths_watchlist_scope_policy_audit(audit, scope_audit)
        events = [
            gap_event(
                collected_at=collected_at,
                reason="ths_watchlist_authorized_input_missing",
                collection_audit=audit,
            )
        ]
        audit["emitted_event_count"] = len(events)
        finalize_audit(audit)
        return events, audit
    events: List[Dict[str, Any]] = []
    for path in paths:
        if limit_during_parse and len(events) >= limit:
            audit["limit_reached"] = True
            break
        extension = path.suffix.lower() or "<none>"
        source_meta = local_scan_meta.get(path_key(path))
        increment_counter(audit, "extension_counts", extension)
        path_result = {
            "path": source_meta.get("source_path_label") if source_meta else str(path),
            "extension": extension,
            "parser": parser_name_for_path(path),
            "status": "parsed",
            "parsed_record_count": 0,
            "filtered_record_count": 0,
            "emitted_event_count": 0,
        }
        audit["path_results"].append(path_result)
        try:
            records = parse_path(path, audit=audit)
        except Exception:
            records = []
            path_result["status"] = "parse_error"
            increment_counter(audit, "skipped_reason_counts", "parse_error")
            increment_counter(audit, "skipped_extension_counts", extension)
            audit["skipped_file_count"] += 1
        path_result["parsed_record_count"] = len(records)
        audit["parsed_record_count"] += len(records)
        for row, record in enumerate(records, start=1):
            if not watchlist_symbol(record):
                path_result["filtered_record_count"] += 1
                audit["filtered_record_count"] += 1
                continue
            annotated_record = annotate_local_scan_record(record, path=path, source_meta=source_meta)
            events.append(record_to_event(annotated_record, path=path, row=row, collected_at=collected_at))
            path_result["emitted_event_count"] += 1
            if source_meta:
                audit["local_scan_event_count"] += 1
            if limit_during_parse and len(events) >= limit:
                audit["limit_reached"] = True
                audit["emitted_event_count"] = len(events[:limit])
                _limited_events, scope_audit = apply_ths_watchlist_scope_policy(events[:limit], normalized_scope_policy)
                attach_ths_watchlist_scope_policy_audit(audit, scope_audit)
                finalize_audit(audit)
                return events[:limit], audit
    pre_scope_policy_event_count = len(events)
    events, scope_audit = apply_ths_watchlist_scope_policy(events, normalized_scope_policy)
    attach_ths_watchlist_scope_policy_audit(audit, scope_audit)
    audit["pre_scope_policy_event_count"] = pre_scope_policy_event_count
    audit["pre_scope_policy_local_scan_event_count"] = audit["local_scan_event_count"]
    if limit is not None and len(events) > limit:
        audit["limit_reached"] = True
        events = events[:limit]
    audit["local_scan_event_count"] = sum(1 for event in events if (event.get("raw_ref") or {}).get("local_scan"))
    if not events:
        reason = "ths_watchlist_scope_policy_filtered_all" if audit.get("ths_watchlist_scope_policy_filtered_all") else "ths_watchlist_records_empty"
        events = [gap_event(collected_at=collected_at, reason=reason, collection_audit=audit)]
    audit["emitted_event_count"] = len(events)
    finalize_audit(audit)
    return events, audit


def resolve_local_scan_platform(platform: str = "auto") -> str:
    if platform not in SUPPORTED_LOCAL_SCAN_PLATFORMS:
        raise ValueError(f"Unsupported Tonghuashun watchlist scan platform: {platform}")
    if platform != "auto":
        return platform
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "generic"


def local_scan_roots(container_root: Optional[str] = None, *, platform: str = "auto") -> List[Path]:
    if container_root:
        return [Path(container_root).expanduser()]
    resolved = resolve_local_scan_platform(platform)
    if resolved == "mac":
        return list(DEFAULT_MAC_SCAN_ROOTS)
    if resolved == "windows":
        return list(DEFAULT_WINDOWS_SCAN_ROOTS)
    if resolved == "linux":
        return list(DEFAULT_LINUX_SCAN_ROOTS)
    return []


def find_local_watchlist_files(
    container_root: Optional[str] = None,
    *,
    platform: str = "auto",
) -> List[Path]:
    """Find likely Tonghuashun watchlist files under user-authorized local roots."""
    found: List[Path] = []
    for root in local_scan_roots(container_root, platform=platform):
        if not root.exists():
            continue
        scanned = 0
        try:
            iterator = root.rglob("*") if root.is_dir() else iter([root])
            for path in iterator:
                if not path.is_file():
                    continue
                scanned += 1
                if scanned > LOCAL_SCAN_MAX_FILES:
                    break
                if is_local_watchlist_candidate(path):
                    found.append(path)
        except OSError:
            continue
    return _dedupe_paths(found)


def build_local_scan_report(
    *,
    platform: str = "auto",
    container_root: Optional[str] = None,
    files: Optional[Iterable[Path]] = None,
) -> Dict[str, Any]:
    resolved = resolve_local_scan_platform(platform)
    file_list = _dedupe_paths(files if files is not None else find_local_watchlist_files(container_root=container_root, platform=platform))
    roots = local_scan_roots(container_root, platform=platform)
    return {
        "probe_type": "ths_watchlist_local_scan",
        "platform": {
            "requested": platform,
            "resolved": resolved,
            "structure_status": (
                "verified_on_current_mac"
                if resolved == "mac" and sys.platform == "darwin"
                else "candidate_rules_need_real_machine_verification"
            ),
        },
        "scan_roots": [safe_path_label(root) for root in roots],
        "watchlist_candidates": {
            "file_count": len(file_list),
            "files": [local_file_label(path) for path in file_list],
            "status": "available" if file_list else "not_found",
        },
        "candidate_selection": {
            "filename_hints": list(LOCAL_SCAN_FILENAME_HINTS),
            "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
            "max_scan_files_per_root": LOCAL_SCAN_MAX_FILES,
        },
        "privacy_policy": {
            "credentials": "not_read",
            "cookies_tokens_sessions": "not_read",
            "full_account_ids_in_paths": "masked_in_probe_and_local_scan_refs",
            "broker_trade_data": "not_collected_by_this_collector",
        },
    }


def is_local_watchlist_candidate(path: Path) -> bool:
    suffix = path.suffix.lower()
    if path.name.startswith(".") or suffix not in SUPPORTED_EXTENSIONS:
        return False
    text = str(path).lower()
    return any(hint.lower() in text for hint in LOCAL_SCAN_FILENAME_HINTS)


def annotate_local_scan_record(
    record: Dict[str, Any],
    *,
    path: Path,
    source_meta: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not source_meta:
        return record
    annotated = dict(record)
    annotated["_collectorx_local_scan"] = True
    annotated["_collectorx_source_platform"] = source_meta.get("source_platform")
    annotated["_collectorx_source_path_label"] = source_meta.get("source_path_label") or local_file_label(path)
    raw_ref = dict(annotated.get("_collectorx_raw_ref") or {})
    raw_ref["path"] = str(raw_ref.get("path") or annotated["_collectorx_source_path_label"])
    raw_ref["path"] = raw_ref["path"].replace(str(path), annotated["_collectorx_source_path_label"])
    if "archive" in raw_ref:
        raw_ref["archive"] = str(raw_ref["archive"]).replace(str(path), annotated["_collectorx_source_path_label"])
    raw_ref["local_scan"] = True
    raw_ref["source_platform"] = annotated["_collectorx_source_platform"]
    raw_ref["source_path_label"] = annotated["_collectorx_source_path_label"]
    annotated["_collectorx_raw_ref"] = raw_ref
    return annotated


def resolve_input_paths(inputs: Iterable[str]) -> Dict[str, Any]:
    paths: List[Path] = []
    requested_inputs: List[str] = []
    path_results: List[Dict[str, Any]] = []
    skipped_reason_counts: Dict[str, int] = {}
    skipped_extension_counts: Dict[str, int] = {}
    skipped_file_count = 0
    input_missing_count = 0
    for raw in inputs:
        path = Path(raw).expanduser()
        requested_inputs.append(str(path))
        if not path.exists():
            input_missing_count += 1
            increment_counter_value(skipped_reason_counts, "input_missing")
            path_results.append(path_result(path, status="missing", reason="input_missing"))
            continue
        candidates = sorted(child for child in path.rglob("*") if child.is_file()) if path.is_dir() else [path]
        for candidate in candidates:
            extension = candidate.suffix.lower() or "<none>"
            if candidate.name.startswith("."):
                skipped_file_count += 1
                increment_counter_value(skipped_reason_counts, "hidden_file")
                increment_counter_value(skipped_extension_counts, extension)
                path_results.append(path_result(candidate, status="skipped", reason="hidden_file"))
                continue
            if extension not in SUPPORTED_EXTENSIONS:
                skipped_file_count += 1
                increment_counter_value(skipped_reason_counts, "unsupported_extension")
                increment_counter_value(skipped_extension_counts, extension)
                path_results.append(path_result(candidate, status="skipped", reason="unsupported_extension"))
                continue
            paths.append(candidate)
    return {
        "paths": paths,
        "requested_inputs": requested_inputs,
        "input_missing_count": input_missing_count,
        "skipped_file_count": skipped_file_count,
        "skipped_reason_counts": skipped_reason_counts,
        "skipped_extension_counts": skipped_extension_counts,
        "path_results": path_results,
    }


def requested_input_labels(raw_inputs: Iterable[str], local_scan_paths: Iterable[Path]) -> List[str]:
    return [str(Path(raw).expanduser()) for raw in raw_inputs] + [local_file_label(path) for path in local_scan_paths]


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    yield from resolve_input_paths(inputs)["paths"]


def parse_path(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path)
    if suffix == ".zip":
        return parse_zip(path, audit=audit)
    return parse_text_codes(path)


def parse_zip(path: Path, *, audit: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if audit is not None:
        audit["archive_count"] += 1
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-ths-watchlist-") as tmp:
        tmp_root = Path(tmp)
        for info in archive.infolist():
            member_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(member_name)
            member_extension = Path(member_name).suffix.lower() or "<none>"
            if audit is not None:
                audit["archive_member_count"] += 1
                increment_counter(audit, "archive_member_extension_counts", member_extension)
            skip_reason = archive_member_skip_reason(info)
            if skip_reason:
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", member_extension)
                    increment_counter(audit, "skipped_archive_member_reason_counts", skip_reason)
                    append_archive_member_result(audit, member_name, status="skipped", reason=skip_reason)
                continue
            target = tmp_root.joinpath(*member_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(archive.read(info))
                parsed = parse_path(target)
            except Exception:
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", member_extension)
                    increment_counter(audit, "skipped_archive_member_reason_counts", "parse_error")
                    append_archive_member_result(audit, member_name, status="parse_error", reason="parse_error")
                continue
            if audit is not None:
                append_archive_member_result(audit, member_name, status="parsed" if parsed else "no_records_parsed", parsed_record_count=len(parsed))
            for member_row, record in enumerate(parsed, start=1):
                if isinstance(record, dict):
                    record["_collectorx_raw_ref"] = {
                        "path": f"{path}::{member_name}",
                        "archive": str(path),
                        "archive_member": member_name,
                        "member_row": member_row,
                    }
                records.append(record)
                if audit is not None:
                    audit["archive_member_imported_record_count"] += 1
    return records


def archive_member_skip_reason(info: zipfile.ZipInfo) -> Optional[str]:
    member_name = info.filename.replace("\\", "/")
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(info.filename)
    suffix = Path(member_name).suffix.lower()
    if info.is_dir():
        return "directory"
    if not is_safe_archive_member(member_path) or windows_path.drive:
        return "unsafe_path"
    if suffix not in ARCHIVE_MEMBER_EXTENSIONS:
        return "unsupported_extension"
    return None


def is_safe_archive_member(member_path: PurePosixPath) -> bool:
    return bool(member_path.parts) and not member_path.is_absolute() and ".." not in member_path.parts


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [{str(key): value for key, value in row.items() if key is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_records(json.loads(text))
    return [row if isinstance(row, dict) else {"code": row} for row in rows]


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"code": loaded}]
    context = {
        str(key): value
        for key, value in loaded.items()
        if not isinstance(value, (list, dict)) and value not in (None, "")
    }
    collected: List[Any] = []
    for key in ("watchlist", "watchlists", "stocks", "items", "records", "data", "list", "自选股"):
        value = loaded.get(key)
        if isinstance(value, list):
            collected.extend(with_context(item, key, context) for item in value)
        elif isinstance(value, dict):
            collected.extend(with_context(item, key, context) for item in extract_records(value))
    if collected:
        return collected
    return [loaded]


def with_context(item: Any, section: str, context: Dict[str, Any]) -> Any:
    if not isinstance(item, dict):
        return {**context, "code": item, "source_section": section}
    record = {**context, **item}
    record.setdefault("source_section", section)
    return record


def parse_workbook(path: Path) -> List[Dict[str, Any]]:
    if openpyxl is None:
        return []
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    records: List[Dict[str, Any]] = []
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            header_index = next((idx for idx, row in enumerate(rows) if any(cell not in (None, "") for cell in row)), None)
            if header_index is None:
                continue
            headers = [str(cell).strip() if cell not in (None, "") else f"column_{idx + 1}" for idx, cell in enumerate(rows[header_index])]
            for row in rows[header_index + 1 :]:
                record = {
                    headers[idx]: value
                    for idx, value in enumerate(row)
                    if idx < len(headers) and value not in (None, "")
                }
                if record:
                    record["sheet"] = sheet.title
                    records.append(record)
    finally:
        workbook.close()
    return records


def parse_text_codes(path: Path) -> List[Dict[str, Any]]:
    text = strip_tags(path.read_text(encoding="utf-8", errors="replace"))
    records: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(r"(?<!\d)(?:SH|SZ|BJ)?\s*(\d{6})(?:\.(?:SH|SZ|BJ))?(?!\d)", line, flags=re.IGNORECASE)
        if not match:
            continue
        code = match.group(1)
        name = line.replace(match.group(0), "").strip(" -_,，\t")
        records.append({"code": code, "name": name, "source_line": line})
    return records


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    symbol = normalize_symbol(watchlist_symbol(record) or "")
    name = first(record, ["name", "stock_name", "security_name", "证券名称", "名称"]) or ""
    group = first(record, ["group", "group_name", "folder", "watchlist", "分组", "自选分组"]) or first(record, ["sheet"])
    added_at = first(record, ["added_at", "created_at", "time", "date", "加入时间", "添加时间", "日期"])
    event_time = added_at or collected_at or now_iso()
    source_platform = first(record, ["_collectorx_source_platform"])
    local_scan = bool(first_raw(record, "_collectorx_local_scan"))
    data = {
        "symbol": symbol,
        "name": name,
        "market": normalize_market(first(record, ["market", "exchange", "市场", "交易所"]) or symbol),
        "group": group,
        "reason": first(record, ["reason", "note", "memo", "备注", "关注理由"]),
        "industry": first(record, ["industry", "sector", "行业", "板块"]),
        "tags": list_values(record, ["tags", "labels", "标签"]),
        "added_at": added_at,
        "source_platform": source_platform,
        "local_scan": local_scan or None,
        "source_section": first(record, ["source_section", "sheet"]),
        "raw": sanitized(record),
        "broker_confirmed_trade": False,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "path": str(path),
        "row": row,
        "symbol": symbol,
    }
    if isinstance(record.get("_collectorx_raw_ref"), dict):
        raw_ref.update(record["_collectorx_raw_ref"])
        raw_ref["row"] = row
        raw_ref["symbol"] = symbol
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, symbol, group, added_at),
        "collector": COLLECTOR,
        "source": "同花顺自选股用户授权本机扫描" if local_scan else "同花顺自选股用户授权导出",
        "owner_scope": "personal",
        "kind": "watchlist",
        "time": event_time,
        "collected_at": collected_at or event_time,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["portfolio"],
        },
        "wiki_targets": [
            "investor.opportunity_watchlist.watchlist",
            "investor.capability_circle.attention_universe",
        ],
    }


def gap_event(
    *,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    messages = {
        "ths_watchlist_authorized_input_missing": "No user-authorized Tonghuashun watchlist input or local-scan candidate was available.",
        "ths_watchlist_records_empty": "Tonghuashun watchlist inputs were available, but no usable watchlist records were parsed.",
        "ths_watchlist_scope_policy_filtered_all": "Tonghuashun watchlist records were found, but every candidate was outside the configured authorization scope policy.",
    }
    statuses = {
        "ths_watchlist_authorized_input_missing": "needs_ths_watchlist_authorized_input",
        "ths_watchlist_records_empty": "no_usable_ths_watchlist_records",
        "ths_watchlist_scope_policy_filtered_all": "scope_policy_filtered_all",
    }
    audit = collection_audit or {}
    scope_audit = audit.get("ths_watchlist_scope_policy") or {}
    timestamp = collected_at or now_iso()
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "同花顺自选股授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": timestamp,
        "collected_at": timestamp,
        "data": {
            "gap": reason,
            "status": statuses.get(reason, "no_usable_ths_watchlist_records"),
            "profile_type": reason,
            "message": messages.get(reason, "Tonghuashun watchlist collection produced no usable events."),
            "candidate_event_count": scope_audit.get("candidate_event_count", audit.get("scope_policy_candidate_event_count", 0)),
            "retained_event_count": scope_audit.get("retained_event_count", audit.get("scope_policy_retained_event_count", 0)),
            "filtered_event_count": scope_audit.get("filtered_event_count", audit.get("scope_policy_filtered_event_count", 0)),
            "filter_reason_counts": scope_audit.get("filter_reason_counts", audit.get("scope_policy_filter_reason_counts", {})),
            "policy_is_user_authorization_scope": scope_audit.get("policy_is_user_authorization_scope", True),
            "policy_does_not_assert_investment_relevance": scope_audit.get("policy_does_not_assert_investment_relevance", True),
            "watchlist_is_attention_universe_only": True,
            "broker_trade_fact_claimed": False,
            "holding_fact_claimed": False,
            "order_or_fund_flow_claimed": False,
        },
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "scope_policy_enabled": bool(scope_audit.get("configured", False)),
        },
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio", "collection_gap"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    market_counts = Counter((event.get("data") or {}).get("market", "unknown") for event in events if event["kind"] == "watchlist")
    group_counts = Counter((event.get("data") or {}).get("group", "unknown") for event in events if event["kind"] == "watchlist")
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    watchlist_event_count = sum(1 for event in events if event.get("kind") == "watchlist")
    gap_event_count = sum(1 for event in events if (event.get("data") or {}).get("gap"))
    field_coverage = build_watchlist_field_coverage(events)
    audit = collection_audit or {}
    local_scan_event_count = sum(1 for event in events if (event.get("raw_ref") or {}).get("local_scan"))
    source_collection_scope = "none" if gap_only else "partial_authorized_input"
    if local_scan_event_count:
        source_collection_scope = "partial_authorized_input_or_local_scan"
    if gap_only and audit.get("ths_watchlist_scope_policy_filtered_all"):
        readiness_status = "scope_policy_filtered_all"
        can_enter_finclaw = False
        source_collection_scope = "scope_policy_excluded_all"
        next_action = "Review or relax Tonghuashun watchlist authorization scope policy, then rerun the collector."
    elif gap_only:
        readiness_status = "needs_ths_watchlist_authorized_input"
        can_enter_finclaw = False
        next_action = "Provide authorized Tonghuashun watchlist export or run authorized local scan."
    else:
        readiness_status = "events_collected"
        can_enter_finclaw = True
        next_action = "Use as attention-universe evidence; corroborate with trades and research."
    return {
        "schema": "collectorx.ths_watchlist.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "watchlist_event_count": watchlist_event_count,
        "gap_event_count": gap_event_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "market_counts": dict(sorted(market_counts.items())),
        "group_counts": dict(sorted(group_counts.items())),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "local_scan_event_count": local_scan_event_count,
        "field_coverage": field_coverage,
        "evidence_policy": {
            "ths_watchlist_is_strong_trade_source": False,
            "broker_confirmed_trade_collection": False,
            "evidence_role": "attention_universe_only",
            "requires_corroboration_with": ["ths_portfolio", "eastmoney_portfolio", "research_documents", "investment_notes", "reviews"],
        },
        "collection_readiness": {
            "status": readiness_status,
            "can_enter_finclaw": can_enter_finclaw,
            "can_claim_complete_ths_attention_universe": False,
            "source_collection_scope": source_collection_scope,
            "next_action": next_action,
        },
        "collection_audit": audit,
        "ths_watchlist_boundary_proof": build_watchlist_boundary_proof(
            events,
            collection_audit=audit,
            field_coverage=field_coverage,
            market_counts=market_counts,
            group_counts=group_counts,
        ),
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    usable_events = [event for event in events if not (event.get("data") or {}).get("gap")]
    by_target: Dict[str, List[Dict[str, Any]]] = {}
    for event in usable_events:
        for target in event.get("wiki_targets") or []:
            by_target.setdefault(str(target), []).append(event)
    evidence = {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": len(usable_events),
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
        },
        "coverage_summary": {
            "ths_watchlist_is_strong_trade_source": False,
            "watchlist_attention_universe_only": True,
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }
    return augment_evidence_with_dimensions(evidence, usable_events, INVESTOR_WIKI_SUBDIMENSION_RULES)


def build_watchlist_field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    watchlist_events = [event for event in events if event.get("kind") == "watchlist"]
    fields = [
        "symbol",
        "market",
        "name",
        "group",
        "industry",
        "reason",
        "tags",
        "added_at",
        "source_section",
    ]
    coverage: Dict[str, Dict[str, int]] = {}
    for field in fields:
        present = sum(1 for event in watchlist_events if (event.get("data") or {}).get(field) not in (None, "", [], {}))
        coverage[field] = {"present": present, "missing": max(len(watchlist_events) - present, 0)}
    return {
        "watchlist_event_count": len(watchlist_events),
        "fields": coverage,
    }


def split_scope_values(values: Any) -> List[str]:
    if values in (None, ""):
        return []
    raw_items = values if isinstance(values, (list, tuple, set)) else [values]
    out: List[str] = []
    seen = set()
    for item in raw_items:
        if isinstance(item, (list, tuple, set)):
            parts = split_scope_values(item)
        else:
            parts = [part.strip() for part in re.split(r"[,，;；]", str(item)) if part.strip()]
        for part in parts:
            key = part.lower()
            if key and key not in seen:
                seen.add(key)
                out.append(part)
    return out


def normalize_ths_watchlist_scope_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    policy = policy or {}
    return {key: split_scope_values(policy.get(key)) for key in THS_WATCHLIST_SCOPE_POLICY_KEYS}


def ths_watchlist_scope_policy_configured(policy: Dict[str, List[str]]) -> bool:
    return any(policy.get(key) for key in THS_WATCHLIST_SCOPE_POLICY_KEYS)


def apply_ths_watchlist_scope_policy(
    events: List[Dict[str, Any]],
    policy: Optional[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    normalized_policy = normalize_ths_watchlist_scope_policy(policy)
    configured = ths_watchlist_scope_policy_configured(normalized_policy)
    candidates = [event for event in events if event.get("kind") == "watchlist"]
    retained: List[Dict[str, Any]] = []
    reason_counts: Counter = Counter()
    for event in events:
        if event.get("kind") != "watchlist":
            retained.append(event)
            continue
        reasons = ths_watchlist_scope_filter_reasons(event, normalized_policy) if configured else []
        if reasons:
            for reason in reasons:
                reason_counts[reason] += 1
            continue
        retained.append(event)
    retained_watchlist_count = sum(1 for event in retained if event.get("kind") == "watchlist")
    audit = {
        "configured": configured,
        "filters": normalized_policy,
        "candidate_event_count": len(candidates),
        "retained_event_count": retained_watchlist_count,
        "filtered_event_count": len(candidates) - retained_watchlist_count,
        "filter_reason_counts": dict(sorted(reason_counts.items())),
        "filtered_all": configured and bool(candidates) and retained_watchlist_count == 0,
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "watchlist_is_attention_universe_only": True,
        "deny_rules_win_over_allow_rules": True,
    }
    return retained, audit


def attach_ths_watchlist_scope_policy_audit(audit: Dict[str, Any], scope_audit: Dict[str, Any]) -> None:
    audit["ths_watchlist_scope_policy"] = scope_audit
    audit["scope_policy_candidate_event_count"] = scope_audit.get("candidate_event_count", 0)
    audit["scope_policy_retained_event_count"] = scope_audit.get("retained_event_count", 0)
    audit["scope_policy_filtered_event_count"] = scope_audit.get("filtered_event_count", 0)
    audit["scope_policy_filter_reason_counts"] = scope_audit.get("filter_reason_counts", {})
    audit["ths_watchlist_scope_policy_filtered_all"] = bool(scope_audit.get("filtered_all"))


def ths_watchlist_scope_filter_reasons(event: Dict[str, Any], policy: Dict[str, List[str]]) -> List[str]:
    data = event.get("data") or {}
    source_values = ths_watchlist_scope_source_values(event)
    checks = [
        ("symbol", policy.get("allow_symbol", []), policy.get("deny_symbol", []), [data.get("symbol"), data.get("code")], scope_identity_match),
        ("market", policy.get("allow_market", []), policy.get("deny_market", []), [data.get("market")], scope_identity_match),
        ("group", policy.get("allow_group", []), policy.get("deny_group", []), [data.get("group")], scope_text_match),
        ("industry", policy.get("allow_industry", []), policy.get("deny_industry", []), [data.get("industry")], scope_text_match),
        ("tag", policy.get("allow_tag", []), policy.get("deny_tag", []), list(data.get("tags") or []), scope_text_match),
        ("keyword", policy.get("allow_keyword", []), policy.get("deny_keyword", []), [ths_watchlist_scope_search_text(event)], scope_text_match),
        ("source", policy.get("allow_source", []), policy.get("deny_source", []), source_values, scope_text_match),
        (
            "source_platform",
            policy.get("allow_source_platform", []),
            policy.get("deny_source_platform", []),
            [data.get("source_platform"), (event.get("raw_ref") or {}).get("source_platform")],
            scope_identity_match,
        ),
    ]
    reasons: List[str] = []
    for name, allow_patterns, deny_patterns, values, matcher in checks:
        if deny_patterns and any_scope_match(values, deny_patterns, matcher):
            reasons.append(f"deny_{name}")
        if allow_patterns and not any_scope_match(values, allow_patterns, matcher):
            reasons.append(f"allow_{name}_mismatch")
    return reasons


def any_scope_match(values: Iterable[Any], patterns: Iterable[str], matcher) -> bool:
    return any(matcher(value, pattern) for value in values if value not in (None, "", [], {}) for pattern in patterns)


def scope_identity_match(value: Any, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    normalized_value_symbol = normalize_symbol(value_norm).lower()
    normalized_pattern_symbol = normalize_symbol(pattern_norm).lower()
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm) or (
            bool(normalized_value_symbol)
            and bool(normalized_pattern_symbol)
            and normalized_pattern_symbol not in {"*", "?"}
            and fnmatch.fnmatch(normalized_value_symbol, normalized_pattern_symbol)
        )
    return value_norm == pattern_norm or (
        bool(normalized_value_symbol)
        and bool(normalized_pattern_symbol)
        and normalized_value_symbol == normalized_pattern_symbol
    )


def scope_text_match(value: Any, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm)
    return pattern_norm in value_norm


def ths_watchlist_scope_source_values(event: Dict[str, Any]) -> List[Any]:
    raw_ref = event.get("raw_ref") or {}
    data = event.get("data") or {}
    return [
        event.get("source"),
        raw_ref.get("path"),
        raw_ref.get("archive"),
        raw_ref.get("archive_member"),
        raw_ref.get("source_path_label"),
        data.get("source_platform"),
        data.get("source_section"),
    ]


def ths_watchlist_scope_search_text(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    values = [
        data.get("symbol"),
        data.get("code"),
        data.get("market"),
        data.get("name"),
        data.get("group"),
        data.get("industry"),
        data.get("reason"),
        data.get("source_platform"),
        data.get("source_section"),
        *(data.get("tags") or []),
        *ths_watchlist_scope_source_values(event),
        json.dumps(raw, ensure_ascii=False, sort_keys=True) if raw else "",
    ]
    return "\n".join(str(value) for value in values if value not in (None, "", [], {}))


def ths_watchlist_authorization_scope_boundary(collection_audit: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    audit = collection_audit or {}
    scope = audit.get("ths_watchlist_scope_policy") or {}
    return {
        "policy_configured": bool(scope.get("configured")),
        "filters": scope.get("filters", normalize_ths_watchlist_scope_policy(None)),
        "candidate_event_count": scope.get("candidate_event_count", 0),
        "retained_event_count": scope.get("retained_event_count", 0),
        "filtered_event_count": scope.get("filtered_event_count", 0),
        "filter_reason_counts": scope.get("filter_reason_counts", {}),
        "filtered_all": bool(scope.get("filtered_all")),
        "policy_is_user_authorization_scope": scope.get("policy_is_user_authorization_scope", True),
        "policy_does_not_assert_investment_relevance": scope.get("policy_does_not_assert_investment_relevance", True),
        "deny_rules_win_over_allow_rules": scope.get("deny_rules_win_over_allow_rules", True),
    }


def build_watchlist_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    collection_audit: Dict[str, Any],
    field_coverage: Dict[str, Any],
    market_counts: Counter[str],
    group_counts: Counter[str],
) -> Dict[str, Any]:
    usable_events = [event for event in events if event.get("kind") == "watchlist"]
    gap_only = bool(events) and not usable_events
    scope_policy_filtered_all = bool(collection_audit.get("ths_watchlist_scope_policy_filtered_all"))
    if scope_policy_filtered_all:
        proof_level = "scope_policy_filtered_all"
    elif not events or gap_only:
        proof_level = "no_authorized_ths_watchlist_input"
    elif int(collection_audit.get("local_scan_event_count") or 0) > 0:
        proof_level = "authorized_ths_local_scan_partial"
    elif int(collection_audit.get("archive_member_imported_record_count") or 0) > 0:
        proof_level = "authorized_ths_watchlist_package_partial"
    else:
        proof_level = "authorized_ths_watchlist_partial"
    return {
        "source_type": collection_audit.get("source_type", "authorized_local_ths_watchlist_export"),
        "proof_level": proof_level,
        "event_count": len(usable_events),
        "parsed_record_count": collection_audit.get("parsed_record_count", 0),
        "filtered_record_count": collection_audit.get("filtered_record_count", 0),
        "emitted_event_count": collection_audit.get("emitted_event_count", len(events)),
        "authorization_scope_boundary": ths_watchlist_authorization_scope_boundary(collection_audit),
        "input_boundary": {
            "input_count": collection_audit.get("input_count", 0),
            "requested_inputs": collection_audit.get("requested_inputs", []),
            "resolved_input_file_count": collection_audit.get("resolved_input_file_count", 0),
            "input_missing_count": collection_audit.get("input_missing_count", 0),
            "skipped_file_count": collection_audit.get("skipped_file_count", 0),
            "skipped_reason_counts": collection_audit.get("skipped_reason_counts", {}),
            "limit": collection_audit.get("limit"),
            "limit_reached": collection_audit.get("limit_reached", False),
        },
        "format_boundary": {
            "extension_counts": collection_audit.get("extension_counts", {}),
            "skipped_extension_counts": collection_audit.get("skipped_extension_counts", {}),
            "archive_count": collection_audit.get("archive_count", 0),
            "archive_member_count": collection_audit.get("archive_member_count", 0),
            "archive_member_extension_counts": collection_audit.get("archive_member_extension_counts", {}),
            "archive_member_imported_record_count": collection_audit.get("archive_member_imported_record_count", 0),
            "skipped_archive_member_count": collection_audit.get("skipped_archive_member_count", 0),
            "skipped_archive_member_reason_counts": collection_audit.get("skipped_archive_member_reason_counts", {}),
        },
        "local_scan_boundary": {
            "local_scan_requested": collection_audit.get("local_scan_requested", False),
            "local_scan_platform": collection_audit.get("local_scan_platform"),
            "local_scan_roots": collection_audit.get("local_scan_roots", []),
            "local_scan_candidate_file_count": collection_audit.get("local_scan_candidate_file_count", 0),
            "local_scan_candidate_files": collection_audit.get("local_scan_candidate_files", []),
            "local_scan_event_count": collection_audit.get("local_scan_event_count", 0),
            "candidate_selection": collection_audit.get("local_scan_candidate_selection", {}),
            "credentials_read": False,
            "cookies_tokens_sessions_read": False,
        },
        "watchlist_surface": {
            "market_counts": dict(sorted(market_counts.items())),
            "group_counts": dict(sorted(group_counts.items())),
            "field_coverage": field_coverage,
            "archive_member_event_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("archive_member")),
            "local_scan_event_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("local_scan")),
        },
        "strong_trade_boundary": {
            "broker_confirmed_trade_collection": False,
            "holdings_collected": False,
            "executions_collected": False,
            "orders_collected": False,
            "fund_flows_collected": False,
            "watchlist_attention_universe_only": True,
            "requires_corroboration_with": ["ths_portfolio", "eastmoney_portfolio", "research_documents", "investment_notes", "reviews"],
        },
        "complete_attention_universe_claimed": False,
        "direct_tonghuashun_account_reconnect": False,
        "local_scan_without_trade_password": True,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": bool(usable_events) and not scope_policy_filtered_all,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_summary(path: Path, manifest: Dict[str, Any]) -> None:
    lines = [
        "# Tonghuashun Watchlist Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Watchlist evidence is an attention-universe signal and should be corroborated with trades, notes, and research.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def watchlist_symbol(record: Dict[str, Any]) -> Optional[str]:
    stock = first_raw(record, "stock")
    stock_record = stock if isinstance(stock, dict) else {}
    return first(record, ["symbol", "code", "stock_code", "stockCode", "证券代码", "股票代码", "代码"]) or first(
        stock_record,
        ["symbol", "code", "stock_code", "stockCode"],
    )


def increment_counter(audit: Dict[str, Any], key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def increment_counter_value(counts: Dict[str, int], value: str) -> None:
    counts[value] = int(counts.get(value, 0)) + 1


def path_result(path: Path, *, status: str, reason: Optional[str] = None) -> Dict[str, Any]:
    result = {
        "path": str(path),
        "extension": path.suffix.lower() or "<none>",
        "status": status,
    }
    if reason:
        result["reason"] = reason
    return result


def parser_name_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix in {".csv", ".tsv"}:
        return "csv"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
    if suffix in {".xlsx", ".xlsm"}:
        return "openpyxl"
    if suffix in {".html", ".htm", ".txt", ".md", ".markdown"}:
        return "text"
    return "unknown"


def append_archive_member_result(
    audit: Dict[str, Any],
    member: str,
    *,
    status: str,
    reason: Optional[str] = None,
    parsed_record_count: Optional[int] = None,
) -> None:
    result = {"member": member, "status": status}
    if reason:
        result["reason"] = reason
    if parsed_record_count is not None:
        result["parsed_record_count"] = parsed_record_count
    audit.setdefault("archive_member_results", []).append(result)


def finalize_audit(audit: Dict[str, Any]) -> None:
    for key in (
        "extension_counts",
        "skipped_extension_counts",
        "skipped_reason_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "skipped_archive_member_reason_counts",
        "scope_policy_filter_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    normalized = {normalize_key(key): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(normalize_key(key))
        if value not in (None, ""):
            return str(value)
    return None


def normalize_key(value: Any) -> str:
    return re.sub(r"[\s_\-/%()（）]+", "", str(value).lower())


def list_values(record: Dict[str, Any], keys: Iterable[str]) -> List[str]:
    for key in keys:
        value = first_raw(record, key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,，、;；|\n]+", value) if item.strip()]
        if isinstance(value, list):
            return [str(item.get("name") if isinstance(item, dict) else item) for item in value if str(item)]
    return []


def first_raw(record: Dict[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    normalized_key = normalize_key(key)
    for candidate, value in record.items():
        if normalize_key(candidate) == normalized_key:
            return value
    return None


def normalize_symbol(value: str) -> str:
    text = str(value).strip().upper()
    text = re.sub(r"^(SH|SZ|BJ)", "", text)
    text = re.sub(r"\.(SH|SZ|BJ)$", "", text)
    if text.isdigit() and len(text) < 6:
        if text.startswith("0") and len(text) >= 4:
            return text
        return text.zfill(6)
    return text


def normalize_market(value: Optional[str]) -> str:
    text = str(value or "").upper()
    if text.isdigit() and len(text) != 6:
        return "unknown"
    if "SH" in text or text.startswith(("6", "9")) or "沪" in text:
        return "SH"
    if "SZ" in text or text.startswith(("0", "2", "3")) or "深" in text:
        return "SZ"
    if "BJ" in text or text.startswith(("4", "8")) or "北" in text:
        return "BJ"
    return "unknown"


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            if any(fragment in str(key).lower() for fragment in SECRET_KEY_FRAGMENTS):
                continue
            clean[str(key)] = sanitized(item)
        return clean
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:4000]
    return value


def strip_tags(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "\n", value))


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    result: List[Path] = []
    for path in paths:
        key = path_key(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def path_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except OSError:
        return str(path.expanduser().absolute())


def safe_path_label(path: Path) -> str:
    text = str(path.expanduser())
    text = re.sub(r"(?<!\d)\d{6,}(?!\d)", "<digits>", text)
    text = re.sub(r"([A-Za-z0-9._%+-]{2})[A-Za-z0-9._%+-]*(@)", r"\1***\2", text)
    return text


def local_file_label(path: Path) -> str:
    return safe_path_label(path)
