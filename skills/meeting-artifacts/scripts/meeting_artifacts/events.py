"""Build CollectorX events for meeting artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


COLLECTOR = "meeting-artifacts"
CN_TZ = timezone(timedelta(hours=8))
EXPECTED_P1_MEETING_PLATFORMS = ("feishu", "dingtalk", "wecom", "tencent-meeting")
GENERIC_MEETING_PLATFORMS = {"local-file"}
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
MEETING_RECOMMENDED_FIELDS = (
    "artifact_type",
    "platform",
    "title",
    "start_time",
    "end_time",
    "organizer",
    "participants",
    "participant_refs",
    "participant_role_counts",
    "meeting_url",
    "text_preview",
    "duration",
    "attachment_refs",
    "recording_refs",
    "action_items",
    "decision_points",
    "risk_items",
    "mentioned_symbols",
    "time",
)


def split_policy_terms(values: Optional[Iterable[str]]) -> List[str]:
    terms: List[str] = []
    for value in values or []:
        for item in re.split(r"[,，;；|\n]+", str(value)):
            cleaned = item.strip()
            if cleaned:
                terms.append(cleaned)
    return terms


def build_meeting_scope_policy(
    *,
    allow_source_platforms: Optional[Iterable[str]] = None,
    deny_source_platforms: Optional[Iterable[str]] = None,
    allow_participants: Optional[Iterable[str]] = None,
    deny_participants: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "allow_source_platforms": split_policy_terms(allow_source_platforms),
        "deny_source_platforms": split_policy_terms(deny_source_platforms),
        "allow_participants": split_policy_terms(allow_participants),
        "deny_participants": split_policy_terms(deny_participants),
        "allow_keywords": split_policy_terms(allow_keywords),
        "deny_keywords": split_policy_terms(deny_keywords),
        "filtered_record_count": 0,
        "filter_reason_counts": {},
        "policy_does_not_assert_investment_relevance": True,
    }
    policy["enabled"] = any(
        policy[key]
        for key in (
            "allow_source_platforms",
            "deny_source_platforms",
            "allow_participants",
            "deny_participants",
            "allow_keywords",
            "deny_keywords",
        )
    )
    return policy


def meeting_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy or not policy.get("enabled"):
        return None
    if policy.get("deny_source_platforms") and policy_hit(policy["deny_source_platforms"], meeting_platform_surface(event)):
        return "source_platform_denied"
    if policy.get("allow_source_platforms") and not policy_hit(policy["allow_source_platforms"], meeting_platform_surface(event)):
        return "source_platform_not_allowed"
    if policy.get("deny_participants") and policy_hit(policy["deny_participants"], meeting_participant_surface(event)):
        return "participant_denied"
    if policy.get("allow_participants") and not policy_hit(policy["allow_participants"], meeting_participant_surface(event)):
        return "participant_not_allowed"
    if policy.get("deny_keywords") and policy_hit(policy["deny_keywords"], meeting_keyword_surface(event)):
        return "keyword_denied"
    if policy.get("allow_keywords") and not policy_hit(policy["allow_keywords"], meeting_keyword_surface(event)):
        return "keyword_not_allowed"
    return None


def finalize_meeting_scope_policy_audit(audit: Dict[str, Any]) -> Dict[str, Any]:
    policy = audit.get("meeting_scope_policy") or {}
    if policy:
        policy["filter_reason_counts"] = dict(sorted((policy.get("filter_reason_counts") or {}).items()))
    candidate_count = int(audit.get("candidate_record_count") or 0)
    emitted_count = int(audit.get("emitted_event_count") or 0)
    audit["meeting_scope_policy_filtered_all"] = bool(policy.get("enabled") and candidate_count > 0 and emitted_count == 0)
    return audit


def meeting_platform_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    return [data.get("platform"), raw_ref.get("platform"), event.get("collector")]


def meeting_participant_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    surface: List[Any] = [data.get("organizer")]
    surface.extend(data.get("participants") or [])
    for ref in data.get("participant_refs") or []:
        if isinstance(ref, dict):
            surface.extend([ref.get("name"), ref.get("role")])
        else:
            surface.append(ref)
    return surface


def meeting_keyword_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    surface: List[Any] = [
        data.get("artifact_type"),
        data.get("title"),
        data.get("meeting_url"),
        data.get("text_preview"),
        raw_ref.get("path"),
        raw_ref.get("archive_member"),
    ]
    for key in ("action_items", "decision_points", "risk_items", "mentioned_symbols", "attachment_refs", "recording_refs"):
        surface.extend(flatten_policy_surface(data.get(key)))
    return surface


def flatten_policy_surface(value: Any) -> List[Any]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, dict):
        surface: List[Any] = []
        for item in value.values():
            surface.extend(flatten_policy_surface(item))
        return surface
    if isinstance(value, list):
        surface = []
        for item in value:
            surface.extend(flatten_policy_surface(item))
        return surface
    return [value]


def policy_hit(terms: Sequence[str], surfaces: Iterable[Any]) -> bool:
    haystacks = [str(surface).lower() for surface in surfaces if surface not in (None, "", [], {})]
    for term in terms:
        needle = str(term).lower()
        if needle and any(needle in haystack for haystack in haystacks):
            return True
    return False


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def artifact_to_event(record: Dict[str, Any], *, path: Path, collected_at: Optional[str] = None) -> Dict[str, Any]:
    path_label = first(record, ["path", "file", "source_path"]) or str(path)
    title = first(record, ["title", "meeting_title", "name", "topic", "标题", "会议主题"]) or Path(path_label).stem
    text = first(record, ["text", "content", "transcript", "summary", "minutes", "正文", "内容", "纪要", "逐字稿"]) or ""
    participants = participants_for(record)
    participant_refs = participant_refs_for(record, participants)
    attachment_refs = attachment_refs_for(record)
    recording_refs = recording_refs_for(record)
    action_items = action_items_for(record, text)
    decision_points = decision_points_for(record, text)
    risk_items = risk_items_for(record, text)
    mentioned_symbols = mentioned_symbols_for(record, text)
    explicit_platform = first(record, ["platform", "source_app", "provider", "来源", "平台"])
    platform = normalize_platform(explicit_platform) if explicit_platform else infer_platform(path_label, record)
    start_time = first(record, ["start_time", "started_at", "time", "date", "meeting_time", "开始时间", "日期"])
    end_time = first(record, ["end_time", "ended_at", "结束时间"])
    artifact_type = first(record, ["artifact_type", "type", "kind", "类型"]) or infer_artifact_type(path)
    data = {
        "artifact_type": artifact_type,
        "platform": platform,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "organizer": first(record, ["organizer", "host", "主持人", "组织者"]),
        "participants": participants,
        "participant_count": len(participants),
        "participant_refs": participant_refs,
        "participant_role_counts": role_counts(participant_refs),
        "meeting_url": first(record, ["meeting_url", "url", "link", "会议链接", "链接"]),
        "text_preview": text[:2000],
        "has_text": bool(text),
        "text_length": len(text),
        "duration": first(record, ["duration", "时长"]),
        "attachment_refs": attachment_refs,
        "attachment_ref_count": len(attachment_refs),
        "recording_refs": recording_refs,
        "recording_ref_count": len(recording_refs),
        "artifact_ref_summary": artifact_ref_summary(attachment_refs, recording_refs),
        "action_items": action_items,
        "action_item_count": len(action_items),
        "decision_points": decision_points,
        "decision_point_count": len(decision_points),
        "risk_items": risk_items,
        "risk_item_count": len(risk_items),
        "mentioned_symbols": mentioned_symbols,
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "path": path_label,
        "artifact_type": artifact_type,
        "platform": platform,
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_label, title, start_time, text[:160]),
        "collector": COLLECTOR,
        "source": "用户授权会议产物",
        "owner_scope": "personal",
        "kind": "note",
        "time": start_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": raw_ref,
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


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event["kind"] for event in events)
    type_counts = Counter((event.get("data") or {}).get("artifact_type", "unknown") for event in events)
    platform_counts = Counter((event.get("data") or {}).get("platform", "unknown") for event in events)
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    scope_policy_filtered_all = bool((collection_audit or {}).get("meeting_scope_policy_filtered_all"))
    observed_platforms = sorted(platform for platform, count in platform_counts.items() if count and platform != "unknown")
    observed_expected = [platform for platform in EXPECTED_P1_MEETING_PLATFORMS if platform_counts.get(platform)]
    missing_expected = [platform for platform in EXPECTED_P1_MEETING_PLATFORMS if not platform_counts.get(platform)]
    unknown_event_count = sum(
        count
        for platform, count in platform_counts.items()
        if platform not in EXPECTED_P1_MEETING_PLATFORMS and platform not in GENERIC_MEETING_PLATFORMS
    )
    return {
        "schema": "collectorx.meeting_artifacts.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "artifact_type_counts": dict(sorted(type_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "platform_coverage": {
            "expected_p1_platforms": list(EXPECTED_P1_MEETING_PLATFORMS),
            "observed_platforms": observed_platforms,
            "observed_expected_platforms": observed_expected,
            "missing_expected_platforms": missing_expected,
            "platform_counts": dict(sorted(platform_counts.items())),
            "unknown_event_count": unknown_event_count,
            "real_account_validation": False,
        },
        "field_coverage": field_coverage(events),
        "meeting_surface_summary": meeting_surface_summary(events),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_meeting_classification_done": False,
            "required_lens": "meeting-minutes",
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": meeting_readiness_status(events, gap_only=gap_only, scope_policy_filtered_all=scope_policy_filtered_all),
            "can_enter_finclaw": bool(events) and not gap_only and not scope_policy_filtered_all,
            "can_claim_investment_meeting_minutes": False,
            "source_collection_scope": meeting_source_collection_scope(gap_only=gap_only, scope_policy_filtered_all=scope_policy_filtered_all),
            "platform_coverage_status": platform_coverage_status(events, missing_expected),
            "next_action": meeting_next_action(gap_only=gap_only, scope_policy_filtered_all=scope_policy_filtered_all),
        },
    }


def meeting_readiness_status(events: List[Dict[str, Any]], *, gap_only: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_filtered_all"
    if gap_only:
        return "needs_meeting_artifact_input"
    if not events:
        return "records_empty"
    return "events_collected"


def meeting_source_collection_scope(*, gap_only: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_excluded_all"
    if gap_only:
        return "none"
    return "partial_authorized_input"


def meeting_next_action(*, gap_only: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "Broaden meeting scope policy or provide authorized meeting artifacts inside the allowed scope."
    if gap_only:
        return "Provide authorized meeting minutes/transcript files."
    return "Feed events into meeting-minutes lens."


def platform_coverage_status(events: List[Dict[str, Any]], missing_expected: List[str]) -> str:
    if not events or all((event.get("data") or {}).get("gap") for event in events):
        return "no_platform_observed"
    if not missing_expected:
        return "all_expected_platforms_observed"
    return "partial_expected_platforms_observed"


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
        f"- observed_platforms: `{', '.join(manifest['platform_coverage']['observed_platforms']) or 'none'}`",
        f"- missing_expected_platforms: `{', '.join(manifest['platform_coverage']['missing_expected_platforms']) or 'none'}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- participant_events: {manifest['meeting_surface_summary']['events_with_participants']}",
        f"- attachment_events: {manifest['meeting_surface_summary']['events_with_attachments']}",
        f"- recording_ref_events: {manifest['meeting_surface_summary']['events_with_recording_refs']}",
        f"- action_item_events: {manifest['meeting_surface_summary']['events_with_action_items']}",
        f"- decision_point_events: {manifest['meeting_surface_summary']['events_with_decision_points']}",
        f"- risk_item_events: {manifest['meeting_surface_summary']['events_with_risk_items']}",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
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


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    meeting_events = [event for event in events if event.get("collector") == COLLECTOR and event.get("kind") == "note"]
    field_counts = {
        field: sum(1 for event in meeting_events if meeting_field_present(event, field))
        for field in MEETING_RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(MEETING_RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_text": sum(1 for event in meeting_events if (event.get("data") or {}).get("has_text")),
    }


def meeting_field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    data = event.get("data") or {}
    value = data.get(field)
    return value not in (None, "", [], {})


def meeting_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    meeting_events = [event for event in events if event.get("collector") == COLLECTOR and event.get("kind") == "note"]
    role_counter: Counter[str] = Counter()
    for event in meeting_events:
        role_counter.update((event.get("data") or {}).get("participant_role_counts") or {})
    return {
        "artifact_event_count": len(meeting_events),
        "events_with_text": sum(1 for event in meeting_events if (event.get("data") or {}).get("has_text")),
        "events_with_participants": sum(1 for event in meeting_events if (event.get("data") or {}).get("participants")),
        "events_with_participant_roles": sum(1 for event in meeting_events if (event.get("data") or {}).get("participant_role_counts")),
        "participant_role_counts": dict(sorted(role_counter.items())),
        "events_with_organizer": sum(1 for event in meeting_events if (event.get("data") or {}).get("organizer")),
        "events_with_meeting_url": sum(1 for event in meeting_events if (event.get("data") or {}).get("meeting_url")),
        "events_with_attachments": sum(1 for event in meeting_events if (event.get("data") or {}).get("attachment_refs")),
        "events_with_recording_refs": sum(1 for event in meeting_events if (event.get("data") or {}).get("recording_refs")),
        "events_with_action_items": sum(1 for event in meeting_events if (event.get("data") or {}).get("action_items")),
        "action_item_count": sum(int((event.get("data") or {}).get("action_item_count") or 0) for event in meeting_events),
        "events_with_decision_points": sum(1 for event in meeting_events if (event.get("data") or {}).get("decision_points")),
        "decision_point_count": sum(int((event.get("data") or {}).get("decision_point_count") or 0) for event in meeting_events),
        "events_with_risk_items": sum(1 for event in meeting_events if (event.get("data") or {}).get("risk_items")),
        "risk_item_count": sum(int((event.get("data") or {}).get("risk_item_count") or 0) for event in meeting_events),
        "events_with_mentioned_symbols": sum(1 for event in meeting_events if (event.get("data") or {}).get("mentioned_symbols")),
        "mentioned_symbol_count": sum(len((event.get("data") or {}).get("mentioned_symbols") or []) for event in meeting_events),
        "events_with_duration": sum(1 for event in meeting_events if (event.get("data") or {}).get("duration")),
        "events_with_start_time": sum(1 for event in meeting_events if (event.get("data") or {}).get("start_time")),
        "events_with_end_time": sum(1 for event in meeting_events if (event.get("data") or {}).get("end_time")),
    }


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    audit = {
        "source_ref_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("path")),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "archive_path_traversal_members_collected": False,
    }
    if collection_audit:
        audit.update(collection_audit)
    return audit


def participants_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("participants") or record.get("attendees") or record.get("参会人") or []
    if isinstance(raw, str):
        return split_people(raw)
    if isinstance(raw, list):
        people = []
        for item in raw:
            if isinstance(item, dict):
                value = first(item, ["name", "display_name", "username", "user_name", "姓名", "名称"])
            else:
                value = str(item)
            if value and value != "None":
                people.append(value.strip())
        return people
    return []


def participant_refs_for(record: Dict[str, Any], participants: List[str]) -> List[Dict[str, str]]:
    raw = record.get("participants") or record.get("attendees") or record.get("speakers") or record.get("参会人") or []
    refs: List[Dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = first(item, ["name", "display_name", "username", "user_name", "姓名", "名称"])
                role = first(item, ["role", "title", "position", "职位", "角色"])
            else:
                name = str(item)
                role = None
            append_participant_ref(refs, name, role)
    else:
        for name in participants:
            append_participant_ref(refs, name, None)
    return refs


def append_participant_ref(refs: List[Dict[str, str]], name: Optional[str], role: Optional[str]) -> None:
    if not name or name == "None":
        return
    clean_name = name.strip()
    clean_role = normalize_role(role) or infer_role_from_name(clean_name)
    ref = {"name": clean_name, "role": clean_role}
    if ref not in refs:
        refs.append(ref)


def normalize_role(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip().lower()
    if any(token in text for token in ("fund", "portfolio", "基金", "组合", "投资经理")):
        return "portfolio_manager"
    if any(token in text for token in ("research", "analyst", "研究", "分析")):
        return "analyst"
    if any(token in text for token in ("expert", "专家")):
        return "expert"
    if any(token in text for token in ("ir", "董秘", "公司")):
        return "company_ir"
    if any(token in text for token in ("risk", "风控")):
        return "risk_control"
    if any(token in text for token in ("committee", "投委")):
        return "investment_committee"
    return None


def infer_role_from_name(name: str) -> str:
    return normalize_role(name) or "unknown"


def role_counts(participant_refs: List[Dict[str, str]]) -> Dict[str, int]:
    counts = Counter(str(ref.get("role") or "unknown") for ref in participant_refs)
    return dict(sorted(counts.items()))


def split_people(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,，、;；|\n]+", text) if item.strip()]


def attachment_refs_for(record: Dict[str, Any]) -> List[str]:
    raw = record.get("attachments") or record.get("attachment_refs") or record.get("附件") or []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item.get("path") if isinstance(item, dict) else item) for item in raw if str(item)]
    return []


def recording_refs_for(record: Dict[str, Any]) -> List[str]:
    raw = (
        record.get("recording")
        or record.get("recording_ref")
        or record.get("recording_refs")
        or record.get("recording_url")
        or record.get("录制")
        or []
    )
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        refs = []
        for item in raw:
            if isinstance(item, dict):
                value = item.get("url") or item.get("path") or item.get("name") or item.get("id")
            else:
                value = item
            if value not in (None, ""):
                refs.append(str(value))
        return refs
    if isinstance(raw, dict):
        value = raw.get("url") or raw.get("path") or raw.get("name") or raw.get("id")
        return [str(value)] if value not in (None, "") else []
    return []


def artifact_ref_summary(attachment_refs: List[str], recording_refs: List[str]) -> Dict[str, Any]:
    refs = attachment_refs + recording_refs
    return {
        "attachment_ref_count": len(attachment_refs),
        "recording_ref_count": len(recording_refs),
        "total_ref_count": len(refs),
        "url_ref_count": sum(1 for ref in refs if is_url(ref)),
        "local_pointer_count": sum(1 for ref in refs if ref and not is_url(ref)),
        "external_refs_fetched": False,
        "recording_body_collected": False,
    }


def is_url(value: str) -> bool:
    return str(value).lower().startswith(("http://", "https://"))


def action_items_for(record: Dict[str, Any], text: str) -> List[str]:
    return structured_items_for(
        record,
        ("action_items", "actions", "todos", "follow_ups", "next_steps", "待办", "行动项", "下一步"),
        text,
        ("行动", "待办", "跟进", "下一步", "action", "todo", "follow", "负责", "会后"),
    )


def decision_points_for(record: Dict[str, Any], text: str) -> List[str]:
    return structured_items_for(
        record,
        ("decision_points", "decisions", "conclusions", "结论", "决策点", "决策", "决定"),
        text,
        ("决策", "决定", "结论", "通过"),
    )


def risk_items_for(record: Dict[str, Any], text: str) -> List[str]:
    return structured_items_for(
        record,
        ("risk_items", "risks", "risk_points", "风险", "风险点"),
        text,
        ("风险", "下行", "回撤", "止损", "高估", "不确定", "警惕"),
    )


def structured_items_for(
    record: Dict[str, Any],
    keys: Iterable[str],
    text: str,
    tokens: Iterable[str],
    *,
    limit: int = 20,
) -> List[str]:
    items: List[str] = []
    for key in keys:
        items.extend(normalize_item_list(record.get(key)))
    lowered_tokens = tuple(token.lower() for token in tokens)
    for segment in text_segments(text):
        lowered = segment.lower()
        if any(token in lowered for token in lowered_tokens):
            items.append(segment)
    return dedupe_text_items(items, limit=limit)


def normalize_item_list(raw: Any) -> List[str]:
    if raw in (None, "", [], {}):
        return []
    if isinstance(raw, str):
        return [item.strip() for item in re.split(r"[\n;；]+", raw) if item.strip()]
    if isinstance(raw, list):
        items = []
        for item in raw:
            if isinstance(item, dict):
                value = first(item, ["text", "title", "content", "name", "summary", "内容"])
            else:
                value = str(item)
            if value and value != "None":
                items.append(value.strip())
        return items
    if isinstance(raw, dict):
        value = first(raw, ["text", "title", "content", "name", "summary", "内容"])
        return [value] if value else []
    return [str(raw)]


def text_segments(text: str) -> List[str]:
    parts: List[str] = []
    for line in str(text or "").splitlines():
        for segment in re.split(r"[。！？!?；;]", line):
            cleaned = segment.strip(" -\t\r\n")
            if cleaned:
                parts.append(cleaned[:300])
    return parts


def dedupe_text_items(items: Iterable[str], *, limit: int) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = re.sub(r"\s+", " ", str(item)).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned[:300])
        if len(result) >= limit:
            break
    return result


def mentioned_symbols_for(record: Dict[str, Any], text: str) -> List[str]:
    explicit = normalize_item_list(
        record.get("symbols") or record.get("symbol") or record.get("tickers") or record.get("security_code") or record.get("证券代码")
    )
    found = re.findall(r"(?<!\d)(?:[036]\d{5})(?!\d)", text)
    return dedupe_text_items([*explicit, *found], limit=50)


def infer_platform(path_label: str, record: Optional[Dict[str, Any]] = None) -> str:
    body = str(path_label).lower()
    if record:
        body += " " + json.dumps(sanitized(record), ensure_ascii=False).lower()
    matched = platform_match(body)
    return matched or "local-file"


def normalize_platform(value: Any) -> str:
    body = str(value).lower()
    return platform_match(body) or str(value)


def platform_match(body: str) -> Optional[str]:
    if "feishu" in body or "lark" in body or "飞书" in body:
        return "feishu"
    if "dingtalk" in body or "钉钉" in body:
        return "dingtalk"
    if "wecom" in body or "企业微信" in body or "work.weixin" in body:
        return "wecom"
    if "tencent" in body or "腾讯会议" in body or "meeting.tencent" in body:
        return "tencent-meeting"
    return None


def sanitized(value: Any) -> Any:
    secret_fragments = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session")
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if any(fragment in str(key).lower() for fragment in secret_fragments):
                continue
            cleaned[str(key)] = sanitized(item)
        return cleaned
    if isinstance(value, list):
        return [sanitized(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:4000]
    return value


def infer_artifact_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".vtt", ".srt"}:
        return "transcript"
    return "minutes"


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
