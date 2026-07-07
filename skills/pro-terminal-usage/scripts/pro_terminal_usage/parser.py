"""Parse professional terminal usage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency for runtime installs
    openpyxl = None


COLLECTOR = "pro-terminal-usage"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_RECORD_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".ndjson",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xlsm",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
    ".ini",
    ".conf",
    ".log",
}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SUPPORTED_ZIP_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session", "license")
CONTENT_KEY_FRAGMENTS = ("content", "body", "正文", "全文", "payload", "result")
EXPECTED_PRO_TERMINALS = ("wind", "choice", "ifind", "bloomberg")
EXPECTED_TERMINAL_ACTIVITY_TYPES = ("workspace", "watchlist", "search", "download", "model_template", "factor_attention")
RECOMMENDED_WORKFLOW_FIELDS = (
    "workspace",
    "project",
    "module",
    "function_code",
    "menu_path",
    "query",
    "symbols",
    "universe",
    "industries",
    "regions",
    "factors",
    "datasets",
    "fields",
    "template_name",
    "frequency",
    "date_range",
    "download_format",
    "file_name",
)
SECTION_ACTIVITY_TYPES = {
    "usage": None,
    "workspaces": "workspace",
    "dashboards": "workspace",
    "watchlists": "watchlist",
    "searches": "search",
    "queries": "search",
    "downloads": "download",
    "exports": "download",
    "templates": "model_template",
    "models": "model_template",
    "factors": "factor_attention",
    "indicators": "factor_attention",
}
VENDOR_TERMS = {
    "wind": ("wind", "万得"),
    "choice": ("choice", "东方财富choice"),
    "ifind": ("ifind", "同花顺ifind", "同花顺 iFinD", "同花顺ifind"),
    "bloomberg": ("bloomberg", "彭博"),
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="pro_terminal_usage_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events or [gap_event(collected_at=collected_at, reason="pro_terminal_usage_records_empty")]


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and is_supported_path(child):
                    yield child
        elif path.is_file() and is_supported_path(path):
            yield path


def is_supported_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return parse_zip(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path, path_label=str(path))
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
        rows = extract_records(json.loads(text))
    records = [row if isinstance(row, dict) else {"value": row} for row in rows]
    for record in records:
        record.setdefault("_source_path", path_label)
    return records


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    context = {
        str(key): value
        for key, value in loaded.items()
        if not isinstance(value, (list, dict)) and value not in (None, "")
    }
    collected: List[Any] = []
    for key in (
        "usage",
        "workspaces",
        "dashboards",
        "watchlists",
        "searches",
        "queries",
        "downloads",
        "exports",
        "templates",
        "models",
        "factors",
        "indicators",
        "records",
        "items",
        "data",
        "list",
    ):
        value = loaded.get(key)
        if isinstance(value, list):
            collected.extend(with_section_context(item, key, context) for item in value)
        elif isinstance(value, dict):
            collected.extend(with_section_context(item, key, context) for item in extract_records(value))
    if collected:
        return collected
    return [loaded]


def with_section_context(item: Any, section: str, context: Dict[str, Any]) -> Any:
    activity_type = SECTION_ACTIVITY_TYPES.get(section)
    if not isinstance(item, dict):
        return {"value": item, "source_section": section, "activity_type": activity_type}
    record = {**context, **item}
    record.setdefault("source_section", section)
    if activity_type:
        record.setdefault("activity_type", activity_type)
    return record


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_text(text, suffix=path.suffix.lower(), path_label=str(path))


def parse_table_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    records = [dict(row) for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    for record in records:
        record.setdefault("_source_path", path_label)
    return records


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_workbook(path_or_stream: Any, *, path_label: Optional[str] = None) -> List[Dict[str, Any]]:
    if openpyxl is None:
        return []
    workbook = openpyxl.load_workbook(path_or_stream, read_only=True, data_only=True)
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
                    if path_label:
                        record.setdefault("_source_path", path_label)
                    record.setdefault("source_section", sheet.title)
                    records.append(record)
    finally:
        workbook.close()
    return records


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_html_text(html, path_label=str(path), default_title=path.stem)


def parse_html_text(html: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    text = html_to_text(html)
    return {
        "activity_type": "workspace",
        "title": title_tag(html) or infer_title(default_title, text),
        "source": meta_content(html, "application-name") or meta_content(html, "og:site_name"),
        "content": text,
        "_source_path": path_label,
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_text_text(text, path_label=str(path), default_title=path.stem)


def parse_text_text(text: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    return {
        "activity_type": infer_activity_from_text(text, path_label),
        "title": infer_title(default_title, text),
        "content": text,
        "_source_path": path_label,
    }


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            if should_skip_zip_member(member):
                continue
            suffix = Path(member.filename).suffix.lower()
            path_label = f"{path.name}::{member.filename}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".xlsx", ".xlsm"}:
                    parsed = parse_workbook(io.BytesIO(archive.read(member)), path_label=path_label)
                elif suffix in {".html", ".htm"}:
                    parsed = [parse_html_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member.filename).stem)]
                else:
                    parsed = [parse_text_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member.filename).stem)]
            except Exception:
                parsed = []
            records.extend(parsed)
    return records


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    member_path = Path(member.filename)
    if member.is_dir():
        return True
    if member_path.is_absolute() or ".." in member_path.parts:
        return True
    return member_path.suffix.lower() not in SUPPORTED_ZIP_EXTENSIONS


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    path_label = str(record.get("_source_path") or first(record, ["source_path", "file"]) or path)
    activity_type = infer_activity_type(record, path_label)
    terminal = infer_terminal(record, path_label)
    title = first(record, ["title", "name", "workspace", "template", "model", "标题", "名称", "工作区", "模板"]) or Path(path_label).stem
    text = first(record, ["text", "content", "description", "note", "summary", "正文", "内容", "备注", "说明"]) or ""
    query = first(record, ["query", "keyword", "search", "搜索词", "关键词"])
    event_time = first(record, ["time", "date", "created_at", "updated_at", "used_at", "downloaded_at", "时间", "日期", "使用时间", "下载时间"])
    data = {
        "activity_type": activity_type,
        "terminal": terminal,
        "title": title,
        "source_section": first(record, ["source_section", "sheet"]),
        "workspace": first(record, ["workspace", "workspace_name", "工作区", "工作台"]),
        "project": first(record, ["project", "project_name", "strategy", "portfolio", "项目", "策略", "组合"]),
        "module": first(record, ["module", "function", "page", "screen", "模块", "功能", "页面"]),
        "function_code": first(record, ["function_code", "command", "api", "formula", "函数", "命令", "公式"]),
        "menu_path": first(record, ["menu_path", "navigation", "path", "菜单路径", "导航路径"]),
        "query": query,
        "symbols": symbols_for(record),
        "universe": list_values(record, ["universe", "scope", "stock_pool", "股票池", "样本空间"]),
        "industries": list_values(record, ["industries", "industry", "行业"]),
        "regions": list_values(record, ["regions", "region", "markets", "market", "地区", "市场"]),
        "factors": list_values(record, ["factors", "factor", "因子", "指标"]),
        "datasets": list_values(record, ["datasets", "dataset", "database", "table", "数据集", "数据库", "表"]),
        "fields": list_values(record, ["fields", "field", "columns", "indicators", "字段", "列", "指标"]),
        "template_name": first(record, ["template_name", "template", "model_name", "模板名称", "模型名称"]),
        "frequency": first(record, ["frequency", "freq", "周期", "频率"]),
        "date_range": first(record, ["date_range", "range", "区间", "日期区间"]),
        "start_date": first(record, ["start_date", "from_date", "开始日期"]),
        "end_date": first(record, ["end_date", "to_date", "结束日期"]),
        "download_format": first(record, ["download_format", "format", "file_type", "文件格式", "格式"]),
        "file_name": first(record, ["file_name", "filename", "export_name", "文件名", "导出文件"]),
        "file_path_hint": first(record, ["file_path", "local_path", "path_hint", "文件路径"]),
        "content_preview": text[:800],
        "has_content_preview": bool(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_label, row, terminal, activity_type, title, query, event_time),
        "collector": COLLECTOR,
        "source": "专业终端用户工作流痕迹",
        "owner_scope": "personal",
        "kind": kind_for_activity(activity_type),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": path_label,
            "row": row,
            "terminal": terminal,
            "activity_type": activity_type,
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["work_confidential"],
        },
        "wiki_targets": wiki_targets_for_activity(activity_type),
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "专业终端使用痕迹授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "activity_type": "collector_gap",
            "gap": reason,
            "message": "No user-authorized professional terminal workflow export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["work_confidential"]},
        "wiki_targets": ["investor.data_quality.collection_gaps"],
    }


def infer_activity_type(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["activity_type", "type", "kind", "action", "event", "类型", "动作", "行为"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path_label).lower()
    probe = (explicit or text).lower()
    if any(token in probe for token in ("watchlist", "自选", "关注证券", "portfolio list")):
        return "watchlist"
    if any(token in probe for token in ("search", "query", "搜索", "检索")):
        return "search"
    if any(token in probe for token in ("download", "export", "导出", "下载")):
        return "download"
    if any(token in probe for token in ("template", "model", "模型", "模板", "估值表")):
        return "model_template"
    if any(token in probe for token in ("factor", "因子", "指标", "roe", "pe", "pb")):
        return "factor_attention"
    if any(token in probe for token in ("workspace", "dashboard", "workbench", "工作区", "工作台", "看板")):
        return "workspace"
    return infer_activity_from_text(text, path_label)


def infer_activity_from_text(text: str, path_label: str) -> str:
    lowered = (text + " " + str(path_label)).lower()
    if any(token in lowered for token in ("自选", "watchlist")):
        return "watchlist"
    if any(token in lowered for token in ("搜索", "search")):
        return "search"
    if any(token in lowered for token in ("下载", "导出", "download", "export")):
        return "download"
    if any(token in lowered for token in ("模型", "模板", "model", "template")):
        return "model_template"
    if any(token in lowered for token in ("因子", "roe", "pe", "pb", "factor")):
        return "factor_attention"
    return "workspace"


def infer_terminal(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["terminal", "platform", "app", "source_app", "终端", "平台", "应用"])
    text = (explicit or "") + " " + json.dumps(record, ensure_ascii=False) + " " + str(path_label)
    lowered = text.lower()
    for terminal, terms in VENDOR_TERMS.items():
        if any(term.lower() in lowered for term in terms):
            return terminal
    return "unknown"


def kind_for_activity(activity_type: str) -> str:
    if activity_type == "watchlist":
        return "watchlist"
    if activity_type in {"workspace", "model_template", "factor_attention"}:
        return "note"
    return "other"


def wiki_targets_for_activity(activity_type: str) -> List[str]:
    targets = {
        "workspace": ["investor.research_consumption.workflow", "investor.capability_circle.analysis_ability"],
        "watchlist": ["investor.capability_circle.attention_universe", "investor.execution.watchlist_alerts"],
        "search": ["investor.research_consumption.workflow", "investor.information_sources.news_consumption"],
        "download": ["investor.research_consumption.workflow", "investor.record_review.review_record"],
        "model_template": ["investor.decision_framework.strategy_rules", "investor.capability_circle.analysis_ability"],
        "factor_attention": ["investor.capability_circle.analysis_ability", "investor.decision_framework.monitoring_rules"],
    }
    return targets.get(activity_type, ["investor.data_quality.collection_gaps"])


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in events)
    terminal_counts = Counter((event.get("data") or {}).get("terminal", "unknown") for event in events)
    gap_only = bool(events) and set(activity_counts) == {"collector_gap"}
    observed_terminals = sorted(terminal for terminal, count in terminal_counts.items() if count and terminal != "unknown")
    observed_expected_terminals = [terminal for terminal in EXPECTED_PRO_TERMINALS if terminal_counts.get(terminal)]
    missing_expected_terminals = [terminal for terminal in EXPECTED_PRO_TERMINALS if not terminal_counts.get(terminal)]
    unknown_terminal_count = sum(count for terminal, count in terminal_counts.items() if terminal not in EXPECTED_PRO_TERMINALS)
    observed_activities = sorted(activity for activity, count in activity_counts.items() if count and activity not in {"collector_gap", "unknown"})
    observed_expected_activities = [activity for activity in EXPECTED_TERMINAL_ACTIVITY_TYPES if activity_counts.get(activity)]
    missing_expected_activities = [activity for activity in EXPECTED_TERMINAL_ACTIVITY_TYPES if not activity_counts.get(activity)]
    unknown_activity_count = sum(count for activity, count in activity_counts.items() if activity not in EXPECTED_TERMINAL_ACTIVITY_TYPES and activity != "collector_gap")
    field_counts = Counter(
        field
        for event in events
        for field in RECOMMENDED_WORKFLOW_FIELDS
        if (event.get("data") or {}).get(field) not in (None, "", [])
    )
    observed_recommended_fields = [field for field in RECOMMENDED_WORKFLOW_FIELDS if field_counts.get(field)]
    missing_recommended_fields = [field for field in RECOMMENDED_WORKFLOW_FIELDS if not field_counts.get(field)]
    return {
        "schema": "pro_terminal.usage.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "activity_counts": dict(sorted(activity_counts.items())),
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "terminal_coverage": {
            "expected_p2_terminals": list(EXPECTED_PRO_TERMINALS),
            "observed_terminals": observed_terminals,
            "observed_expected_terminals": observed_expected_terminals,
            "missing_expected_terminals": missing_expected_terminals,
            "terminal_counts": dict(sorted(terminal_counts.items())),
            "unknown_terminal_count": unknown_terminal_count,
            "real_account_validation": False,
        },
        "activity_coverage": {
            "expected_activity_types": list(EXPECTED_TERMINAL_ACTIVITY_TYPES),
            "observed_activities": observed_activities,
            "observed_expected_activities": observed_expected_activities,
            "missing_expected_activities": missing_expected_activities,
            "activity_counts": dict(sorted(activity_counts.items())),
            "unknown_activity_count": unknown_activity_count,
            "real_account_validation": False,
        },
        "workflow_field_coverage": {
            "recommended_workflow_fields": list(RECOMMENDED_WORKFLOW_FIELDS),
            "observed_recommended_fields": observed_recommended_fields,
            "missing_recommended_fields": missing_recommended_fields,
            "field_counts": dict(sorted(field_counts.items())),
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": "needs_pro_terminal_usage_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_terminal_usage": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "license_boundary": "workflow_metadata_only",
            "terminal_coverage_status": coverage_status(events, missing_expected_terminals, "terminal"),
            "activity_coverage_status": coverage_status(events, missing_expected_activities, "activity_type"),
            "workflow_field_coverage_status": coverage_status(events, missing_recommended_fields, "workflow_field"),
            "next_action": "Provide authorized Wind/Choice/iFinD/Bloomberg workflow export." if gap_only else "Use as investor workflow evidence; continue licensed platform validation.",
        },
    }


def coverage_status(events: List[Dict[str, Any]], missing_expected: List[str], noun: str) -> str:
    if not events or all((event.get("data") or {}).get("activity_type") == "collector_gap" for event in events):
        return f"no_{noun}_observed"
    if not missing_expected:
        return f"all_expected_{noun}s_observed"
    return f"partial_expected_{noun}s_observed"


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    usable_events = 0
    for event in events:
        if (event.get("data") or {}).get("activity_type") == "collector_gap":
            continue
        usable_events += 1
        for target in event.get("wiki_targets", []):
            by_target[target].append(event)
    return {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": usable_events,
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
        },
        "coverage_summary": {
            "licensed_content_mirrored": False,
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }


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
            return split_terms(value)
        if isinstance(value, list):
            return clean_list_items(value)
    return []


def first_raw(record: Dict[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    normalized_key = normalize_key(key)
    for candidate, value in record.items():
        if normalize_key(candidate) == normalized_key:
            return value
    return None


def split_terms(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,，、;；|\n]+", text) if item.strip()]


def clean_list_items(items: List[Any]) -> List[str]:
    cleaned: List[str] = []
    for item in items:
        if isinstance(item, dict):
            value = first(item, ["name", "title", "code", "symbol", "field", "字段", "名称"])
        else:
            value = str(item)
        if value and value != "None":
            cleaned.append(value.strip())
    return cleaned


def symbols_for(record: Dict[str, Any]) -> List[str]:
    return list_values(record, ["symbols", "codes", "tickers", "securities", "证券", "代码", "股票"])


def sanitized(value: Any, key_hint: str = "") -> Any:
    lowered_hint = key_hint.lower()
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            clean[str(key)] = sanitized(item, str(key))
        return clean
    if isinstance(value, list):
        return [sanitized(item, key_hint) for item in value[:200]]
    if isinstance(value, str):
        cap = 800 if any(fragment in lowered_hint for fragment in CONTENT_KEY_FRAGMENTS) else 4000
        return value[:cap]
    return value


def title_tag(html: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(strip_tags(match.group(1))) if match else None


def meta_content(html: str, name: str) -> Optional[str]:
    pattern = (
        r"<meta[^>]+(?:name|property)=[\"']"
        + re.escape(name)
        + r"[\"'][^>]+content=[\"']([^\"']+)[\"'][^>]*>"
    )
    match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(unescape(match.group(1))) if match else None


def html_to_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(strip_tags(html))


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(value))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def infer_title(default_title: str, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return default_title


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
