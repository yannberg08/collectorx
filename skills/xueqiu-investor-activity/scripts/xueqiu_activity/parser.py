"""Parse user-authorized Xueqiu exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


COLLECTOR = "xueqiu-investor-activity"
CN_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(inputs: Iterable[str], *, collected_at: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    paths = list(iter_paths(inputs))
    if not paths:
        return [gap_event(collected_at=collected_at, reason="xueqiu_authorized_input_missing")]
    events: List[Dict[str, Any]] = []
    for path in paths:
        for record in parse_path(path):
            events.append(record_to_event(record, path=path, collected_at=collected_at))
            if limit is not None and len(events) >= limit:
                return events[:limit]
    return events


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in {".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".txt", ".html", ".htm"}:
                    yield child
        elif path.is_file():
            yield path


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_csv(path)
    return parse_text(path)


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        loaded = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        obj = json.loads(text)
        if isinstance(obj, list):
            loaded = obj
        elif isinstance(obj, dict):
            for key in ("activities", "items", "records", "data", "statuses", "watchlist", "stocks"):
                if isinstance(obj.get(key), list):
                    loaded = obj[key]
                    break
            else:
                loaded = [obj]
        else:
            loaded = [{"value": obj}]
    return [item if isinstance(item, dict) else {"value": item} for item in loaded]


def parse_csv(path: Path) -> List[Dict[str, Any]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    return [{str(k): v for k, v in row.items() if k is not None} for row in reader]


def parse_text(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [{"activity_type": "saved_page", "title": path.stem, "content_preview": text[:1200], "path": str(path)}]


def record_to_event(record: Dict[str, Any], *, path: Path, collected_at: Optional[str]) -> Dict[str, Any]:
    activity_type = infer_activity_type(record)
    kind = kind_for_activity(activity_type)
    data = {
        "activity_type": activity_type,
        "symbol": first(record, ["symbol", "code", "股票代码", "证券代码"]),
        "name": first(record, ["name", "stock_name", "股票名称", "证券名称", "title", "标题"]),
        "group": first(record, ["group", "分组", "组合", "portfolio_name"]),
        "author": first(record, ["author", "screen_name", "user", "用户名", "作者"]),
        "content_preview": preview(first(record, ["text", "content", "description", "正文", "内容", "评论", "note", "备注"])),
        "url": first(record, ["url", "link", "链接"]),
        "raw": record,
        "broker_confirmed_trade": False,
    }
    data = {key: value for key, value in data.items() if value not in (None, "")}
    event_time = first(record, ["time", "date", "created_at", "updated_at", "created", "日期", "时间"])
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, json.dumps(record, ensure_ascii=False, sort_keys=True)),
        "collector": COLLECTOR,
        "source": "雪球用户授权投资活动",
        "owner_scope": "personal",
        "kind": kind,
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {"path": str(path), "activity_type": activity_type},
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


def infer_activity_type(record: Dict[str, Any]) -> str:
    text = " ".join(str(value).lower() for value in record.values() if value is not None)
    explicit = first(record, ["activity_type", "type", "kind", "action", "类别", "类型", "动作"])
    if explicit:
        explicit_text = explicit.lower()
        if any(token in explicit_text for token in ["watch", "自选", "stock"]):
            return "watchlist"
        if any(token in explicit_text for token in ["follow_user", "关注用户", "user"]):
            return "follow_user"
        if any(token in explicit_text for token in ["portfolio", "组合", "调仓", "rebalance"]):
            return "portfolio_activity"
        if any(token in explicit_text for token in ["comment", "评论", "reply"]):
            return "comment"
        if any(token in explicit_text for token in ["favorite", "收藏", "like"]):
            return "favorite"
        if any(token in explicit_text for token in ["post", "status", "发帖"]):
            return "post"
    if any(key in record for key in ["code", "symbol", "股票代码", "证券代码"]):
        return "watchlist"
    if "调仓" in text or "组合" in text or "portfolio" in text:
        return "portfolio_activity"
    if "评论" in text or "comment" in text:
        return "comment"
    if "收藏" in text or "favorite" in text:
        return "favorite"
    return "post"


def kind_for_activity(activity_type: str) -> str:
    if activity_type == "watchlist":
        return "watchlist"
    if activity_type == "follow_user":
        return "profile"
    if activity_type == "portfolio_activity":
        return "holding"
    if activity_type == "comment":
        return "message"
    if activity_type in {"favorite", "post"}:
        return "note"
    return "other"


def wiki_targets_for_activity(activity_type: str) -> List[str]:
    targets = {
        "watchlist": ["investor.opportunity_watchlist.watchlist", "investor.capability_circle.attention_universe"],
        "follow_user": ["investor.network_collaboration.discussions", "investor.information_sources.news_consumption"],
        "portfolio_activity": ["investor.decision_framework.strategy_rules", "investor.risk_portfolio.portfolio_constraints"],
        "comment": ["investor.network_collaboration.discussions", "investor.behavior.emotion_pattern"],
        "favorite": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "post": ["investor.record_review.review_record", "investor.decision_framework.strategy_rules"],
    }
    return targets.get(activity_type, ["investor.data_quality.collection_gaps"])


def build_manifest(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(event["kind"] for event in events)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in events)
    gap_only = bool(events) and set(activity_counts) == {"collector_gap"}
    return {
        "schema": "xueqiu.investor_activity.manifest.v1",
        "collector": COLLECTOR,
        "event_count": len(events),
        "kind_counts": dict(sorted(counts.items())),
        "activity_counts": dict(sorted(activity_counts.items())),
        "collection_readiness": {
            "status": "needs_xueqiu_authorized_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events),
            "can_claim_broker_trade_collection": False,
            "next_action": "提供雪球个人活动导出或授权输入后重跑。" if gap_only else "可进入投资分身蒸馏；后续补真实登录适配和增量验证。",
        },
    }


def build_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
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
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def preview(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return str(value)[:500]


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
