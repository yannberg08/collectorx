"""
qq.events — Convert normalized QQ messages to CollectorX events.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COLLECTOR_ID = "qq"
DEFAULT_SOURCE = "QQ 本地聊天记录"
CN_TZ = timezone(timedelta(hours=8))


def messages_to_events(
    messages: Iterable[Dict[str, Any]],
    *,
    source: str = DEFAULT_SOURCE,
    raw_file: Optional[str] = None,
    collected_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return [
        message_to_event(
            message,
            source=source,
            raw_file=raw_file,
            collected_at=collected_at,
        )
        for message in messages
    ]


def message_to_event(
    message: Dict[str, Any],
    *,
    source: str = DEFAULT_SOURCE,
    raw_file: Optional[str] = None,
    collected_at: Optional[str] = None,
) -> Dict[str, Any]:
    collected = collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds")
    raw_ref: Dict[str, Any] = {
        "chat_id": message.get("chat_id") or message.get("chat"),
        "message_id": message.get("message_id"),
    }
    if raw_file:
        raw_ref["file"] = str(Path(raw_file))

    return {
        "schema": "collectorx.event.v1",
        "id": _stable_event_id(message),
        "collector": COLLECTOR_ID,
        "source": source,
        "owner_scope": "personal",
        "kind": "message",
        "time": message.get("time"),
        "collected_at": collected,
        "data": {
            "chat": message.get("chat", ""),
            "sender": message.get("sender", ""),
            "sender_is_owner": bool(message.get("sender_is_owner")),
            "text": message.get("text", ""),
            "message_type": message.get("message_type", "text"),
        },
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message", "contact"],
        },
        "wiki_targets": [
            "external.relationships.conversations",
            "external.relationships.contacts",
            "internal.knowledge.information_sources",
            "investor.network_collaboration.discussions",
        ],
    }


def write_events_jsonl(path: str, events: Iterable[Dict[str, Any]]) -> None:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _stable_event_id(message: Dict[str, Any]) -> str:
    body = "|".join(
        [
            COLLECTOR_ID,
            str(message.get("chat_id") or message.get("chat") or ""),
            str(message.get("message_id") or ""),
            str(message.get("time") or ""),
            str(message.get("sender") or ""),
            str(message.get("text") or ""),
        ]
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR_ID}:{digest}"
