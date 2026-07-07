"""Parse user-authorized Xueqiu watchlist exports."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, Iterator, List, Optional

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency for runtime installs
    openpyxl = None


COLLECTOR = "xueqiu-watchlist"
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
        return [gap_event(collected_at=collected_at, reason="xueqiu_watchlist_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for row, record in enumerate(parse_path(path), start=1):
            if not watchlist_symbol(record):
                continue
            events.append(record_to_event(record, path=path, row=row, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events or [gap_event(collected_at=collected_at, reason="xueqiu_watchlist_records_empty")]


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
    if suffix == ".zip":
        return parse_zip(path)
    return parse_text_watchlist(path)


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-xueqiu-watchlist-") as tmp:
        tmp_root = Path(tmp)
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(member_name)
            suffix = Path(member_name).suffix.lower()
            if not is_safe_archive_member(member_path) or suffix not in ARCHIVE_MEMBER_EXTENSIONS:
                continue
            target = tmp_root.joinpath(*member_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            for member_row, record in enumerate(parse_path(target), start=1):
                if isinstance(record, dict):
                    record["_collectorx_raw_ref"] = {
                        "path": f"{path}::{member_name}",
                        "archive": str(path),
                        "archive_member": member_name,
                        "member_row": member_row,
                    }
                records.append(record)
    return records


def is_safe_archive_member(member_path: PurePosixPath) -> bool:
    return bool(member_path.parts) and not member_path.is_absolute() and ".." not in member_path.parts


def parse_watchlist_csv(file_path: str) -> List[Dict[str, Any]]:
    """Backward-compatible parser used by the legacy CLI and old tests."""
    records = []
    for record in parse_path(Path(file_path)):
        symbol = normalize_symbol(watchlist_symbol(record) or "")
        if not symbol:
            continue
        records.append(
            {
                "source": "xueqiu",
                "code": symbol_code(symbol),
                "symbol": symbol,
                "market": normalize_market(symbol),
                "name": first(record, ["name", "stock_name", "security_name", "名称", "证券名称", "股票名称"]) or "",
                "industry": first(record, ["industry", "sector", "行业", "板块"]) or "",
                "note": first(record, ["note", "memo", "reason", "备注", "关注理由"]) or "",
            }
        )
    return records


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    lines = text.splitlines()
    if not looks_like_header(lines[0]):
        return parse_plain_lines(lines)
    return [{str(key): value for key, value in row.items() if key is not None} for row in csv.DictReader(lines, delimiter=delimiter)]


def looks_like_header(line: str) -> bool:
    normalized = normalize_key(line)
    return any(key in normalized for key in ("code", "symbol", "name", "股票代码", "证券代码", "代码", "名称"))


def parse_plain_lines(lines: Iterable[str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in lines:
        stripped = line.strip()
        symbol = first_symbol_in_text(stripped)
        if symbol:
            records.append({"code": symbol, "source_line": stripped})
    return records


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
    for key in ("watchlist", "watchlists", "stocks", "items", "records", "data", "list", "自选股", "关注列表"):
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


def parse_text_watchlist(path: Path) -> List[Dict[str, Any]]:
    text = strip_tags(path.read_text(encoding="utf-8", errors="replace"))
    records: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        symbol = first_symbol_in_text(line)
        if not symbol:
            continue
        name = line.replace(symbol, "").strip(" -_,，\t")
        records.append({"code": symbol, "name": name, "source_line": line})
    return records


def first_symbol_in_text(line: str) -> Optional[str]:
    match = re.search(
        r"(?<![A-Z0-9])((?:SH|SZ|BJ)\d{6}|(?:HK)\d{4,5}|\d{6}|\d{5}\.HK|\d{6}\.(?:SH|SZ|BJ))(?![A-Z0-9])",
        line,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    raw_symbol = watchlist_symbol(record) or ""
    symbol = normalize_symbol(raw_symbol)
    followed_at = first(record, ["followed_at", "added_at", "created_at", "time", "date", "加入时间", "关注时间", "日期"])
    group = first(record, ["group", "group_name", "folder", "watchlist", "分组", "自选分组"]) or first(record, ["sheet", "source_section"])
    data = {
        "symbol": symbol,
        "code": symbol_code(symbol),
        "market": normalize_market(first(record, ["market", "exchange", "市场", "交易所"]) or symbol),
        "name": first(record, ["name", "stock_name", "security_name", "名称", "证券名称", "股票名称"]),
        "group": group,
        "industry": first(record, ["industry", "sector", "行业", "板块"]),
        "note": first(record, ["note", "memo", "reason", "备注", "关注理由"]),
        "tags": list_values(record, ["tags", "labels", "标签"]),
        "followed_at": followed_at,
        "source_section": first(record, ["source_section", "sheet"]),
        "raw": sanitized(record),
        "broker_confirmed_trade": False,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {"path": str(path), "row": row, "symbol": symbol}
    if isinstance(record.get("_collectorx_raw_ref"), dict):
        raw_ref.update(record["_collectorx_raw_ref"])
        raw_ref["row"] = row
        raw_ref["symbol"] = symbol
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, symbol, group, followed_at),
        "collector": COLLECTOR,
        "source": "雪球关注列表用户授权导出",
        "owner_scope": "personal",
        "kind": "watchlist",
        "time": followed_at,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio"]},
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
        "source": "雪球关注列表授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "gap": reason,
            "message": "No user-authorized Xueqiu watchlist export was provided.",
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
        "schema": "collectorx.xueqiu_watchlist.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "market_counts": dict(sorted(market_counts.items())),
        "group_counts": dict(sorted(group_counts.items())),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "evidence_policy": {
            "xueqiu_watchlist_is_strong_trade_source": False,
            "broker_confirmed_trade_collection": False,
            "evidence_role": "attention_universe_only",
            "requires_corroboration_with": ["broker_trades", "portfolio_holdings", "research_documents", "investment_notes", "reviews"],
        },
        "collection_readiness": {
            "status": "needs_xueqiu_watchlist_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_complete_xueqiu_watchlist_boundary": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized Xueqiu watchlist export." if gap_only else "Use as attention-universe evidence; corroborate with Xueqiu activity and broker trades.",
        },
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
        "# Xueqiu Watchlist Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Xueqiu watchlists are attention-universe evidence, not broker-confirmed holdings or trades.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def watchlist_symbol(record: Dict[str, Any]) -> Optional[str]:
    stock = dict_child(record, "stock")
    return first(record, ["symbol", "code", "stock_symbol", "stockCode", "股票代码", "证券代码", "代码"]) or first(stock, ["symbol", "code"])


def dict_child(record: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


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
    text = text.strip("$")
    text = re.sub(r"\s+", "", text)
    suffix_match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", text)
    if suffix_match:
        return f"{suffix_match.group(2)}{suffix_match.group(1)}"
    hk_suffix = re.fullmatch(r"(\d{4,5})\.HK", text)
    if hk_suffix:
        return f"HK{hk_suffix.group(1).zfill(5)}"
    if re.fullmatch(r"(SH|SZ|BJ)\d{6}", text):
        return text
    if re.fullmatch(r"HK\d{4,5}", text):
        return "HK" + text[2:].zfill(5)
    if text.isdigit() and len(text) == 6:
        market = normalize_market(text)
        return f"{market}{text}" if market in {"SH", "SZ", "BJ"} else text
    if text.isdigit() and len(text) == 5 and text.startswith("0"):
        return f"HK{text}"
    return text


def symbol_code(symbol: str) -> str:
    text = str(symbol)
    if re.fullmatch(r"(SH|SZ|BJ)\d{6}", text):
        return text[2:]
    if re.fullmatch(r"HK\d{5}", text):
        return text[2:]
    return text


def normalize_market(value: Optional[str]) -> str:
    text = str(value or "").upper()
    if text.startswith("SH") or text.endswith(".SH") or "沪" in text:
        return "SH"
    if text.startswith("SZ") or text.endswith(".SZ") or "深" in text:
        return "SZ"
    if text.startswith("BJ") or text.endswith(".BJ") or "北" in text:
        return "BJ"
    if text.startswith("HK") or text.endswith(".HK") or "港" in text:
        return "HK"
    if text.isdigit() and len(text) == 6:
        if text.startswith(("6", "9")):
            return "SH"
        if text.startswith(("0", "2", "3")):
            return "SZ"
        if text.startswith(("4", "8")):
            return "BJ"
    if text.isdigit() and len(text) == 5 and text.startswith("0"):
        return "HK"
    return "unknown"


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).startswith("_collectorx_"):
                continue
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
