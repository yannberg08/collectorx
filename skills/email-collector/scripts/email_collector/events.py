"""
email_collector.events — Convert collected emails to CollectorX events.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COLLECTOR_ID = "email"
DEFAULT_SOURCE = "IMAP 邮件"
CN_TZ = timezone(timedelta(hours=8))


def emails_to_events(
    emails: Iterable[Dict[str, Any]],
    *,
    source: str = DEFAULT_SOURCE,
    account: Optional[str] = None,
    folder: Optional[str] = None,
    collected_at: Optional[str] = None,
    include_body: bool = False,
) -> List[Dict[str, Any]]:
    return [
        email_to_event(
            item,
            source=source,
            account=account,
            folder=folder,
            collected_at=collected_at,
            include_body=include_body,
        )
        for item in emails
    ]


def email_to_event(
    item: Dict[str, Any],
    *,
    source: str = DEFAULT_SOURCE,
    account: Optional[str] = None,
    folder: Optional[str] = None,
    collected_at: Optional[str] = None,
    include_body: bool = False,
) -> Dict[str, Any]:
    collected = collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds")
    body = str(item.get("body") or "")
    data = {
        "mailbox": account or item.get("mailbox") or "",
        "folder": folder or item.get("folder") or "",
        "from": item.get("from", ""),
        "to": item.get("to", ""),
        "cc": item.get("cc", ""),
        "subject": item.get("subject", ""),
        "body_preview": body[:300],
        "has_body": bool(body),
    }
    if include_body:
        data["body"] = body

    return {
        "schema": "collectorx.event.v1",
        "id": _stable_event_id(item, account=account, folder=folder),
        "collector": COLLECTOR_ID,
        "source": source,
        "owner_scope": "personal",
        "kind": "email",
        "time": item.get("date"),
        "collected_at": collected,
        "data": data,
        "raw_ref": {
            "imap_uid": item.get("id") or item.get("uid"),
            "message_id": item.get("message_id"),
            "folder": folder or item.get("folder"),
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["email", "contact", "personal_message"],
        },
        "wiki_targets": [
            "external.relationships.contacts",
            "external.experience.project_correspondence",
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


def _stable_event_id(item: Dict[str, Any], *, account: Optional[str], folder: Optional[str]) -> str:
    body = "|".join(
        [
            COLLECTOR_ID,
            str(account or item.get("mailbox") or ""),
            str(folder or item.get("folder") or ""),
            str(item.get("id") or item.get("uid") or ""),
            str(item.get("message_id") or ""),
            str(item.get("date") or ""),
            str(item.get("from") or ""),
            str(item.get("subject") or ""),
        ]
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR_ID}:{digest}"
