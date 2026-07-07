"""Parse professional terminal usage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "pro-terminal-usage"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".html", ".htm", ".md", ".markdown", ".txt", ".ini", ".conf", ".log"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session", "license")
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
    return events


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
        rows = extract_records(json.loads(text))
    return [row if isinstance(row, dict) else {"value": row} for row in rows]


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    for key in ("usage", "workspaces", "watchlists", "searches", "downloads", "templates", "models", "factors", "records", "items", "data", "list"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
    return [loaded]


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [dict(row) for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "activity_type": "workspace",
        "title": title_tag(html) or infer_title(path, text),
        "source": meta_content(html, "application-name") or meta_content(html, "og:site_name"),
        "content": text,
        "path": str(path),
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "activity_type": infer_activity_from_text(text, path),
        "title": infer_title(path, text),
        "content": text,
        "path": str(path),
    }


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    activity_type = infer_activity_type(record, path)
    terminal = infer_terminal(record, path)
    title = first(record, ["title", "name", "workspace", "template", "model", "标题", "名称", "工作区", "模板"]) or path.stem
    text = first(record, ["text", "content", "description", "note", "summary", "正文", "内容", "备注", "说明"]) or ""
    query = first(record, ["query", "keyword", "search", "搜索词", "关键词"])
    event_time = first(record, ["time", "date", "created_at", "updated_at", "used_at", "downloaded_at", "时间", "日期", "使用时间", "下载时间"])
    data = {
        "activity_type": activity_type,
        "terminal": terminal,
        "title": title,
        "workspace": first(record, ["workspace", "workspace_name", "工作区", "工作台"]),
        "module": first(record, ["module", "function", "page", "screen", "模块", "功能", "页面"]),
        "query": query,
        "symbols": symbols_for(record),
        "industries": list_values(record, ["industries", "industry", "行业"]),
        "factors": list_values(record, ["factors", "factor", "因子", "指标"]),
        "template_name": first(record, ["template_name", "template", "model_name", "模板名称", "模型名称"]),
        "file_name": first(record, ["file_name", "filename", "export_name", "文件名", "导出文件"]),
        "content_preview": text[:800],
        "has_content_preview": bool(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, terminal, activity_type, title, query, event_time),
        "collector": COLLECTOR,
        "source": "专业终端用户工作流痕迹",
        "owner_scope": "personal",
        "kind": kind_for_activity(activity_type),
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
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


def infer_activity_type(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["activity_type", "type", "kind", "action", "event", "类型", "动作", "行为"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path).lower()
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
    return infer_activity_from_text(text, path)


def infer_activity_from_text(text: str, path: Path) -> str:
    lowered = (text + " " + str(path)).lower()
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


def infer_terminal(record: Dict[str, Any], path: Path) -> str:
    explicit = first(record, ["terminal", "platform", "app", "source_app", "终端", "平台", "应用"])
    text = (explicit or "") + " " + json.dumps(record, ensure_ascii=False) + " " + str(path)
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
    return {
        "schema": "pro_terminal.usage.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "activity_counts": dict(sorted(activity_counts.items())),
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "collection_readiness": {
            "status": "needs_pro_terminal_usage_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_terminal_usage": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "license_boundary": "workflow_metadata_only",
            "next_action": "Provide authorized Wind/Choice/iFinD/Bloomberg workflow export." if gap_only else "Use as investor workflow evidence; continue licensed platform validation.",
        },
    }


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
    return None


def list_values(record: Dict[str, Any], keys: Iterable[str]) -> List[str]:
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").replace("、", ",").split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item.get("name") if isinstance(item, dict) else item) for item in value if str(item)]
    return []


def symbols_for(record: Dict[str, Any]) -> List[str]:
    return list_values(record, ["symbols", "codes", "tickers", "securities", "证券", "代码", "股票"])


def sanitized(record: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in record.items():
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
            continue
        clean[key] = value
    return clean


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


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return path.stem


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
