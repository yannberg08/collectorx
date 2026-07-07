"""Build CollectorX events for WeChat favorites and public-account articles."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COLLECTOR = "wechat-favorites"
CN_TZ = timezone(timedelta(hours=8))
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "key")


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def favorite_to_event(
    record: Dict[str, Any],
    *,
    path: Path,
    row: int,
    collected_at: Optional[str] = None,
) -> Dict[str, Any]:
    title = first(record, ["title", "name", "subject", "标题", "文章标题"]) or path.stem
    url = first(record, ["url", "link", "href", "article_url", "原文链接", "链接"])
    account = first(record, ["source_account", "account", "author", "publisher", "公众号", "作者", "来源"])
    action_type = normalize_action(first(record, ["action_type", "action", "event", "type", "动作", "行为"]) or infer_action(record, path))
    item_type = first(record, ["item_type", "content_type", "kind", "类型"]) or infer_item_type(record, path)
    action_time = first(record, ["saved_at", "favorited_at", "read_at", "shared_at", "time", "date", "created_at", "收藏时间", "阅读时间", "转发时间", "时间"])
    text = first(record, ["text", "content", "body", "summary", "abstract", "note", "正文", "内容", "摘要", "备注"]) or ""
    tags = tags_for(record)
    data = {
        "item_type": item_type,
        "action_type": action_type,
        "title": title,
        "source_account": account,
        "url": url,
        "action_time": action_time,
        "tags": tags,
        "text_preview": text[:2000],
        "has_text": bool(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, row, title, url, action_time, action_type),
        "collector": COLLECTOR,
        "source": "微信收藏/公众号文章",
        "owner_scope": "personal",
        "kind": "file",
        "time": action_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "row": row,
            "url": url,
            "source_account": account,
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message"],
        },
        "wiki_targets": ["internal.knowledge.saved_articles"],
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "微信收藏授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "gap": reason,
            "message": "No user-authorized WeChat favorites or public-account article export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message"],
        },
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    action_counts = Counter((event.get("data") or {}).get("action_type", "unknown") for event in events)
    item_counts = Counter((event.get("data") or {}).get("item_type", "unknown") for event in events)
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    return {
        "schema": "collectorx.wechat_favorites.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "action_type_counts": dict(sorted(action_counts.items())),
        "item_type_counts": dict(sorted(item_counts.items())),
        "collection_readiness": {
            "status": "needs_wechat_favorites_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_article_favorites": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized WeChat favorites or public-account article exports." if gap_only else "Feed events into wechat-article-favorites lens.",
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
        "# WeChat Favorites Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Generic WeChat favorite/article events are not written to the investor Wiki directly. Use the wechat-article-favorites lens.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def tags_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("tags") or record.get("labels") or record.get("标签") or []
    if isinstance(raw, str):
        return [item.strip() for item in raw.replace("，", ",").replace("、", ",").split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item.get("name") if isinstance(item, dict) else item) for item in raw if str(item)]
    return []


def infer_action(record: Dict[str, Any], path: Path) -> str:
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path).lower()
    if "转发" in text or "share" in text:
        return "share"
    if "阅读" in text or "read" in text:
        return "read"
    if "保存" in text or "saved_file" in text or path.suffix.lower() in {".html", ".htm", ".md", ".markdown", ".txt"}:
        return "saved_file"
    return "favorite"


def normalize_action(value: str) -> str:
    text = value.strip().lower()
    if any(token in text for token in ("share", "forward", "转发", "分享")):
        return "share"
    if any(token in text for token in ("read", "阅读", "浏览")):
        return "read"
    if any(token in text for token in ("save", "保存", "file")):
        return "saved_file"
    if any(token in text for token in ("favorite", "fav", "收藏")):
        return "favorite"
    return text or "favorite"


def infer_item_type(record: Dict[str, Any], path: Path) -> str:
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path).lower()
    if "公众号" in text or "mp.weixin.qq.com" in text or "public_account" in text:
        return "public_account_article"
    if "http" in text or path.suffix.lower() in {".html", ".htm"}:
        return "article"
    return "favorite_item"


def sanitized(record: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in record.items():
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
            continue
        clean[key] = value
    return clean


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
