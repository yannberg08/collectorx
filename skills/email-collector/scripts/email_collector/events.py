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
    attachments = item.get("attachment_refs") or item.get("attachments") or []
    if attachments:
        data["attachment_refs"] = attachments
        data["has_attachments"] = True
    if include_body:
        data["body"] = body
    raw_ref = {
        "imap_uid": item.get("id") or item.get("uid"),
        "message_id": item.get("message_id"),
        "folder": folder or item.get("folder"),
    }
    if isinstance(item.get("raw_ref"), dict):
        raw_ref.update(item["raw_ref"])

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
        "raw_ref": raw_ref,
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


def write_json(path: str, payload: Any) -> None:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def gap_event(*, collected_at: Optional[str] = None, reason: str = "email_authorized_input_missing") -> Dict[str, Any]:
    collected = collected_at or datetime.now(CN_TZ).isoformat(timespec="seconds")
    return {
        "schema": "collectorx.event.v1",
        "id": f"{COLLECTOR_ID}:gap:{reason}",
        "collector": COLLECTOR_ID,
        "source": "邮箱授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected,
        "data": {
            "gap": reason,
            "message": "No user-authorized mailbox account or local email export was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["email"]},
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


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
            str((item.get("raw_ref") or {}).get("path") or ""),
            str((item.get("raw_ref") or {}).get("row") or ""),
        ]
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR_ID}:{digest}"
