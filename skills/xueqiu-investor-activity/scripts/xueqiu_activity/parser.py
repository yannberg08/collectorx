"""Parse user-authorized Xueqiu exports into CollectorX events."""

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


COLLECTOR = "xueqiu-investor-activity"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".txt", ".html", ".htm", ".md", ".markdown"}
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
EXPECTED_ACTIVITY_TYPES = ("watchlist", "follow_user", "follow_portfolio", "portfolio_activity", "comment", "favorite", "post")


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="xueqiu_authorized_input_missing")]
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
    for key in (
        "activities",
        "statuses",
        "comments",
        "favorites",
        "follows",
        "followers",
        "friends",
        "watchlist",
        "stocks",
        "cubes",
        "portfolios",
        "rebalancing_histories",
        "items",
        "records",
        "list",
        "data",
    ):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_records(value)
            if not (len(nested) == 1 and nested[0] == value):
                return nested
    for value in loaded.values():
        if isinstance(value, list):
            return value
    return [loaded]


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [{str(k): v for k, v in row.items() if k is not None} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(html)
    return {
        "activity_type": "saved_page",
        "title": meta_content(html, "og:title") or title_tag(html) or infer_title(path, text),
        "author": meta_content(html, "author") or meta_content(html, "og:site_name"),
        "url": canonical_url(html) or first_url(html),
        "content": text,
        "path": str(path),
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "activity_type": "saved_page" if "xueqiu.com" in text.lower() else "post",
        "title": infer_title(path, text),
        "url": first_url(text),
        "content": text,
        "path": str(path),
    }


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    activity_type = infer_activity_type(record, path)
    kind = kind_for_activity(activity_type)
    stock = dict_child(record, "stock")
    user = dict_child(record, "user")
    cube = dict_child(record, "cube")
    symbol = normalize_symbol(
        first(record, ["symbol", "code", "stock_symbol", "stockCode", "股票代码", "证券代码"])
        or first(stock, ["symbol", "code"])
    )
    name = (
        first(record, ["name", "stock_name", "stockName", "股票名称", "证券名称", "title", "标题"])
        or first(stock, ["name", "stock_name"])
        or first(cube, ["name", "cube_name", "title"])
    )
    content = first(record, ["text", "content", "description", "正文", "内容", "评论", "comment", "note", "备注"]) or ""
    url = first(record, ["url", "link", "target_url", "链接"]) or build_xueqiu_url(record, user)
    event_time = first(
        record,
        [
            "time",
            "date",
            "created_at",
            "createdAt",
            "updated_at",
            "updatedAt",
            "created",
            "created_time",
            "日期",
            "时间",
        ],
    )
    data = {
        "activity_type": activity_type,
        "source_surface": infer_source_surface(record, path),
        "symbol": symbol,
        "symbols": symbols_for(record),
        "name": name,
        "group": first(record, ["group", "分组", "组合", "portfolio_name"]),
        "author": first(record, ["author", "screen_name", "用户名", "作者"]) or first(user, ["screen_name", "name"]),
        "author_id": first(record, ["user_id", "userid", "uid"]) or first(user, ["id", "uid", "user_id"]),
        "target_user": first(record, ["target_user", "target_screen_name", "followed_user", "被关注用户"]),
        "portfolio_symbol": first(record, ["cube_symbol", "portfolio_symbol", "组合代码"]) or first(cube, ["symbol"]),
        "portfolio_name": first(record, ["cube_name", "portfolio_name", "组合名称"]) or first(cube, ["name"]),
        "content_preview": preview(content),
        "url": url,
        "tags": tags_for(record),
        "metrics": metrics_for(record),
        "portfolio_changes": portfolio_changes_for(record),
        "raw": sanitized(record),
        "broker_confirmed_trade": False,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, activity_type, event_time, symbol, name, url, json.dumps(sanitized(record), ensure_ascii=False, sort_keys=True)),
        "collector": COLLECTOR,
        "source": "雪球用户授权投资活动",
        "owner_scope": "personal",
        "kind": kind,
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {"path": str(path), "row": row, "activity_type": activity_type, "source_surface": data.get("source_surface")},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio", "personal_message", "contact"]},
        "wiki_targets": wiki_targets_for_activity(activity_type),
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "雪球投资活动授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "activity_type": "collector_gap",
            "gap": reason,
            "message": "No user-authorized Xueqiu export or local input was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio"]},
        "wiki_targets": ["investor.data_quality.collection_gaps"],
    }


