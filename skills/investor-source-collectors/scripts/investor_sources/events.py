"""CollectorX event and evidence builders for investor source profiles."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .profiles import INVESTOR_DIMENSIONS, SOURCE_PROFILES, get_profile, profile_count_by_priority


EVENT_SCHEMA = "collectorx.event.v1"
EVIDENCE_SCHEMA = "finclaw.investor_wiki_evidence.v1"
CN_TZ = timezone(timedelta(hours=8))
ALLOWED_KINDS = {
    "message",
    "file",
    "note",
    "email",
    "calendar",
    "task",
    "trade",
    "holding",
    "watchlist",
    "a2a",
    "profile",
    "other",
}
INVESTMENT_NOTE_TYPE_ORDER = (
    "review_note",
    "rules_library",
    "trade_checklist",
    "valuation_assumption",
    "research_note",
    "unclassified_investment_note",
)
TASK_CALENDAR_SURFACE_ORDER = (
    "research_task",
    "trade_plan",
    "review_reminder",
    "earnings_calendar",
    "research_meeting",
    "risk_check",
    "unclassified_task_calendar",
)
MEETING_MINUTES_SURFACE_ORDER = (
    "roadshow_minutes",
    "research_meeting",
    "investment_committee",
    "expert_call",
    "earnings_call",
    "decision_point",
    "risk_discussion",
    "follow_up_action",
    "unclassified_meeting_minutes",
)
WECHAT_ARTICLE_SURFACE_ORDER = (
    "broker_research_article",
    "company_fundamental_article",
    "market_strategy_article",
    "industry_theme_article",
    "valuation_method_article",
    "portfolio_case_article",
    "risk_warning_article",
    "macro_policy_article",
    "unclassified_wechat_article",
)
WECHAT_SOURCE_ACCOUNT_TYPE_ORDER = (
    "broker_research_account",
    "finance_media_account",
    "investment_creator_account",
    "company_ir_account",
    "unknown_account_type",
)
SOCIAL_INFLUENCE_TOPIC_ORDER = (
    "macro_policy",
    "market_strategy",
    "industry_theme",
    "company_fundamental",
    "fund_wealth",
    "trading_review",
    "risk_control",
    "portfolio_watch",
    "creator_education",
    "hk_us_market",
    "unclassified_social_topic",
)


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def stable_id(*parts: Any) -> str:
    body = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"investor-source:{digest}"


def normalize_kind(kind: str) -> str:
    return kind if kind in ALLOWED_KINDS else "other"


def build_event(
    *,
    source_id: str,
    source_label: str,
    record: Dict[str, Any],
    raw_ref: Dict[str, Any],
    collected_at: Optional[str] = None,
    event_kind: Optional[str] = None,
    event_time: Optional[str] = None,
    classification: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    profile = get_profile(source_id)
    kind = normalize_kind(event_kind or profile["default_kind"])
    event_time = event_time or first_value(
        record,
        [
            "time",
            "date",
            "datetime",
            "timestamp",
            "created_at",
            "updated_at",
            "交易日期",
            "日期",
            "时间",
        ],
    )
    normalized = normalize_record_payload(record)
    data = {
        "source_profile": source_id,
        "source_priority": profile["priority"],
        "evidence_level": profile["evidence_level"],
        "investor_subdimensions": profile["subdimensions"],
        "normalized": normalized,
        "classification": classification or {},
        "payload": record,
    }
    return {
        "schema": EVENT_SCHEMA,
        "id": stable_id(source_id, source_label, raw_ref.get("path"), raw_ref.get("row"), json.dumps(record, ensure_ascii=False, sort_keys=True)),
        "collector": source_id,
        "source": source_label,
        "owner_scope": "personal",
        "kind": kind,
        "time": event_time,
        "collected_at": collected_at or now_iso(),
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": profile.get("contains", []),
        },
        "wiki_targets": profile.get("wiki_targets", []),
    }


def build_gap_event(source_id: str, *, collected_at: Optional[str] = None, reason: str = "source_input_missing") -> Dict[str, Any]:
    profile = get_profile(source_id)
    message = {
        "source_input_missing": "No authorized input was provided; collector did not fabricate source data.",
        "no_readable_input": "Authorized input was provided, but no readable records were found.",
        "no_investment_evidence_matched": "Authorized input was scanned, but no investment-related evidence matched the lens rules.",
        "source_policy_filtered_all": "Authorized input was scanned, but every candidate was excluded by the configured source allow/deny policy.",
    }.get(reason, "Collector could not produce source evidence for this run.")
    record = {
        "signal_type": "collector_preflight_gap",
        "gap": reason,
        "message": message,
        "accepted_inputs": profile.get("accepted_inputs", []),
        "authorization": profile.get("authorization", ""),
    }
    event = build_event(
        source_id=source_id,
        source_label=f"{profile['display_name']} preflight",
        record=record,
        raw_ref={"preflight": True, "reason": reason},
        collected_at=collected_at,
        event_kind="other",
    )
    event["data"]["investor_subdimensions"] = []
    event["data"]["evidence_level"] = "none"
    event["data"]["classification"] = {
        "is_investment_evidence": False,
        "confidence": 0,
        "reasons": [reason],
        "classifier": "collector-preflight-gap",
    }
    event["wiki_targets"] = []
    return event


def build_manifest(
    source_id: str,
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    profile = get_profile(source_id)
    kind_counts = Counter(event["kind"] for event in events)
    only_gap = bool(events) and all(is_gap_event(event) for event in events)
    gap_reason = None
    if only_gap:
        gap_reason = (events[0].get("data") or {}).get("payload", {}).get("gap")
    status = {
        "source_input_missing": "needs_source_authorization_or_input",
        "no_readable_input": "no_readable_input",
        "no_investment_evidence_matched": "no_investment_evidence_matched",
        "source_policy_filtered_all": "source_policy_filtered_all",
    }.get(str(gap_reason), "events_collected" if not only_gap else "needs_source_authorization_or_input")
    classifications = [
        (event.get("data") or {}).get("classification") or {}
        for event in events
        if not is_gap_event(event)
    ]
    return {
        "schema": "collectorx.investor_source_collect.manifest.v1",
        "collector": source_id,
        "skill": "investor-source-collectors",
        "display_name": profile["display_name"],
        "priority": profile["priority"],
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "classification_summary": {
            "classifier": "investor-source-keyword-v1",
            "matched_event_count": sum(1 for item in classifications if item.get("is_investment_evidence")),
            "non_matched_event_count": sum(1 for item in classifications if not item.get("is_investment_evidence")),
            "average_confidence": round(
                sum(float(item.get("confidence") or 0) for item in classifications) / len(classifications),
                3,
            )
            if classifications
            else 0,
        },
        "lens_surface_summary": lens_surface_summary(source_id, events),
        "collection_readiness": {
            "status": status,
            "can_enter_finclaw": bool(events) and not only_gap,
            "can_claim_complete_source_collection": False,
            "source_collection_scope": "none" if only_gap else "partial_authorized_input",
            "next_action": next_action_for_status(status),
        },
        "privacy": {
            "local_only": True,
            "sensitive": True,
            "contains": profile.get("contains", []),
        },
        "collection_audit": collection_audit or {},
    }


def build_investor_wiki_evidence(events: List[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    by_subdimension: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    source_counts = Counter()
    kind_counts = Counter()
    for event in usable_events:
        kind_counts[event.get("kind", "unknown")] += 1
        data = event.get("data") or {}
        source_profile = data.get("source_profile") or event.get("collector")
        source_counts[source_profile] += 1
        for subdimension in data.get("investor_subdimensions", []):
            by_subdimension[str(subdimension)].append(event)

    dimensions = []
    support_counts = Counter()
    for dimension in INVESTOR_DIMENSIONS:
        children = []
        for sub_id, sub_name in dimension["children"]:
            sub_events = by_subdimension.get(sub_id, [])
            source_ids = sorted({(event.get("data") or {}).get("source_profile") or event.get("collector") for event in sub_events})
            support_level = support_level_for_sources(source_ids)
            support_counts[support_level] += 1
            children.append(
                {
                    "subdimension_id": sub_id,
                    "subdimension_name": sub_name,
                    "support_level": support_level,
                    "suggested_maturity": maturity_for_support(support_level),
                    "evidence_count": len(sub_events),
                    "source_profiles": source_ids,
                    "route_targets": sorted({target for event in sub_events for target in event.get("wiki_targets", [])}),
                    "signals": signals_for(sub_id, source_ids),
                    "gaps": gaps_for(sub_id, source_ids),
                    "privacy": {
                        "local_only": True,
                        "sensitive": any((event.get("privacy") or {}).get("sensitive") for event in sub_events),
                    },
                }
            )
        dimensions.append(
            {
                "dimension_id": dimension["dimension_id"],
                "dimension_name": dimension["dimension_name"],
                "children": children,
            }
        )

    return {
        "schema": EVIDENCE_SCHEMA,
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "skill": "investor-source-collectors",
            "event_schema": EVENT_SCHEMA,
            "event_count": len(usable_events),
            "kind_counts": dict(sorted(kind_counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "source_profile_priority_counts": profile_count_by_priority(
                SOURCE_PROFILES[source_id] for source_id in source_counts if source_id in SOURCE_PROFILES
            ),
            "soulmirror_target_schema": "external.investor / 7 dimensions / 20 subdimensions",
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": [
                "collectorx.event.v1",
                "finclaw.investor_wiki_evidence.v1",
                "SoulMirror investor-portrait distill/organize",
                "schema-controlled markdown wiki",
            ],
        },
        "dimensions": dimensions,
        "coverage_summary": {
            "dimension_count": len(dimensions),
            "subdimension_count": sum(len(d["children"]) for d in dimensions),
            "support_level_counts": dict(sorted(support_counts.items())),
            "source_surface_summary": source_surface_summary(usable_events),
            "usable_for_wiki_now": [
                child["subdimension_id"]
                for dimension in dimensions
                for child in dimension["children"]
                if child["support_level"] in {"strong", "medium"}
            ],
        },
    }


def lens_surface_summary(source_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if source_id == "investment-notes":
        return investment_note_surface_summary(events)
    if source_id == "task-calendar-investor":
        return task_calendar_surface_summary(events)
    if source_id == "meeting-minutes":
        return meeting_minutes_surface_summary(events)
    if source_id == "wechat-article-favorites":
        return wechat_article_surface_summary(events)
    if source_id == "social-investment-influence":
        return social_influence_surface_summary(events)
    return {}


def source_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    summaries: Dict[str, Any] = {}
    by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        source_id = str((event.get("data") or {}).get("source_profile") or event.get("collector") or "unknown")
        by_source[source_id].append(event)
    if "investment-notes" in by_source:
        summaries["investment-notes"] = investment_note_surface_summary(by_source["investment-notes"])
    if "task-calendar-investor" in by_source:
        summaries["task-calendar-investor"] = task_calendar_surface_summary(by_source["task-calendar-investor"])
    if "meeting-minutes" in by_source:
        summaries["meeting-minutes"] = meeting_minutes_surface_summary(by_source["meeting-minutes"])
    if "wechat-article-favorites" in by_source:
        summaries["wechat-article-favorites"] = wechat_article_surface_summary(by_source["wechat-article-favorites"])
    if "social-investment-influence" in by_source:
        summaries["social-investment-influence"] = social_influence_surface_summary(by_source["social-investment-influence"])
    return summaries


def investment_note_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    note_type_counts: Counter[str] = Counter()
    primary_type_counts: Counter[str] = Counter()
    source_app_counts: Counter[str] = Counter()
    upstream_collector_counts: Counter[str] = Counter()
    matched_symbol_event_count = 0
    full_content_event_count = 0
    tagged_event_count = 0
    path_event_count = 0
    url_event_count = 0
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        classification = data.get("classification") if isinstance(data.get("classification"), dict) else {}
        note_types = classification.get("investment_note_types") if isinstance(classification.get("investment_note_types"), list) else []
        if not note_types:
            note_types = ["unclassified_investment_note"]
        for note_type in note_types:
            note_type_counts[str(note_type)] += 1
        primary_type_counts[str(classification.get("primary_investment_note_type") or note_types[0])] += 1
        source_app_counts[note_source_app(event)] += 1
        upstream_collector_counts[str(payload.get("upstream_collector") or event.get("raw_ref", {}).get("upstream_collector") or "direct_input")] += 1
        if classification.get("matched_symbols"):
            matched_symbol_event_count += 1
        if payload.get("content_included") is True or "content" in payload:
            full_content_event_count += 1
        if payload.get("tags"):
            tagged_event_count += 1
        if payload.get("path") or event.get("raw_ref", {}).get("path"):
            path_event_count += 1
        if payload.get("url") or event.get("raw_ref", {}).get("url"):
            url_event_count += 1
    return {
        "event_count": len(usable_events),
        "expected_investment_note_types": list(INVESTMENT_NOTE_TYPE_ORDER[:-1]),
        "investment_note_type_counts": ordered_counts(note_type_counts, INVESTMENT_NOTE_TYPE_ORDER),
        "primary_investment_note_type_counts": ordered_counts(primary_type_counts, INVESTMENT_NOTE_TYPE_ORDER),
        "missing_expected_investment_note_types": [
            note_type for note_type in INVESTMENT_NOTE_TYPE_ORDER[:-1] if note_type_counts.get(note_type, 0) == 0
        ],
        "source_app_counts": dict(sorted(source_app_counts.items())),
        "upstream_collector_counts": dict(sorted(upstream_collector_counts.items())),
        "matched_symbol_event_count": matched_symbol_event_count,
        "full_content_event_count": full_content_event_count,
        "preview_only_event_count": max(len(usable_events) - full_content_event_count, 0),
        "tagged_event_count": tagged_event_count,
        "path_event_count": path_event_count,
        "url_event_count": url_event_count,
        "generic_notes_lens": True,
        "collector_writes_wiki_directly": False,
    }


def note_source_app(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw_ref = event.get("raw_ref") or {}
    value = payload.get("source_app") or raw_ref.get("source_app")
    upstream_raw_ref = raw_ref.get("upstream_raw_ref")
    if not value and isinstance(upstream_raw_ref, dict):
        value = upstream_raw_ref.get("source_app")
    return str(value or "unknown")


def ordered_counts(counts: Counter[str], order: Iterable[str]) -> Dict[str, int]:
    result = {key: counts[key] for key in order if counts.get(key)}
    for key, value in sorted(counts.items()):
        if key not in result:
            result[key] = value
    return result


def task_calendar_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    surface_counts: Counter[str] = Counter()
    primary_surface_counts: Counter[str] = Counter()
    upstream_collector_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    source_platform_counts: Counter[str] = Counter()
    matched_symbol_event_count = 0
    events_with_time = 0
    events_with_due_or_start = 0
    events_with_reminders = 0
    events_with_meeting_url = 0
    events_with_project_or_calendar = 0
    events_with_duration_minutes = 0
    multi_day_event_count = 0
    invalid_time_range_count = 0
    completed_task_count = 0
    overdue_task_count = 0
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        classification = data.get("classification") if isinstance(data.get("classification"), dict) else {}
        surfaces = classification.get("task_calendar_surfaces") if isinstance(classification.get("task_calendar_surfaces"), list) else []
        if not surfaces:
            surfaces = ["unclassified_task_calendar"]
        for surface in surfaces:
            surface_counts[str(surface)] += 1
        primary_surface_counts[str(classification.get("primary_task_calendar_surface") or surfaces[0])] += 1
        upstream = str(payload.get("upstream_collector") or event.get("raw_ref", {}).get("upstream_collector") or event.get("kind") or "direct_input")
        upstream_collector_counts[upstream] += 1
        kind_counts[str(event.get("kind") or "unknown")] += 1
        source_platform_counts[task_calendar_source_platform(event)] += 1
        if classification.get("matched_symbols"):
            matched_symbol_event_count += 1
        if event.get("time") or payload.get("time"):
            events_with_time += 1
        if payload.get("due") or payload.get("start") or event.get("time"):
            events_with_due_or_start += 1
        if payload.get("reminders"):
            events_with_reminders += 1
        if payload.get("meeting_url"):
            events_with_meeting_url += 1
        if payload.get("project_name") or payload.get("calendar_name"):
            events_with_project_or_calendar += 1
        if isinstance(payload.get("duration_minutes"), int):
            events_with_duration_minutes += 1
        if payload.get("is_multi_day") is True:
            multi_day_event_count += 1
        if payload.get("time_order_valid") is False:
            invalid_time_range_count += 1
        if payload.get("is_completed") is True:
            completed_task_count += 1
        if payload.get("is_overdue") is True:
            overdue_task_count += 1
    return {
        "event_count": len(usable_events),
        "expected_task_calendar_surfaces": list(TASK_CALENDAR_SURFACE_ORDER[:-1]),
        "task_calendar_surface_counts": ordered_counts(surface_counts, TASK_CALENDAR_SURFACE_ORDER),
        "primary_task_calendar_surface_counts": ordered_counts(primary_surface_counts, TASK_CALENDAR_SURFACE_ORDER),
        "missing_expected_task_calendar_surfaces": [
            surface for surface in TASK_CALENDAR_SURFACE_ORDER[:-1] if surface_counts.get(surface, 0) == 0
        ],
        "upstream_collector_counts": dict(sorted(upstream_collector_counts.items())),
        "kind_counts": dict(sorted(kind_counts.items())),
        "source_platform_counts": dict(sorted(source_platform_counts.items())),
        "matched_symbol_event_count": matched_symbol_event_count,
        "events_with_time": events_with_time,
        "events_with_due_or_start": events_with_due_or_start,
        "events_with_reminders": events_with_reminders,
        "events_with_meeting_url": events_with_meeting_url,
        "events_with_project_or_calendar": events_with_project_or_calendar,
        "events_with_duration_minutes": events_with_duration_minutes,
        "multi_day_event_count": multi_day_event_count,
        "invalid_time_range_count": invalid_time_range_count,
        "completed_task_count": completed_task_count,
        "overdue_task_count": overdue_task_count,
        "generic_task_calendar_lens": True,
        "collector_writes_wiki_directly": False,
    }


def task_calendar_source_platform(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw_ref = event.get("raw_ref") or {}
    value = payload.get("source_app") or payload.get("source_platform") or raw_ref.get("source_app") or raw_ref.get("source_platform")
    upstream_raw_ref = raw_ref.get("upstream_raw_ref")
    if not value and isinstance(upstream_raw_ref, dict):
        value = upstream_raw_ref.get("source_app") or upstream_raw_ref.get("source_platform")
    return str(value or "unknown")


def social_influence_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    topic_counts: Counter[str] = Counter()
    primary_topic_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    platform_topic_counts: Counter[str] = Counter()
    action_topic_counts: Counter[str] = Counter()
    creator_event_count = 0
    creator_url_event_count = 0
    url_event_count = 0
    tagged_event_count = 0
    symbol_event_count = 0
    engagement_event_count = 0
    comment_preview_event_count = 0
    content_preview_event_count = 0
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        topics = payload.get("social_topics") if isinstance(payload.get("social_topics"), list) else []
        if not topics:
            topics = ["unclassified_social_topic"]
        platform = str(payload.get("platform") or "unknown")
        action = str(payload.get("action_type") or "unknown")
        platform_counts[platform] += 1
        action_counts[action] += 1
        for topic in topics:
            topic_value = str(topic)
            topic_counts[topic_value] += 1
            platform_topic_counts[f"{platform}:{topic_value}"] += 1
            action_topic_counts[f"{action}:{topic_value}"] += 1
        primary_topic_counts[str(payload.get("primary_social_topic") or topics[0])] += 1
        if payload.get("creator"):
            creator_event_count += 1
        if payload.get("creator_url"):
            creator_url_event_count += 1
        if payload.get("url"):
            url_event_count += 1
        if payload.get("tags") or payload.get("topics"):
            tagged_event_count += 1
        if payload.get("symbols"):
            symbol_event_count += 1
        if any(payload.get(field) is not None for field in ("like_count", "comment_count", "share_count", "favorite_count", "view_count", "follower_count")):
            engagement_event_count += 1
        if payload.get("comment_preview"):
            comment_preview_event_count += 1
        if payload.get("content_preview"):
            content_preview_event_count += 1
    return {
        "event_count": len(usable_events),
        "expected_social_topics": list(SOCIAL_INFLUENCE_TOPIC_ORDER[:-1]),
        "social_topic_counts": ordered_counts(topic_counts, SOCIAL_INFLUENCE_TOPIC_ORDER),
        "primary_social_topic_counts": ordered_counts(primary_topic_counts, SOCIAL_INFLUENCE_TOPIC_ORDER),
        "missing_expected_social_topics": [
            topic for topic in SOCIAL_INFLUENCE_TOPIC_ORDER[:-1] if topic_counts.get(topic, 0) == 0
        ],
        "platform_counts": dict(sorted(platform_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "platform_topic_counts": dict(sorted(platform_topic_counts.items())),
        "action_topic_counts": dict(sorted(action_topic_counts.items())),
        "creator_event_count": creator_event_count,
        "creator_url_event_count": creator_url_event_count,
        "url_event_count": url_event_count,
        "tagged_event_count": tagged_event_count,
        "symbol_event_count": symbol_event_count,
        "engagement_event_count": engagement_event_count,
        "comment_preview_event_count": comment_preview_event_count,
        "content_preview_event_count": content_preview_event_count,
        "evidence_strength": "weak_attention",
        "requires_corroboration": True,
        "usable_as_investment_conclusion": False,
        "generic_social_lens": True,
        "collector_writes_wiki_directly": False,
    }


def meeting_minutes_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    surface_counts: Counter[str] = Counter()
    primary_surface_counts: Counter[str] = Counter()
    upstream_collector_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    source_platform_counts: Counter[str] = Counter()
    matched_symbol_event_count = 0
    participant_event_count = 0
    participant_ref_count = 0
    meeting_url_event_count = 0
    attachment_ref_event_count = 0
    recording_ref_event_count = 0
    events_with_time = 0
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        classification = data.get("classification") if isinstance(data.get("classification"), dict) else {}
        surfaces = classification.get("meeting_minutes_surfaces") if isinstance(classification.get("meeting_minutes_surfaces"), list) else []
        if not surfaces:
            surfaces = ["unclassified_meeting_minutes"]
        for surface in surfaces:
            surface_counts[str(surface)] += 1
        primary_surface_counts[str(classification.get("primary_meeting_minutes_surface") or surfaces[0])] += 1
        upstream = str(payload.get("upstream_collector") or event.get("raw_ref", {}).get("upstream_collector") or "direct_input")
        upstream_collector_counts[upstream] += 1
        kind_counts[str(event.get("kind") or "unknown")] += 1
        source_platform_counts[meeting_source_platform(event)] += 1
        if classification.get("matched_symbols"):
            matched_symbol_event_count += 1
        participant_count = value_count(first_payload_value(payload, ("participants", "attendees", "speakers", "participant_refs", "参会人")))
        if participant_count:
            participant_event_count += 1
            participant_ref_count += participant_count
        if value_present(first_payload_value(payload, ("meeting_url", "url", "link", "source_url", "会议链接"))):
            meeting_url_event_count += 1
        if value_present(first_payload_value(payload, ("attachment", "attachments", "attachment_refs", "file_refs", "files", "附件"))):
            attachment_ref_event_count += 1
        if value_present(first_payload_value(payload, ("recording", "recording_ref", "recording_refs", "recording_url", "录制"))):
            recording_ref_event_count += 1
        if event.get("time") or first_payload_value(payload, ("time", "date", "start_time", "timestamp", "upstream_time", "会议时间")):
            events_with_time += 1
    return {
        "event_count": len(usable_events),
        "expected_meeting_minutes_surfaces": list(MEETING_MINUTES_SURFACE_ORDER[:-1]),
        "meeting_minutes_surface_counts": ordered_counts(surface_counts, MEETING_MINUTES_SURFACE_ORDER),
        "primary_meeting_minutes_surface_counts": ordered_counts(primary_surface_counts, MEETING_MINUTES_SURFACE_ORDER),
        "missing_expected_meeting_minutes_surfaces": [
            surface for surface in MEETING_MINUTES_SURFACE_ORDER[:-1] if surface_counts.get(surface, 0) == 0
        ],
        "upstream_collector_counts": dict(sorted(upstream_collector_counts.items())),
        "kind_counts": dict(sorted(kind_counts.items())),
        "source_platform_counts": dict(sorted(source_platform_counts.items())),
        "matched_symbol_event_count": matched_symbol_event_count,
        "participant_event_count": participant_event_count,
        "participant_ref_count": participant_ref_count,
        "meeting_url_event_count": meeting_url_event_count,
        "attachment_ref_event_count": attachment_ref_event_count,
        "recording_ref_event_count": recording_ref_event_count,
        "events_with_time": events_with_time,
        "generic_meeting_lens": True,
        "collector_writes_wiki_directly": False,
    }


def meeting_source_platform(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw_ref = event.get("raw_ref") or {}
    value = (
        payload.get("source_platform")
        or payload.get("source_app")
        or payload.get("platform")
        or payload.get("upstream_collector")
        or raw_ref.get("source_platform")
        or raw_ref.get("source_app")
    )
    upstream_raw_ref = raw_ref.get("upstream_raw_ref")
    if not value and isinstance(upstream_raw_ref, dict):
        value = upstream_raw_ref.get("source_platform") or upstream_raw_ref.get("source_app") or upstream_raw_ref.get("platform")
    return str(value or "unknown")


def first_payload_value(payload: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def value_present(value: Any) -> bool:
    return value_count(value) > 0


def value_count(value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, dict):
        return 1 if value else 0
    if isinstance(value, (list, tuple, set)):
        return sum(1 for item in value if item not in (None, "", [], {}))
    return 1


def wechat_article_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    surface_counts: Counter[str] = Counter()
    primary_surface_counts: Counter[str] = Counter()
    action_type_counts: Counter[str] = Counter()
    item_type_counts: Counter[str] = Counter()
    upstream_collector_counts: Counter[str] = Counter()
    source_account_type_counts: Counter[str] = Counter()
    matched_symbol_event_count = 0
    events_with_url = 0
    events_with_source_account = 0
    events_with_tags = 0
    events_with_text = 0
    events_with_action_time = 0
    public_account_article_count = 0
    source_accounts = set()
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        classification = data.get("classification") if isinstance(data.get("classification"), dict) else {}
        surfaces = classification.get("wechat_article_surfaces") if isinstance(classification.get("wechat_article_surfaces"), list) else []
        if not surfaces:
            surfaces = ["unclassified_wechat_article"]
        for surface in surfaces:
            surface_counts[str(surface)] += 1
        primary_surface_counts[str(classification.get("primary_wechat_article_surface") or surfaces[0])] += 1
        action_type_counts[str(payload.get("action_type") or "unknown")] += 1
        item_type = str(payload.get("item_type") or "unknown")
        item_type_counts[item_type] += 1
        if item_type == "public_account_article":
            public_account_article_count += 1
        upstream = str(payload.get("upstream_collector") or event.get("raw_ref", {}).get("upstream_collector") or "direct_input")
        upstream_collector_counts[upstream] += 1
        source_account = str(payload.get("source_account") or "")
        if source_account:
            source_accounts.add(source_account)
            events_with_source_account += 1
        source_account_type_counts[wechat_source_account_type(source_account)] += 1
        if classification.get("matched_symbols"):
            matched_symbol_event_count += 1
        if payload.get("url") or event.get("raw_ref", {}).get("url"):
            events_with_url += 1
        if value_present(payload.get("tags")):
            events_with_tags += 1
        if payload.get("has_text") is True or value_present(payload.get("text_preview")) or value_present(payload.get("content")):
            events_with_text += 1
        if event.get("time") or first_payload_value(payload, ("action_time", "time", "saved_at", "read_at", "shared_at")):
            events_with_action_time += 1
    return {
        "event_count": len(usable_events),
        "expected_wechat_article_surfaces": list(WECHAT_ARTICLE_SURFACE_ORDER[:-1]),
        "wechat_article_surface_counts": ordered_counts(surface_counts, WECHAT_ARTICLE_SURFACE_ORDER),
        "primary_wechat_article_surface_counts": ordered_counts(primary_surface_counts, WECHAT_ARTICLE_SURFACE_ORDER),
        "missing_expected_wechat_article_surfaces": [
            surface for surface in WECHAT_ARTICLE_SURFACE_ORDER[:-1] if surface_counts.get(surface, 0) == 0
        ],
        "action_type_counts": dict(sorted(action_type_counts.items())),
        "item_type_counts": dict(sorted(item_type_counts.items())),
        "upstream_collector_counts": dict(sorted(upstream_collector_counts.items())),
        "source_account_type_counts": ordered_counts(source_account_type_counts, WECHAT_SOURCE_ACCOUNT_TYPE_ORDER),
        "source_account_count": len(source_accounts),
        "public_account_article_count": public_account_article_count,
        "matched_symbol_event_count": matched_symbol_event_count,
        "events_with_url": events_with_url,
        "events_with_source_account": events_with_source_account,
        "events_with_tags": events_with_tags,
        "events_with_text": events_with_text,
        "events_with_action_time": events_with_action_time,
        "generic_wechat_article_lens": True,
        "collector_writes_wiki_directly": False,
    }


def wechat_source_account_type(source_account: str) -> str:
    text = source_account.lower()
    if any(token in source_account for token in ("券商", "证券", "研究所", "中信", "中金", "华泰", "国泰君安", "招商", "广发")):
        return "broker_research_account"
    if any(token in source_account for token in ("财联社", "华尔街见闻", "格隆汇", "第一财经", "证券时报", "财经")):
        return "finance_media_account"
    if any(token in source_account for token in ("投资", "价投", "价值", "复盘", "量化", "炒股", "组合")):
        return "investment_creator_account"
    if "ir" in text or any(token in source_account for token in ("投资者关系", "董秘", "公司公告")):
        return "company_ir_account"
    return "unknown_account_type"


def normalize_record_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    symbol = first_value(record, ["symbol", "code", "股票代码", "证券代码", "基金代码", "标的"])
    name = first_value(record, ["name", "title", "股票名称", "证券名称", "基金名称", "名称", "标题"])
    amount = first_value(record, ["amount", "market_value", "市值", "金额", "资产", "持仓金额", "参考市值"])
    side = first_value(record, ["side", "操作", "买卖方向", "交易类型"])
    author = first_value(record, ["author", "sender", "from", "speaker", "作者", "发送人", "说话人"])
    text = first_value(record, ["text", "content", "body", "note", "summary", "正文", "内容", "备注"])
    normalized = {
        "symbol": symbol,
        "name": name,
        "amount": amount,
        "side": side,
        "author": author,
        "text_preview": str(text)[:500] if text is not None else None,
    }
    return {key: value for key, value in normalized.items() if value not in (None, "")}


def is_gap_event(event: Dict[str, Any]) -> bool:
    return (event.get("data") or {}).get("payload", {}).get("signal_type") == "collector_preflight_gap"


def next_action_for_status(status: str) -> str:
    return {
        "needs_source_authorization_or_input": "提供用户授权的源数据或连接器输入后重跑。",
        "no_readable_input": "检查输入路径、文件格式和导出内容后重跑。",
        "no_investment_evidence_matched": "输入已读取，但未命中投资证据；可降低阈值、补充白名单或确认这批数据不属于投资分身。",
        "source_policy_filtered_all": "输入已读取，但全部被来源范围策略排除；请检查联系人/群/发送者白名单和黑名单。",
        "events_collected": "可进入投资分身蒸馏；继续做真实源适配和增量验证。",
    }.get(status, "检查 manifest 后决定下一步。")


def first_value(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def support_level_for_sources(source_ids: List[str]) -> str:
    if not source_ids:
        return "none"
    levels = {SOURCE_PROFILES.get(source_id, {}).get("evidence_level", "") for source_id in source_ids}
    if any(level.startswith("strong") for level in levels):
        return "strong"
    if any(level.startswith("medium") for level in levels):
        return "medium"
    return "weak"


def maturity_for_support(level: str) -> str:
    return {
        "strong": "solid",
        "medium": "basic",
        "weak": "hint",
        "none": "empty",
    }.get(level, "empty")


def signals_for(subdimension_id: str, source_ids: List[str]) -> List[str]:
    if not source_ids:
        return []
    labels = [SOURCE_PROFILES[source_id]["display_name"] for source_id in source_ids if source_id in SOURCE_PROFILES]
    return [f"来自 {', '.join(labels)} 的个人授权证据。"]


def gaps_for(subdimension_id: str, source_ids: List[str]) -> List[str]:
    if source_ids:
        return ["仍需跨源去重、时间线对齐和交易事实交叉验证。"]
    return ["当前还没有该子维度的个人授权证据。"]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
