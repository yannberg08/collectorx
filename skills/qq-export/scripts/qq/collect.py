"""
qq.collect — WeChat-style QQ collection filtering and payload formatting.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set


def split_csv(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def is_noise_for_owner_relevance(message: Dict[str, Any]) -> bool:
    content = str(message.get("text") or "").strip()
    if not content:
        return True
    if content.startswith("<"):
        return True
    if "撤回了一条消息" in content:
        return True
    return False


def detect_active_groups(messages: Iterable[Dict[str, Any]], all_groups: Set[str]) -> Set[str]:
    active = set()
    for message in messages:
        chat = message.get("chat") or ""
        if chat not in all_groups:
            continue
        if message.get("is_received"):
            continue
        if is_noise_for_owner_relevance(message):
            continue
        active.add(chat)
    return active


def detect_active_private(messages: Iterable[Dict[str, Any]], all_groups: Set[str]) -> Set[str]:
    active = set()
    for message in messages:
        chat = message.get("chat") or ""
        if not chat or chat in all_groups:
            continue
        if message.get("is_received"):
            continue
        if is_noise_for_owner_relevance(message):
            continue
        active.add(chat)
    return active


def filter_owner_relevant_messages(
    messages: Iterable[Dict[str, Any]],
    all_groups: Set[str],
    *,
    exclude_set: Optional[Set[str]] = None,
    group_whitelist: Optional[Set[str]] = None,
    private_whitelist: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    exclude_set = exclude_set or set()
    group_whitelist = group_whitelist or set()
    kept = []
    for message in messages:
        chat = message.get("chat") or ""
        if chat in exclude_set:
            continue
        if chat in all_groups:
            if chat not in group_whitelist:
                continue
        elif private_whitelist is not None and chat not in private_whitelist:
            continue
        kept.append(message)
    return kept


def collect_records(
    messages: List[Dict[str, Any]],
    *,
    after_ts: Optional[float] = None,
    limit: int = 0,
    exclude: Optional[str] = None,
    include_groups: Optional[str] = None,
    active_group_days: Optional[int] = 30,
    participated_only: bool = False,
) -> List[Dict[str, Any]]:
    messages = sorted(messages, key=lambda item: item.get("time_ts") or 0)
    all_groups = {message.get("chat") or "" for message in messages if message.get("is_group")}
    exclude_set = split_csv(exclude)
    include_group_set = split_csv(include_groups)

    active_groups = set()
    if active_group_days and active_group_days > 0:
        latest_ts = max((message.get("time_ts") or 0 for message in messages), default=0)
        cutoff = latest_ts - active_group_days * 86400
        active_candidates = [m for m in messages if (m.get("time_ts") or 0) >= cutoff]
        active_groups = detect_active_groups(active_candidates, all_groups)

    group_whitelist = (include_group_set | active_groups) - exclude_set
    private_whitelist = None
    if participated_only:
        private_whitelist = detect_active_private(messages, all_groups) - exclude_set

    filtered = filter_owner_relevant_messages(
        messages,
        all_groups,
        exclude_set=exclude_set,
        group_whitelist=group_whitelist,
        private_whitelist=private_whitelist,
    )

    out: List[Dict[str, Any]] = []
    for message in filtered:
        ts = message.get("time_ts") or 0
        if after_ts and ts < after_ts:
            continue
        content = str(message.get("text") or "").strip()
        if is_noise_for_owner_relevance(message):
            continue
        chat = message.get("chat") or ""
        time_text = _format_time(message)
        sender = "我" if not message.get("is_received") else (message.get("sender") or chat)
        record_id = _stable_collect_id(chat, time_text, sender, content)
        out.append(
            {
                "id": f"qq-{record_id}",
                "source": format_collect_source(chat, bool(message.get("is_group")), time_text),
                "data": {
                    "chat": chat,
                    "sender": sender,
                    "time": time_text,
                    "text": content,
                },
            }
        )
        if limit and len(out) >= limit:
            break
    return out


def dump_collect_payload(records: List[Dict[str, Any]], *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(records, ensure_ascii=False, indent=2)
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def collect_records_to_messages(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    messages = []
    for record in records:
        data = record.get("data") or {}
        messages.append(
            {
                "chat": data.get("chat", ""),
                "chat_id": data.get("chat", ""),
                "sender": data.get("sender", ""),
                "sender_is_owner": data.get("sender") == "我",
                "text": data.get("text", ""),
                "message_type": "text",
                "time": data.get("time"),
                "message_id": record.get("id", ""),
            }
        )
    return messages


def format_collect_source(chat: str, is_group: bool, time_text: str) -> str:
    date = (time_text or "")[:10]
    chat = chat or "(unknown)"
    if is_group:
        return f"QQ群「{chat}」· {date} 的聊天" if date else f"QQ群「{chat}」的聊天"
    return f"跟{chat}在 {date} 的QQ聊天" if date else f"跟{chat}的QQ聊天"


def _format_time(message: Dict[str, Any]) -> str:
    value = message.get("time")
    if value:
        return str(value).replace("T", " ")[:19]
    ts = message.get("time_ts")
    if ts:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _stable_collect_id(chat: str, time_text: str, sender: str, content: str) -> str:
    body = f"{chat}|{time_text}|{sender}|{content}"
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]