def infer_activity_type(record: Dict[str, Any], path: Optional[Path] = None) -> str:
    explicit = first(record, ["activity_type", "type", "kind", "action", "event", "类别", "类型", "动作"])
    text = json.dumps(sanitized(record), ensure_ascii=False).lower()
    if path is not None:
        text += " " + str(path).lower()
    if explicit:
        explicit_text = explicit.lower()
        if any(token in explicit_text for token in ["watch", "watchlist", "自选", "stock"]):
            return "watchlist"
        if any(token in explicit_text for token in ["follow_portfolio", "follow_cube", "关注组合"]):
            return "follow_portfolio"
        if any(token in explicit_text for token in ["follow_user", "user_follow", "关注用户", "follow"]):
            return "follow_user"
        if any(token in explicit_text for token in ["portfolio", "cube", "组合", "调仓", "rebalance"]):
            return "portfolio_activity"
        if any(token in explicit_text for token in ["comment", "评论", "reply"]):
            return "comment"
        if any(token in explicit_text for token in ["favorite", "fav", "收藏", "like"]):
            return "favorite"
        if any(token in explicit_text for token in ["saved_page", "保存页面"]):
            return "saved_page"
        if any(token in explicit_text for token in ["post", "status", "发帖"]):
            return "post"
    if any(key in record for key in ["rebalancing_histories", "cube_symbol", "cube_name", "portfolio_symbol", "组合代码"]):
        return "portfolio_activity"
    if any(key in record for key in ["comment_id", "reply_comment_id", "评论"]) or "评论" in text or "comment" in text:
        return "comment"
    if "调仓" in text or "组合" in text or "rebalance" in text or "portfolio" in text or "cube" in text:
        return "portfolio_activity"
    if "收藏" in text or "favorite" in text or '"fav' in text:
        return "favorite"
    if "关注组合" in text:
        return "follow_portfolio"
    if "关注用户" in text or "follow_user" in text:
        return "follow_user"
    if any(key in record for key in ["code", "symbol", "stock_symbol", "stockCode", "股票代码", "证券代码"]):
        return "watchlist"
    if first_url(text) and "xueqiu.com" in text:
        return "saved_page"
    return "post"


def infer_source_surface(record: Dict[str, Any], path: Path) -> str:
    text = json.dumps(sanitized(record), ensure_ascii=False).lower() + " " + str(path).lower()
    if "cube" in text or "组合" in text or "portfolio" in text:
        return "portfolio"
    if "comment" in text or "评论" in text:
        return "comment"
    if "favorite" in text or "收藏" in text:
        return "favorite"
    if "watchlist" in text or "自选" in text or "stock" in text:
        return "watchlist"
    if "follow" in text or "关注" in text:
        return "follow"
    if "status" in text or "timeline" in text:
        return "status"
    if path.suffix.lower() in {".html", ".htm"}:
        return "saved_page"
    return "unknown"


def kind_for_activity(activity_type: str) -> str:
    if activity_type == "watchlist":
        return "watchlist"
    if activity_type in {"follow_user", "follow_portfolio"}:
        return "profile"
    if activity_type == "portfolio_activity":
        return "holding"
    if activity_type == "comment":
        return "message"
    if activity_type in {"favorite", "post", "saved_page"}:
        return "note"
    return "other"


