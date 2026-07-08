"""Parse user-authorized Tonghuashun watchlist exports."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
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
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xlsx", ".xlsm", ".html", ".htm", ".txt", ".md", ".markdown"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
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


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="ths_watchlist_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            if not first(record, ["symbol", "code", "stock_code", "证券代码", "代码"]):
                continue
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events or [gap_event(collected_at=collected_at, reason="ths_watchlist_records_empty")]


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
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path)
    return parse_text_codes(path)


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
    symbol = normalize_symbol(first(record, ["symbol", "code", "stock_code", "证券代码", "代码"]) or "")
    name = first(record, ["name", "stock_name", "security_name", "证券名称", "名称"]) or ""
    group = first(record, ["group", "group_name", "folder", "watchlist", "分组", "自选分组"]) or first(record, ["sheet"])
    added_at = first(record, ["added_at", "created_at", "time", "date", "加入时间", "添加时间", "日期"])
    data = {
        "symbol": symbol,
        "name": name,
        "market": normalize_market(first(record, ["market", "exchange", "市场", "交易所"]) or symbol),
        "group": group,
        "reason": first(record, ["reason", "note", "memo", "备注", "关注理由"]),
        "industry": first(record, ["industry", "sector", "行业", "板块"]),
        "tags": list_values(record, ["tags", "labels", "标签"]),
        "added_at": added_at,
        "source_section": first(record, ["source_section", "sheet"]),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, symbol, group, added_at),
        "collector": COLLECTOR,
        "source": "同花顺自选股用户授权导出",
        "owner_scope": "personal",
        "kind": "watchlist",
        "time": added_at,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "row": row,
            "symbol": symbol,
        },
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


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "同花顺自选股授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "gap": reason,
            "message": "No user-authorized Tonghuashun watchlist export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    market_counts = Counter((event.get("data") or {}).get("market", "unknown") for event in events if event["kind"] == "watchlist")
    group_counts = Counter((event.get("data") or {}).get("group", "unknown") for event in events if event["kind"] == "watchlist")
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    return {
        "schema": "collectorx.ths_watchlist.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "market_counts": dict(sorted(market_counts.items())),
        "group_counts": dict(sorted(group_counts.items())),
        "collection_readiness": {
            "status": "needs_ths_watchlist_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_ths_attention_universe": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized Tonghuashun watchlist export." if gap_only else "Use as attention-universe evidence; corroborate with trades and research.",
        },
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
