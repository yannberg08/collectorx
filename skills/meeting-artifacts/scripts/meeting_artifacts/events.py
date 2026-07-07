"""Build CollectorX events for meeting artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COLLECTOR = "meeting-artifacts"
CN_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def artifact_to_event(record: Dict[str, Any], *, path: Path, collected_at: Optional[str] = None) -> Dict[str, Any]:
    title = first(record, ["title", "meeting_title", "name", "topic", "标题", "会议主题"]) or path.stem
    text = first(record, ["text", "content", "transcript", "summary", "minutes", "正文", "内容", "纪要", "逐字稿"]) or ""
    participants = participants_for(record)
    platform = first(record, ["platform", "source_app", "provider", "来源", "平台"]) or infer_platform(path)
    start_time = first(record, ["start_time", "started_at", "time", "date", "meeting_time", "开始时间", "日期"])
    artifact_type = first(record, ["artifact_type", "type", "kind", "类型"]) or infer_artifact_type(path)
    data = {
        "artifact_type": artifact_type,
        "platform": platform,
        "title": title,
        "participants": participants,
        "text_preview": text[:2000],
        "has_text": bool(text),
        "duration": first(record, ["duration", "时长"]),
        "attachment_refs": attachment_refs_for(record),
        "raw": record,
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path, title, start_time, text[:160]),
        "collector": COLLECTOR,
        "source": "用户授权会议产物",
        "owner_scope": "personal",
        "kind": "note",
        "time": start_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": {
            "path": str(path),
            "artifact_type": artifact_type,
            "platform": platform,
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message", "contact", "work_confidential"],
        },
        "wiki_targets": ["internal.collaboration.meetings"],
    }


def gap_event(*, collected_at: Optional[str], reason: str) -> Dict[str, Any]:
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "会议产物授权状态",
        "owner_scope": "personal",
        "kind": "other",
        "time": None,
        "collected_at": collected_at or now_iso(),
        "data": {
            "gap": reason,
            "message": "No user-authorized meeting artifact file or folder was provided.",
        },
        "raw_ref": {"preflight": True},
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["work_confidential"],
        },
        "wiki_targets": ["collectorx.data_quality.collection_gaps"],
    }


def build_manifest(events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    type_counts = Counter((event.get("data") or {}).get("artifact_type", "unknown") for event in events)
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    return {
        "schema": "collectorx.meeting_artifacts.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "artifact_type_counts": dict(sorted(type_counts.items())),
        "collection_readiness": {
            "status": "needs_meeting_artifact_input" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "can_claim_investment_meeting_minutes": False,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "next_action": "Provide authorized meeting minutes/transcript files." if gap_only else "Feed events into meeting-minutes lens.",
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
        "# Meeting Artifacts Collector Package",
        "",
        f"- collector: `{COLLECTOR}`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Generic meeting artifacts are not written to the investor Wiki directly. Use the meeting-minutes lens.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def participants_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("participants") or record.get("attendees") or record.get("参会人") or []
    if isinstance(raw, str):
        return [item.strip() for item in raw.replace("，", ",").replace("、", ",").split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item.get("name") if isinstance(item, dict) else item) for item in raw if str(item)]
    return []


def attachment_refs_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("attachments") or record.get("attachment_refs") or record.get("附件") or []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item.get("path") if isinstance(item, dict) else item) for item in raw if str(item)]
    return []


def infer_platform(path: Path) -> str:
    body = str(path).lower()
    if "feishu" in body or "lark" in body or "飞书" in body:
        return "feishu"
    if "dingtalk" in body or "钉钉" in body:
        return "dingtalk"
    if "wecom" in body or "企业微信" in body:
        return "wecom"
    if "tencent" in body or "腾讯会议" in body:
        return "tencent-meeting"
    return "local-file"


def infer_artifact_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".vtt", ".srt"}:
        return "transcript"
    return "minutes"


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