def wiki_targets_for_activity(activity_type: str) -> List[str]:
    targets = {
        "watchlist": ["investor.opportunity_watchlist.watchlist", "investor.capability_circle.attention_universe"],
        "follow_user": ["investor.network_collaboration.discussions", "investor.information_sources.news_consumption"],
        "follow_portfolio": ["investor.information_sources.news_consumption", "investor.risk_portfolio.portfolio_constraints"],
        "portfolio_activity": ["investor.decision_framework.strategy_rules", "investor.risk_portfolio.portfolio_constraints"],
        "comment": ["investor.network_collaboration.discussions", "investor.behavior.emotion_pattern"],
        "favorite": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "saved_page": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "post": ["investor.record_review.review_record", "investor.decision_framework.strategy_rules"],
    }
    return targets.get(activity_type, ["investor.data_quality.collection_gaps"])


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    counts = Counter(event["kind"] for event in events)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in events)
    surface_counts = Counter((event.get("data") or {}).get("source_surface", "unknown") for event in events)
    gap_only = bool(events) and set(activity_counts) == {"collector_gap"}
    observed = sorted(activity for activity in activity_counts if activity != "collector_gap")
    missing = [activity for activity in EXPECTED_ACTIVITY_TYPES if activity not in activity_counts]
    return {
        "schema": "xueqiu.investor_activity.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "source_file_count": len({(event.get("raw_ref") or {}).get("path") for event in events if (event.get("raw_ref") or {}).get("path")}),
        "kind_counts": dict(sorted(counts.items())),
        "activity_counts": dict(sorted(activity_counts.items())),
        "surface_counts": dict(sorted(surface_counts.items())),
        "observed_activity_types": observed,
        "missing_expected_activity_types": missing,
        "collection_readiness": {
            "status": "needs_xueqiu_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events),
            "can_claim_broker_trade_collection": False,
            "can_claim_complete_xueqiu_activity_boundary": False,
            "activity_boundary_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "提供雪球个人活动导出或授权输入后重跑。" if gap_only else "可进入投资分身蒸馏；后续补真实账号分页/关注/收藏/组合覆盖验证。",
        },
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in events)
    for event in events:
        for target in event.get("wiki_targets", []):
            by_target[target].append(event)
    return {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": len(events),
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
        },
        "coverage_summary": {
            "xueqiu_is_strong_trade_source": False,
            "activity_counts": dict(sorted(activity_counts.items())),
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
            "evidence_role": "attention_network_opinion_and_model_portfolio_only",
        },
    }


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def dict_child(record: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def preview(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return str(value)[:1200]


def number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def normalize_symbol(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    symbol = str(value).strip().upper()
    if re.fullmatch(r"\d{6}", symbol):
        if symbol.startswith(("6", "9")):
            return f"SH{symbol}"
        if symbol.startswith(("0", "2", "3")):
            return f"SZ{symbol}"
        if symbol.startswith(("4", "8")):
            return f"BJ{symbol}"
    return symbol


def symbols_for(record: Dict[str, Any]) -> List[str]:
    symbols: List[str] = []
    for key in ("symbol", "code", "stock_symbol", "stockCode", "股票代码", "证券代码"):
        value = normalize_symbol(first(record, [key]))
        if value:
            symbols.append(value)
    stock = dict_child(record, "stock")
    for key in ("symbol", "code"):
        value = normalize_symbol(first(stock, [key]))
        if value:
            symbols.append(value)
    text = json.dumps(sanitized(record), ensure_ascii=False)
    for match in re.finditer(r"\$[^$()]{1,40}\(((?:SH|SZ|BJ|HK|US)?[A-Z0-9.]{2,12})\)\$", text, flags=re.IGNORECASE):
        symbols.append(normalize_symbol(match.group(1)) or match.group(1).upper())
    for match in re.finditer(r"\b(?:SH|SZ|BJ)\d{6}\b|\bHK\d{5}\b|(?<!\d)[6038]\d{5}(?!\d)", text, flags=re.IGNORECASE):
        value = normalize_symbol(match.group(0))
        if value:
            symbols.append(value)
    return sorted(set(symbols))


def tags_for(record: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for key in ("tags", "tag", "topics", "topic", "行业", "标签", "话题"):
        value = record.get(key)
        if isinstance(value, list):
            tags.extend(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            tags.extend(part.strip() for part in re.split(r"[,，;；\s]+", str(value)) if part.strip())
    return sorted(set(tags))


def metrics_for(record: Dict[str, Any]) -> Dict[str, float]:
    metrics = {
        "comment_count": number(first(record, ["comment_count", "comments_count", "reply_count", "评论数"])),
        "like_count": number(first(record, ["like_count", "liked_count", "赞数", "点赞数"])),
        "favorite_count": number(first(record, ["favorite_count", "fav_count", "收藏数"])),
        "retweet_count": number(first(record, ["retweet_count", "share_count", "转发数"])),
    }
    return {key: value for key, value in metrics.items() if value is not None}


def portfolio_changes_for(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = record.get("rebalancing_histories") or record.get("holdings") or record.get("positions") or record.get("changes")
    if not isinstance(candidates, list):
        return []
    changes: List[Dict[str, Any]] = []
    for item in candidates[:50]:
        if not isinstance(item, dict):
            continue
        stock = dict_child(item, "stock")
        changes.append(
            {
                "symbol": normalize_symbol(first(item, ["stock_symbol", "symbol", "code"]) or first(stock, ["symbol", "code"])),
                "name": first(item, ["stock_name", "name"]) or first(stock, ["name"]),
                "prev_weight": number(first(item, ["prev_weight", "prevWeight", "old_weight", "原仓位"])),
                "target_weight": number(first(item, ["target_weight", "targetWeight", "weight", "目标仓位"])),
                "price": number(first(item, ["price", "成交价", "价格"])),
                "updated_at": first(item, ["updated_at", "created_at", "time", "date"]),
            }
        )
    return [{key: value for key, value in change.items() if value not in (None, "", [], {})} for change in changes]


def build_xueqiu_url(record: Dict[str, Any], user: Dict[str, Any]) -> Optional[str]:
    status_id = first(record, ["id", "status_id"])
    user_id = first(record, ["user_id", "uid"]) or first(user, ["id", "uid"])
    if status_id and user_id:
        return f"https://xueqiu.com/{user_id}/{status_id}"
    return None


def sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            cleaned[str(key)] = sanitized(item)
        return cleaned
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:2000]
    return value


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def meta_content(html: str, name: str) -> Optional[str]:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return unescape(match.group(1)).strip()
    return None


def title_tag(html: str) -> Optional[str]:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not match:
        return None
    return html_to_text(match.group(1))[:200]


def canonical_url(html: str) -> Optional[str]:
    match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if match:
        return unescape(match.group(1)).strip()
    return None


def first_url(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return match.group(0) if match else None


def infer_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return path.stem


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
