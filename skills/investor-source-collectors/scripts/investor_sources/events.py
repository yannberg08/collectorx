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
WECHAT_DIALOGUE_SURFACE_ORDER = (
    "trade_intention",
    "buy_sell_reason",
    "position_sizing",
    "risk_emotion",
    "consultation_network",
    "research_discussion",
    "review_reflection",
    "unclassified_wechat_dialogue",
)
WECHAT_SOURCE_ACCOUNT_TYPE_ORDER = (
    "broker_research_account",
    "finance_media_account",
    "investment_creator_account",
    "company_ir_account",
    "unknown_account_type",
)
RESEARCH_DOCUMENT_SURFACE_ORDER = (
    "research_report",
    "financial_statement",
    "valuation_model",
    "announcement_note",
    "review_note",
    "screenshot_or_image",
    "table_model",
    "unclassified_research_document",
)
EMAIL_RESEARCH_SURFACE_ORDER = (
    "morning_meeting",
    "broker_research_report",
    "roadshow_invite",
    "company_ir_thread",
    "earnings_announcement",
    "research_attachment",
    "portfolio_alert",
    "unclassified_email_research",
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
    resolved_collected_at = collected_at or now_iso()
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
    ) or resolved_collected_at
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
        "collected_at": resolved_collected_at,
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
    collection_readiness = {
        "status": status,
        "can_enter_finclaw": bool(events) and not only_gap,
        "can_claim_complete_source_collection": False,
        "source_collection_scope": "none" if only_gap else "partial_authorized_input",
        "next_action": next_action_for_status(status),
    }
    lens_surface = lens_surface_summary(source_id, events)
    research_proof = (
        build_research_corpus_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "research-documents"
        else None
    )
    wechat_proof = (
        build_wechat_dialogue_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "wechat-investment-dialogue"
        else None
    )
    investment_note_proof = (
        build_investment_note_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "investment-notes"
        else None
    )
    task_calendar_proof = (
        build_task_calendar_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "task-calendar-investor"
        else None
    )
    meeting_minutes_proof = (
        build_meeting_minutes_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "meeting-minutes"
        else None
    )
    wechat_article_proof = (
        build_wechat_article_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "wechat-article-favorites"
        else None
    )
    social_influence_proof = (
        build_social_influence_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "social-investment-influence"
        else None
    )
    email_research_proof = (
        build_email_research_boundary_proof(events, audit=collection_audit or {}, collection_readiness=collection_readiness)
        if source_id == "email-research"
        else None
    )
    manifest = {
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
        "lens_surface_summary": lens_surface,
        "collection_readiness": collection_readiness,
        "privacy": {
            "local_only": True,
            "sensitive": True,
            "contains": profile.get("contains", []),
        },
        "collection_audit": collection_audit or {},
    }
    if research_proof is not None:
        manifest["research_corpus_boundary_proof"] = research_proof
    if wechat_proof is not None:
        manifest["wechat_dialogue_boundary_proof"] = wechat_proof
    if investment_note_proof is not None:
        manifest["investment_note_boundary_proof"] = investment_note_proof
    if task_calendar_proof is not None:
        manifest["task_calendar_boundary_proof"] = task_calendar_proof
    if meeting_minutes_proof is not None:
        manifest["meeting_minutes_boundary_proof"] = meeting_minutes_proof
    if wechat_article_proof is not None:
        manifest["wechat_article_boundary_proof"] = wechat_article_proof
    if social_influence_proof is not None:
        manifest["social_influence_boundary_proof"] = social_influence_proof
    if email_research_proof is not None:
        manifest["email_research_boundary_proof"] = email_research_proof
    return manifest


def build_research_corpus_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    policy = audit.get("content_extraction_policy") if isinstance(audit.get("content_extraction_policy"), dict) else {}
    surface = research_document_surface_summary(usable_events)
    return {
        "source_type": "user_selected_research_files_or_upstream_file_events",
        "proof_level": research_corpus_proof_level(usable_events, audit=audit, readiness=collection_readiness),
        "event_count": len(usable_events),
        "candidate_record_count": audit.get("candidate_record_count", 0),
        "matched_event_count": audit.get("matched_event_count", 0),
        "filtered_candidate_count": audit.get("filtered_candidate_count", 0),
        "input_boundary": {
            "input_count": audit.get("input_count", 0),
            "requested_inputs": audit.get("requested_inputs", []),
            "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
            "input_missing_count": audit.get("input_missing_count", 0),
            "skipped_file_count": audit.get("skipped_file_count", 0),
            "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
            "limit": audit.get("limit"),
            "limit_reached": audit.get("limit_reached", False),
        },
        "format_boundary": {
            "extension_counts": audit.get("extension_counts", {}),
            "skipped_extension_counts": audit.get("skipped_extension_counts", {}),
            "parser_counts": audit.get("parser_counts", {}),
        },
        "content_boundary": {
            "include_content_enabled": policy.get("include_content_enabled", False),
            "include_image_ocr_enabled": policy.get("include_image_ocr_enabled", False),
            "content_read_event_count": audit.get("content_read_event_count", 0),
            "metadata_only_file_count": audit.get("metadata_only_file_count", 0),
            "screenshot_metadata_only_file_count": audit.get("screenshot_metadata_only_file_count", 0),
            "image_ocr_event_count": audit.get("image_ocr_event_count", 0),
            "ocr_performed": audit.get("ocr_performed", False),
            "content_extract_status_counts": audit.get("content_extract_status_counts", {}),
            "image_ocr_status_counts": audit.get("image_ocr_status_counts", {}),
            "preview_char_limit": policy.get("preview_char_limit"),
            "extracted_text_char_limit": policy.get("extracted_text_char_limit"),
        },
        "research_document_surface_summary": surface,
        "complete_research_corpus_claimed": False,
        "whole_disk_scan_claimed": False,
        "public_report_database_crawl_claimed": False,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": collection_readiness.get("can_enter_finclaw", False),
    }


def research_corpus_proof_level(
    usable_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    readiness: Dict[str, Any],
) -> str:
    if not usable_events:
        status = str(readiness.get("status") or "")
        if status == "needs_source_authorization_or_input":
            return "no_authorized_research_input"
        if status == "no_readable_input":
            return "no_readable_research_input"
        if status == "source_policy_filtered_all":
            return "source_policy_filtered_all"
        return "no_usable_research_evidence_after_filter"
    if int(audit.get("image_ocr_event_count") or 0) > 0:
        return "authorized_research_corpus_with_image_ocr"
    if int(audit.get("content_read_event_count") or 0) > 0:
        return "authorized_research_corpus_with_content"
    if int(audit.get("metadata_only_file_count") or 0) > 0:
        return "authorized_research_corpus_metadata_only"
    return "authorized_research_corpus_event_only"


def build_email_research_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    source_policy = audit.get("source_policy") if isinstance(audit.get("source_policy"), dict) else {}
    surface = email_research_surface_summary(usable_events)
    return {
        "source_type": "email_lake_research_lens",
        "proof_level": email_research_proof_level(usable_events, audit=audit, readiness=collection_readiness),
        "event_count": len(usable_events),
        "candidate_record_count": audit.get("candidate_record_count", 0),
        "matched_event_count": audit.get("matched_event_count", 0),
        "filtered_candidate_count": audit.get("filtered_candidate_count", 0),
        "input_boundary": {
            "input_count": audit.get("input_count", 0),
            "requested_inputs": audit.get("requested_inputs", []),
            "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
            "input_missing_count": audit.get("input_missing_count", 0),
            "skipped_file_count": audit.get("skipped_file_count", 0),
            "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
            "limit": audit.get("limit"),
            "limit_reached": audit.get("limit_reached", False),
        },
        "source_policy_boundary": {
            "enabled": source_policy.get("enabled", False),
            "allow_senders": source_policy.get("allow_senders", []),
            "deny_senders": source_policy.get("deny_senders", []),
            "filtered_candidate_count": source_policy.get("filtered_candidate_count", 0),
            "filter_reason_counts": source_policy.get("filter_reason_counts", {}),
            "policy_does_not_assert_investment_relevance": source_policy.get("policy_does_not_assert_investment_relevance", True),
        },
        "mailbox_boundary": {
            "sender_domain_counts": surface.get("sender_domain_counts", {}),
            "mailbox_counts": surface.get("mailbox_counts", {}),
            "folder_counts": surface.get("folder_counts", {}),
            "events_with_time": surface.get("events_with_time", 0),
            "message_id_event_count": surface.get("message_id_event_count", 0),
            "upstream_collector_counts": surface.get("upstream_collector_counts", {}),
        },
        "content_boundary": {
            "body_preview_event_count": surface.get("body_preview_event_count", 0),
            "full_body_event_count": surface.get("full_body_event_count", 0),
            "attachment_ref_event_count": surface.get("attachment_ref_event_count", 0),
            "research_attachment_event_count": surface.get("research_attachment_event_count", 0),
            "attachment_filename_event_count": surface.get("attachment_filename_event_count", 0),
            "full_body_in_wiki_by_default": False,
            "attachment_bodies_collected": False,
        },
        "email_research_surface_summary": surface,
        "complete_mailbox_claimed": False,
        "complete_email_thread_context_claimed": False,
        "attachment_body_collected_by_default": False,
        "direct_email_reconnect": False,
        "requires_upstream_email_collector": True,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": collection_readiness.get("can_enter_finclaw", False),
    }


def email_research_proof_level(
    usable_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    readiness: Dict[str, Any],
) -> str:
    if not usable_events:
        status = str(readiness.get("status") or "")
        if status == "needs_source_authorization_or_input":
            return "no_authorized_email_lake_input"
        if status == "source_policy_filtered_all":
            return "source_policy_filtered_all"
        if status == "no_readable_input":
            return "no_readable_email_lake_input"
        return "no_usable_email_research_after_filter"
    surface = email_research_surface_summary(usable_events)
    if int(surface.get("research_attachment_event_count") or 0) > 0:
        return "authorized_email_research_with_research_attachment_refs"
    if int(surface.get("attachment_ref_event_count") or 0) > 0:
        return "authorized_email_research_with_attachment_refs"
    if int(surface.get("body_preview_event_count") or 0) > 0:
        return "authorized_email_research_preview_only"
    return "authorized_email_research_event_only"


def build_wechat_dialogue_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    source_policy = audit.get("source_policy") if isinstance(audit.get("source_policy"), dict) else {}
    surface = wechat_dialogue_surface_summary(usable_events)
    return {
        "source_type": "wechat_lake_investment_dialogue_lens",
        "proof_level": wechat_dialogue_proof_level(usable_events, audit=audit, readiness=collection_readiness),
        "event_count": len(usable_events),
        "candidate_record_count": audit.get("candidate_record_count", 0),
        "matched_event_count": audit.get("matched_event_count", 0),
        "filtered_candidate_count": audit.get("filtered_candidate_count", 0),
        "source_policy_boundary": {
            "enabled": source_policy.get("enabled", False),
            "allow_chats": source_policy.get("allow_chats", []),
            "deny_chats": source_policy.get("deny_chats", []),
            "allow_senders": source_policy.get("allow_senders", []),
            "deny_senders": source_policy.get("deny_senders", []),
            "filtered_candidate_count": source_policy.get("filtered_candidate_count", 0),
            "filter_reason_counts": source_policy.get("filter_reason_counts", {}),
            "policy_does_not_assert_investment_relevance": source_policy.get("policy_does_not_assert_investment_relevance", True),
        },
        "dialogue_boundary": surface,
        "complete_wechat_history_claimed": False,
        "complete_dialogue_context_claimed": False,
        "raw_wechat_database_access": False,
        "direct_wechat_reconnect": False,
        "requires_upstream_wechat_collector": True,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": collection_readiness.get("can_enter_finclaw", False),
    }


def wechat_dialogue_proof_level(
    usable_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    readiness: Dict[str, Any],
) -> str:
    if not usable_events:
        status = str(readiness.get("status") or "")
        if status == "needs_source_authorization_or_input":
            return "no_authorized_wechat_lake_input"
        if status == "source_policy_filtered_all":
            return "source_policy_filtered_all"
        if status == "no_readable_input":
            return "no_readable_wechat_lake_input"
        return "no_usable_investment_dialogue_after_filter"
    source_policy = audit.get("source_policy") if isinstance(audit.get("source_policy"), dict) else {}
    if source_policy.get("enabled"):
        return "authorized_wechat_dialogue_with_source_policy"
    return "authorized_wechat_dialogue_partial"


def build_investment_note_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    source_policy = audit.get("source_policy") if isinstance(audit.get("source_policy"), dict) else {}
    surface = investment_note_surface_summary(usable_events)
    return {
        "source_type": "notes_lake_investment_note_lens",
        "proof_level": investment_note_proof_level(usable_events, audit=audit, readiness=collection_readiness),
        "event_count": len(usable_events),
        "candidate_record_count": audit.get("candidate_record_count", 0),
        "matched_event_count": audit.get("matched_event_count", 0),
        "filtered_candidate_count": audit.get("filtered_candidate_count", 0),
        "input_boundary": {
            "input_count": audit.get("input_count", 0),
            "requested_inputs": audit.get("requested_inputs", []),
            "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
            "input_missing_count": audit.get("input_missing_count", 0),
            "skipped_file_count": audit.get("skipped_file_count", 0),
            "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
            "limit": audit.get("limit"),
            "limit_reached": audit.get("limit_reached", False),
        },
        "source_policy_boundary": {
            "enabled": source_policy.get("enabled", False),
            "allow_chats": source_policy.get("allow_chats", []),
            "deny_chats": source_policy.get("deny_chats", []),
            "allow_senders": source_policy.get("allow_senders", []),
            "deny_senders": source_policy.get("deny_senders", []),
            "filtered_candidate_count": source_policy.get("filtered_candidate_count", 0),
            "filter_reason_counts": source_policy.get("filter_reason_counts", {}),
            "policy_does_not_assert_investment_relevance": source_policy.get("policy_does_not_assert_investment_relevance", True),
        },
        "content_boundary": {
            "full_content_event_count": surface.get("full_content_event_count", 0),
            "preview_only_event_count": surface.get("preview_only_event_count", 0),
            "tagged_event_count": surface.get("tagged_event_count", 0),
            "path_event_count": surface.get("path_event_count", 0),
            "url_event_count": surface.get("url_event_count", 0),
        },
        "note_boundary": surface,
        "complete_notes_vault_claimed": False,
        "complete_note_context_claimed": False,
        "direct_notes_reconnect": False,
        "requires_upstream_notes_collector": True,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": collection_readiness.get("can_enter_finclaw", False),
    }


def investment_note_proof_level(
    usable_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    readiness: Dict[str, Any],
) -> str:
    if not usable_events:
        status = str(readiness.get("status") or "")
        if status == "needs_source_authorization_or_input":
            return "no_authorized_notes_lake_input"
        if status == "source_policy_filtered_all":
            return "source_policy_filtered_all"
        if status == "no_readable_input":
            return "no_readable_notes_lake_input"
        return "no_usable_investment_notes_after_filter"
    surface = investment_note_surface_summary(usable_events)
    if int(surface.get("full_content_event_count") or 0) > 0:
        return "authorized_investment_notes_with_full_content"
    return "authorized_investment_notes_preview_only"


def build_task_calendar_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    source_policy = audit.get("source_policy") if isinstance(audit.get("source_policy"), dict) else {}
    surface = task_calendar_surface_summary(usable_events)
    return {
        "source_type": "task_and_calendar_lake_investor_lens",
        "proof_level": task_calendar_proof_level(usable_events, audit=audit, readiness=collection_readiness),
        "event_count": len(usable_events),
        "candidate_record_count": audit.get("candidate_record_count", 0),
        "matched_event_count": audit.get("matched_event_count", 0),
        "filtered_candidate_count": audit.get("filtered_candidate_count", 0),
        "input_boundary": {
            "input_count": audit.get("input_count", 0),
            "requested_inputs": audit.get("requested_inputs", []),
            "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
            "input_missing_count": audit.get("input_missing_count", 0),
            "skipped_file_count": audit.get("skipped_file_count", 0),
            "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
            "limit": audit.get("limit"),
            "limit_reached": audit.get("limit_reached", False),
        },
        "source_policy_boundary": {
            "enabled": source_policy.get("enabled", False),
            "allow_chats": source_policy.get("allow_chats", []),
            "deny_chats": source_policy.get("deny_chats", []),
            "allow_senders": source_policy.get("allow_senders", []),
            "deny_senders": source_policy.get("deny_senders", []),
            "filtered_candidate_count": source_policy.get("filtered_candidate_count", 0),
            "filter_reason_counts": source_policy.get("filter_reason_counts", {}),
            "policy_does_not_assert_investment_relevance": source_policy.get("policy_does_not_assert_investment_relevance", True),
        },
        "upstream_boundary": {
            "upstream_collector_counts": surface.get("upstream_collector_counts", {}),
            "kind_counts": surface.get("kind_counts", {}),
            "source_platform_counts": surface.get("source_platform_counts", {}),
        },
        "time_boundary": {
            "events_with_time": surface.get("events_with_time", 0),
            "events_with_due_or_start": surface.get("events_with_due_or_start", 0),
            "events_with_reminders": surface.get("events_with_reminders", 0),
            "events_with_meeting_url": surface.get("events_with_meeting_url", 0),
            "events_with_project_or_calendar": surface.get("events_with_project_or_calendar", 0),
            "events_with_time_zone": surface.get("events_with_time_zone", 0),
            "events_with_recurrence": surface.get("events_with_recurrence", 0),
            "recurrence_frequency_counts": surface.get("recurrence_frequency_counts", {}),
            "events_with_duration_minutes": surface.get("events_with_duration_minutes", 0),
            "multi_day_event_count": surface.get("multi_day_event_count", 0),
            "invalid_time_range_count": surface.get("invalid_time_range_count", 0),
            "completed_task_count": surface.get("completed_task_count", 0),
            "overdue_task_count": surface.get("overdue_task_count", 0),
        },
        "task_structure_boundary": {
            "events_with_checklist": surface.get("events_with_checklist", 0),
            "checklist_item_total": surface.get("checklist_item_total", 0),
            "checklist_item_completed_count": surface.get("checklist_item_completed_count", 0),
            "checklist_item_pending_count": surface.get("checklist_item_pending_count", 0),
            "average_checklist_completion_rate": surface.get("average_checklist_completion_rate", 0),
            "tasks_with_complete_checklist": surface.get("tasks_with_complete_checklist", 0),
            "tasks_with_incomplete_checklist": surface.get("tasks_with_incomplete_checklist", 0),
        },
        "task_calendar_boundary": surface,
        "complete_task_list_claimed": False,
        "complete_calendar_claimed": False,
        "complete_task_calendar_context_claimed": False,
        "direct_task_or_calendar_reconnect": False,
        "requires_upstream_task_calendar_collector": True,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": collection_readiness.get("can_enter_finclaw", False),
    }


def task_calendar_proof_level(
    usable_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    readiness: Dict[str, Any],
) -> str:
    if not usable_events:
        status = str(readiness.get("status") or "")
        if status == "needs_source_authorization_or_input":
            return "no_authorized_task_calendar_lake_input"
        if status == "source_policy_filtered_all":
            return "source_policy_filtered_all"
        if status == "no_readable_input":
            return "no_readable_task_calendar_lake_input"
        return "no_usable_investment_task_calendar_after_filter"
    surface = task_calendar_surface_summary(usable_events)
    if int(surface.get("events_with_duration_minutes") or 0) > 0 or int(surface.get("invalid_time_range_count") or 0) > 0:
        return "authorized_task_calendar_with_time_quality"
    if int(surface.get("events_with_checklist") or 0) > 0:
        return "authorized_task_calendar_with_checklist_surface"
    if int(surface.get("events_with_reminders") or 0) > 0:
        return "authorized_task_calendar_with_reminder_surface"
    if int(surface.get("events_with_due_or_start") or 0) > 0:
        return "authorized_task_calendar_with_time_surface"
    return "authorized_task_calendar_event_only"


def build_meeting_minutes_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    source_policy = audit.get("source_policy") if isinstance(audit.get("source_policy"), dict) else {}
    surface = meeting_minutes_surface_summary(usable_events)
    return {
        "source_type": "meeting_and_collaboration_lake_investor_lens",
        "proof_level": meeting_minutes_proof_level(usable_events, audit=audit, readiness=collection_readiness),
        "event_count": len(usable_events),
        "candidate_record_count": audit.get("candidate_record_count", 0),
        "matched_event_count": audit.get("matched_event_count", 0),
        "filtered_candidate_count": audit.get("filtered_candidate_count", 0),
        "input_boundary": {
            "input_count": audit.get("input_count", 0),
            "requested_inputs": audit.get("requested_inputs", []),
            "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
            "input_missing_count": audit.get("input_missing_count", 0),
            "skipped_file_count": audit.get("skipped_file_count", 0),
            "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
            "limit": audit.get("limit"),
            "limit_reached": audit.get("limit_reached", False),
        },
        "source_policy_boundary": {
            "enabled": source_policy.get("enabled", False),
            "allow_chats": source_policy.get("allow_chats", []),
            "deny_chats": source_policy.get("deny_chats", []),
            "allow_senders": source_policy.get("allow_senders", []),
            "deny_senders": source_policy.get("deny_senders", []),
            "filtered_candidate_count": source_policy.get("filtered_candidate_count", 0),
            "filter_reason_counts": source_policy.get("filter_reason_counts", {}),
            "policy_does_not_assert_investment_relevance": source_policy.get("policy_does_not_assert_investment_relevance", True),
        },
        "upstream_boundary": {
            "upstream_collector_counts": surface.get("upstream_collector_counts", {}),
            "kind_counts": surface.get("kind_counts", {}),
            "source_platform_counts": surface.get("source_platform_counts", {}),
        },
        "meeting_context_boundary": {
            "participant_event_count": surface.get("participant_event_count", 0),
            "participant_ref_count": surface.get("participant_ref_count", 0),
            "participant_role_event_count": surface.get("participant_role_event_count", 0),
            "participant_role_counts": surface.get("participant_role_counts", {}),
            "meeting_url_event_count": surface.get("meeting_url_event_count", 0),
            "attachment_ref_event_count": surface.get("attachment_ref_event_count", 0),
            "recording_ref_event_count": surface.get("recording_ref_event_count", 0),
            "events_with_time": surface.get("events_with_time", 0),
            "matched_symbol_event_count": surface.get("matched_symbol_event_count", 0),
            "mentioned_symbol_event_count": surface.get("mentioned_symbol_event_count", 0),
            "mentioned_symbol_count": surface.get("mentioned_symbol_count", 0),
        },
        "decision_action_boundary": {
            "decision_point_event_count": surface.get("decision_point_event_count", 0),
            "decision_point_count": surface.get("decision_point_count", 0),
            "action_item_event_count": surface.get("action_item_event_count", 0),
            "action_item_count": surface.get("action_item_count", 0),
            "risk_item_event_count": surface.get("risk_item_event_count", 0),
            "risk_item_count": surface.get("risk_item_count", 0),
        },
        "meeting_minutes_boundary": surface,
        "complete_meeting_history_claimed": False,
        "complete_workspace_claimed": False,
        "complete_meeting_context_claimed": False,
        "recording_body_collected_by_default": False,
        "direct_meeting_platform_reconnect": False,
        "requires_upstream_meeting_or_collaboration_collector": True,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": collection_readiness.get("can_enter_finclaw", False),
    }


def meeting_minutes_proof_level(
    usable_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    readiness: Dict[str, Any],
) -> str:
    if not usable_events:
        status = str(readiness.get("status") or "")
        if status == "needs_source_authorization_or_input":
            return "no_authorized_meeting_lake_input"
        if status == "source_policy_filtered_all":
            return "source_policy_filtered_all"
        if status == "no_readable_input":
            return "no_readable_meeting_lake_input"
        return "no_usable_investment_meetings_after_filter"
    surface = meeting_minutes_surface_summary(usable_events)
    if (
        int(surface.get("decision_point_event_count") or 0) > 0
        or int(surface.get("action_item_event_count") or 0) > 0
        or int(surface.get("risk_item_event_count") or 0) > 0
    ):
        return "authorized_meeting_minutes_with_decision_action_surface"
    if int(surface.get("recording_ref_event_count") or 0) > 0 or int(surface.get("attachment_ref_event_count") or 0) > 0:
        return "authorized_meeting_minutes_with_artifact_refs"
    if int(surface.get("participant_event_count") or 0) > 0 or int(surface.get("meeting_url_event_count") or 0) > 0:
        return "authorized_meeting_minutes_with_context"
    if int(surface.get("events_with_time") or 0) > 0:
        return "authorized_meeting_minutes_with_time_surface"
    return "authorized_meeting_minutes_event_only"


def build_wechat_article_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    source_policy = audit.get("source_policy") if isinstance(audit.get("source_policy"), dict) else {}
    surface = wechat_article_surface_summary(usable_events)
    return {
        "source_type": "wechat_favorites_lake_investment_article_lens",
        "proof_level": wechat_article_proof_level(usable_events, audit=audit, readiness=collection_readiness),
        "event_count": len(usable_events),
        "candidate_record_count": audit.get("candidate_record_count", 0),
        "matched_event_count": audit.get("matched_event_count", 0),
        "filtered_candidate_count": audit.get("filtered_candidate_count", 0),
        "input_boundary": {
            "input_count": audit.get("input_count", 0),
            "requested_inputs": audit.get("requested_inputs", []),
            "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
            "input_missing_count": audit.get("input_missing_count", 0),
            "skipped_file_count": audit.get("skipped_file_count", 0),
            "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
            "limit": audit.get("limit"),
            "limit_reached": audit.get("limit_reached", False),
        },
        "source_policy_boundary": {
            "enabled": source_policy.get("enabled", False),
            "allow_chats": source_policy.get("allow_chats", []),
            "deny_chats": source_policy.get("deny_chats", []),
            "allow_senders": source_policy.get("allow_senders", []),
            "deny_senders": source_policy.get("deny_senders", []),
            "filtered_candidate_count": source_policy.get("filtered_candidate_count", 0),
            "filter_reason_counts": source_policy.get("filter_reason_counts", {}),
            "policy_does_not_assert_investment_relevance": source_policy.get("policy_does_not_assert_investment_relevance", True),
        },
        "upstream_boundary": {
            "upstream_collector_counts": surface.get("upstream_collector_counts", {}),
            "item_type_counts": surface.get("item_type_counts", {}),
        },
        "article_action_boundary": {
            "action_type_counts": surface.get("action_type_counts", {}),
            "source_account_type_counts": surface.get("source_account_type_counts", {}),
            "source_account_count": surface.get("source_account_count", 0),
            "public_account_article_count": surface.get("public_account_article_count", 0),
            "matched_symbol_event_count": surface.get("matched_symbol_event_count", 0),
        },
        "content_pointer_boundary": {
            "events_with_url": surface.get("events_with_url", 0),
            "events_with_source_account": surface.get("events_with_source_account", 0),
            "events_with_tags": surface.get("events_with_tags", 0),
            "events_with_text": surface.get("events_with_text", 0),
            "events_with_action_time": surface.get("events_with_action_time", 0),
        },
        "wechat_article_boundary": surface,
        "complete_wechat_favorites_claimed": False,
        "complete_wechat_read_history_claimed": False,
        "public_account_full_crawl_claimed": False,
        "public_article_body_mirrored": False,
        "direct_wechat_reconnect": False,
        "requires_upstream_wechat_favorites_collector": True,
        "collector_writes_wiki_directly": False,
        "can_enter_finclaw": collection_readiness.get("can_enter_finclaw", False),
    }


def wechat_article_proof_level(
    usable_events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    readiness: Dict[str, Any],
) -> str:
    if not usable_events:
        status = str(readiness.get("status") or "")
        if status == "needs_source_authorization_or_input":
            return "no_authorized_wechat_favorites_lake_input"
        if status == "source_policy_filtered_all":
            return "source_policy_filtered_all"
        if status == "no_readable_input":
            return "no_readable_wechat_favorites_lake_input"
        return "no_usable_investment_articles_after_filter"
    surface = wechat_article_surface_summary(usable_events)
    if int(surface.get("events_with_text") or 0) > 0 and int(surface.get("events_with_source_account") or 0) > 0:
        return "authorized_wechat_articles_with_source_and_content_surface"
    if int(surface.get("events_with_source_account") or 0) > 0:
        return "authorized_wechat_articles_with_source_accounts"
    if int(surface.get("events_with_url") or 0) > 0:
        return "authorized_wechat_articles_with_url_surface"
    return "authorized_wechat_article_actions_event_only"


def build_social_influence_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    audit: Dict[str, Any],
    collection_readiness: Dict[str, Any],
) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    surface = social_influence_surface_summary(usable_events)
    topic_counts = surface["social_topic_counts"]
    observed_topics = [topic for topic in SOCIAL_INFLUENCE_TOPIC_ORDER[:-1] if topic_counts.get(topic)]
    missing_topics = list(surface["missing_expected_social_topics"])
    platform_count = len(surface["platform_counts"])
    action_count = len(surface["action_counts"])
    if not usable_events:
        proof_level = "no_social_influence_candidates"
    elif (
        int(surface["event_count"]) >= 3
        and platform_count >= 2
        and action_count >= 2
        and int(surface["creator_event_count"]) > 0
        and int(surface["content_preview_event_count"]) > 0
    ):
        proof_level = "strong_partial_social_influence_boundary"
    elif int(surface["creator_event_count"]) > 0 and observed_topics:
        proof_level = "medium_partial_social_influence_boundary"
    else:
        proof_level = "weak_partial_social_influence_boundary"
    blockers = []
    if not usable_events:
        blockers.append("no_investment_social_activity_matched")
    if missing_topics:
        blockers.append("missing_social_topics:" + ",".join(missing_topics))
    if int(surface["creator_event_count"]) == 0:
        blockers.append("creator_surface_missing")
    if int(surface["url_event_count"]) == 0:
        blockers.append("url_surface_missing")
    if int(surface["engagement_event_count"]) == 0:
        blockers.append("engagement_surface_missing")
    blockers.extend(
        [
            "creator_domain_allowlist_missing",
            "social_topic_false_positive_review_missing",
            "weak_evidence_backtest_missing",
            "strong_trade_research_corroboration_missing",
            "complete_social_activity_history_not_proven",
        ]
    )
    return {
        "proof_level": proof_level,
        "source_profile": "social-investment-influence",
        "authorized_input_observed": bool(usable_events),
        "weak_evidence_only": True,
        "evidence_strength": "weak_attention",
        "requires_corroboration": True,
        "can_enter_finclaw_lake": bool(usable_events),
        "can_feed_investor_wiki_evidence": bool(usable_events),
        "can_claim_investment_conclusion": False,
        "observed_event_count": len(usable_events),
        "social_topic_boundary": {
            "expected_social_topics": list(SOCIAL_INFLUENCE_TOPIC_ORDER[:-1]),
            "observed_social_topics": observed_topics,
            "missing_expected_social_topics": missing_topics,
            "social_topic_counts": surface["social_topic_counts"],
            "social_topic_false_positive_reviewed": False,
        },
        "platform_action_boundary": {
            "platform_counts": surface["platform_counts"],
            "action_counts": surface["action_counts"],
            "platform_topic_counts": surface["platform_topic_counts"],
            "action_topic_counts": surface["action_topic_counts"],
        },
        "creator_content_boundary": {
            "creator_event_count": surface["creator_event_count"],
            "creator_url_event_count": surface["creator_url_event_count"],
            "url_event_count": surface["url_event_count"],
            "tagged_event_count": surface["tagged_event_count"],
            "symbol_event_count": surface["symbol_event_count"],
            "engagement_event_count": surface["engagement_event_count"],
            "comment_preview_event_count": surface["comment_preview_event_count"],
            "content_preview_event_count": surface["content_preview_event_count"],
            "preview_only": True,
        },
        "source_boundary": {
            "requested_input_count": int(audit.get("input_count") or 0),
            "resolved_input_file_count": int(audit.get("resolved_input_file_count") or 0),
            "input_missing_count": int(audit.get("input_missing_count") or 0),
            "candidate_event_count": int(audit.get("candidate_event_count") or len(events)),
            "matched_event_count": len(usable_events),
            "collection_status": collection_readiness.get("status"),
            "source_collection_scope": collection_readiness.get("source_collection_scope"),
        },
        "wiki_boundary": {
            "event_schema": EVENT_SCHEMA,
            "evidence_schema": EVIDENCE_SCHEMA,
            "collector_writes_wiki_directly": False,
            "required_flow": [
                "social-activity collector",
                "social-investment-influence lens",
                "finclaw.investor_wiki_evidence.v1",
                "SoulMirror investor-portrait distill/organize",
            ],
        },
        "false_claims": {
            "investment_conclusion_claimed": False,
            "complete_social_activity_history_claimed": False,
            "real_account_validation_claimed": False,
            "platform_wide_scrape_performed": False,
            "full_creator_profile_scraped": False,
            "full_content_mirrored": False,
            "private_platform_credentials_collected": False,
            "collector_writes_wiki_directly": False,
        },
        "completion_blockers": blockers,
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
                    "evidence_kinds": sorted({str(event.get("kind") or "unknown") for event in sub_events}),
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
            "source_boundary_proof_summary": source_boundary_proof_summary(usable_events),
            "usable_for_wiki_now": [
                child["subdimension_id"]
                for dimension in dimensions
                for child in dimension["children"]
                if child["support_level"] in {"strong", "medium"}
            ],
        },
    }


def lens_surface_summary(source_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if source_id == "research-documents":
        return research_document_surface_summary(events)
    if source_id == "email-research":
        return email_research_surface_summary(events)
    if source_id == "wechat-investment-dialogue":
        return wechat_dialogue_surface_summary(events)
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
    if "research-documents" in by_source:
        summaries["research-documents"] = research_document_surface_summary(by_source["research-documents"])
    if "email-research" in by_source:
        summaries["email-research"] = email_research_surface_summary(by_source["email-research"])
    if "wechat-investment-dialogue" in by_source:
        summaries["wechat-investment-dialogue"] = wechat_dialogue_surface_summary(by_source["wechat-investment-dialogue"])
    if "task-calendar-investor" in by_source:
        summaries["task-calendar-investor"] = task_calendar_surface_summary(by_source["task-calendar-investor"])
    if "meeting-minutes" in by_source:
        summaries["meeting-minutes"] = meeting_minutes_surface_summary(by_source["meeting-minutes"])
    if "wechat-article-favorites" in by_source:
        summaries["wechat-article-favorites"] = wechat_article_surface_summary(by_source["wechat-article-favorites"])
    if "social-investment-influence" in by_source:
        summaries["social-investment-influence"] = social_influence_surface_summary(by_source["social-investment-influence"])
    return summaries


def source_boundary_proof_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    summaries: Dict[str, Any] = {}
    by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        source_id = str((event.get("data") or {}).get("source_profile") or event.get("collector") or "unknown")
        by_source[source_id].append(event)
    if "social-investment-influence" in by_source:
        source_events = by_source["social-investment-influence"]
        summaries["social-investment-influence"] = build_social_influence_boundary_proof(
            source_events,
            audit={},
            collection_readiness={
                "status": "events_collected" if source_events else "no_investment_evidence_matched",
                "source_collection_scope": "partial_authorized_input" if source_events else "none",
            },
        )
    if "email-research" in by_source:
        source_events = by_source["email-research"]
        summaries["email-research"] = build_email_research_boundary_proof(
            source_events,
            audit={},
            collection_readiness={
                "status": "events_collected" if source_events else "no_investment_evidence_matched",
                "source_collection_scope": "partial_authorized_input" if source_events else "none",
            },
        )
    return summaries


def email_research_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    surface_counts: Counter[str] = Counter()
    primary_surface_counts: Counter[str] = Counter()
    sender_domain_counts: Counter[str] = Counter()
    mailbox_counts: Counter[str] = Counter()
    folder_counts: Counter[str] = Counter()
    upstream_collector_counts: Counter[str] = Counter()
    matched_symbol_event_count = 0
    body_preview_event_count = 0
    full_body_event_count = 0
    attachment_ref_event_count = 0
    attachment_filename_event_count = 0
    research_attachment_event_count = 0
    message_id_event_count = 0
    events_with_time = 0
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        raw_ref = event.get("raw_ref") or {}
        classification = data.get("classification") if isinstance(data.get("classification"), dict) else {}
        domain = email_sender_domain(event)
        if domain:
            sender_domain_counts[domain] += 1
        mailbox = str(first_payload_value(payload, ("mailbox", "account", "email", "邮箱", "账号")) or "")
        if mailbox:
            mailbox_counts[mailbox] += 1
        folder = str(first_payload_value(payload, ("folder", "mailbox_folder", "文件夹")) or raw_ref.get("folder") or "")
        if folder:
            folder_counts[folder] += 1
        upstream_collector_counts[str(payload.get("upstream_collector") or raw_ref.get("upstream_collector") or "email")] += 1
        if classification.get("matched_symbols"):
            matched_symbol_event_count += 1
        if value_present(first_payload_value(payload, ("body_preview", "preview", "snippet", "摘要"))):
            body_preview_event_count += 1
        if value_present(first_payload_value(payload, ("body", "content", "正文", "内容"))):
            full_body_event_count += 1
        attachment_count = value_count(first_payload_value(payload, ("attachment_refs", "attachments", "attachment", "附件")))
        if attachment_count:
            attachment_ref_event_count += 1
            attachment_filename_event_count += attachment_count
        upstream_raw_ref = raw_ref.get("upstream_raw_ref") if isinstance(raw_ref.get("upstream_raw_ref"), dict) else {}
        if raw_ref.get("message_id") or upstream_raw_ref.get("message_id") or payload.get("message_id"):
            message_id_event_count += 1
        if event.get("time") or payload.get("date") or payload.get("time"):
            events_with_time += 1
        surfaces = classify_email_research_surfaces(event)
        if "research_attachment" in surfaces:
            research_attachment_event_count += 1
        for surface in surfaces:
            surface_counts[surface] += 1
        primary_surface_counts[surfaces[0]] += 1
    return {
        "event_count": len(usable_events),
        "expected_email_research_surfaces": list(EMAIL_RESEARCH_SURFACE_ORDER[:-1]),
        "email_research_surface_counts": ordered_counts(surface_counts, EMAIL_RESEARCH_SURFACE_ORDER),
        "primary_email_research_surface_counts": ordered_counts(primary_surface_counts, EMAIL_RESEARCH_SURFACE_ORDER),
        "missing_expected_email_research_surfaces": [
            surface for surface in EMAIL_RESEARCH_SURFACE_ORDER[:-1] if surface_counts.get(surface, 0) == 0
        ],
        "sender_domain_counts": dict(sorted(sender_domain_counts.items())),
        "mailbox_counts": dict(sorted(mailbox_counts.items())),
        "folder_counts": dict(sorted(folder_counts.items())),
        "upstream_collector_counts": dict(sorted(upstream_collector_counts.items())),
        "matched_symbol_event_count": matched_symbol_event_count,
        "body_preview_event_count": body_preview_event_count,
        "full_body_event_count": full_body_event_count,
        "attachment_ref_event_count": attachment_ref_event_count,
        "attachment_filename_event_count": attachment_filename_event_count,
        "research_attachment_event_count": research_attachment_event_count,
        "message_id_event_count": message_id_event_count,
        "events_with_time": events_with_time,
        "full_body_in_wiki_by_default": False,
        "attachment_bodies_collected": False,
        "generic_email_lens": True,
        "collector_writes_wiki_directly": False,
    }


def classify_email_research_surfaces(event: Dict[str, Any]) -> List[str]:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    attachment_text = " ".join(email_attachment_filenames(event))
    text = " ".join(
        str(part)
        for part in (
            payload.get("from"),
            payload.get("sender"),
            payload.get("subject"),
            payload.get("title"),
            payload.get("body_preview"),
            payload.get("body"),
            payload.get("content"),
            attachment_text,
        )
        if part not in (None, "")
    ).lower()
    surfaces: List[str] = []
    if any(token in text for token in ("晨会", "早会", "morning meeting", "morning call", "morning note")):
        surfaces.append("morning_meeting")
    if any(token in text for token in ("研报", "深度", "研究所", "证券研究", "策略", "行业深度", "公司研究", "research report", "broker research")):
        surfaces.append("broker_research_report")
    if any(token in text for token in ("路演", "roadshow", "调研邀请", "路演邀请", "邀请函", "业绩说明会", "交流会", "conference call")):
        surfaces.append("roadshow_invite")
    if any(token in text for token in ("投资者关系", "董秘", " ir ", "ir@", "company ir", "investor relations")):
        surfaces.append("company_ir_thread")
    if any(token in text for token in ("财报", "年报", "季报", "公告", "业绩", "earnings", "annual report", "quarterly report")):
        surfaces.append("earnings_announcement")
    attachment_lower = attachment_text.lower()
    if any(
        token in attachment_text or token in attachment_lower
        for token in (
            "研报",
            "研究",
            "深度报告",
            "晨会",
            "策略",
            "行业",
            "调研",
            "路演",
            "纪要",
            "财报",
            "公告",
            "业绩说明会",
            "research",
            "report",
            "roadshow",
            "morning",
        )
    ):
        surfaces.append("research_attachment")
    if any(token in text for token in ("公告提醒", "组合提醒", "持仓提醒", "预警", "alert", "watchlist", "price alert")):
        surfaces.append("portfolio_alert")
    ordered: List[str] = []
    for surface in EMAIL_RESEARCH_SURFACE_ORDER:
        if surface in surfaces and surface not in ordered:
            ordered.append(surface)
    return ordered or ["unclassified_email_research"]


def email_attachment_filenames(event: Dict[str, Any]) -> List[str]:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    names: List[str] = []
    collect_attachment_names(first_payload_value(payload, ("attachment_refs", "attachments", "attachment", "附件")), names)
    return names


def collect_attachment_names(value: Any, names: List[str]) -> None:
    if value in (None, ""):
        return
    if isinstance(value, dict):
        filename = value.get("filename") or value.get("name") or value.get("file_name") or value.get("文件名")
        if filename:
            names.append(str(filename))
        for nested in value.values():
            if isinstance(nested, (dict, list, tuple)):
                collect_attachment_names(nested, names)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            collect_attachment_names(item, names)
        return
    text = str(value).strip()
    if text:
        names.append(text)


def email_sender_domain(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    sender = str(first_payload_value(payload, ("from", "sender", "发件人")) or "")
    if "@" not in sender:
        return ""
    after_at = sender.rsplit("@", 1)[-1]
    domain = after_at.split(">", 1)[0].split()[0].strip().strip("<>,;").lower()
    return domain


def research_document_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    surface_counts: Counter[str] = Counter()
    primary_surface_counts: Counter[str] = Counter()
    extension_counts: Counter[str] = Counter()
    parser_counts: Counter[str] = Counter()
    content_status_counts: Counter[str] = Counter()
    content_read_event_count = 0
    metadata_only_event_count = 0
    image_ocr_event_count = 0
    screenshot_or_image_event_count = 0
    matched_symbol_event_count = 0
    path_event_count = 0
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        raw_ref = event.get("raw_ref") or {}
        classification = data.get("classification") if isinstance(data.get("classification"), dict) else {}
        extension = research_document_extension(event)
        if extension:
            extension_counts[extension] += 1
        parser = raw_ref.get("parser")
        if parser:
            parser_counts[str(parser)] += 1
        extract = payload.get("content_extract")
        if isinstance(extract, dict):
            content_status_counts[str(extract.get("status") or "unknown")] += 1
        if raw_ref.get("content_read") or payload.get("content_read") is True:
            content_read_event_count += 1
        if payload.get("metadata_only") is True:
            metadata_only_event_count += 1
        if raw_ref.get("image_ocr_performed") or payload.get("image_ocr_performed") is True:
            image_ocr_event_count += 1
        if extension in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".heic", ".heif"}:
            screenshot_or_image_event_count += 1
        if classification.get("matched_symbols"):
            matched_symbol_event_count += 1
        if payload.get("path") or raw_ref.get("path"):
            path_event_count += 1
        surfaces = classify_research_document_surfaces(event)
        for surface in surfaces:
            surface_counts[surface] += 1
        primary_surface_counts[surfaces[0]] += 1
    return {
        "event_count": len(usable_events),
        "expected_research_document_surfaces": list(RESEARCH_DOCUMENT_SURFACE_ORDER[:-1]),
        "research_document_surface_counts": ordered_counts(surface_counts, RESEARCH_DOCUMENT_SURFACE_ORDER),
        "primary_research_document_surface_counts": ordered_counts(primary_surface_counts, RESEARCH_DOCUMENT_SURFACE_ORDER),
        "missing_expected_research_document_surfaces": [
            surface for surface in RESEARCH_DOCUMENT_SURFACE_ORDER[:-1] if surface_counts.get(surface, 0) == 0
        ],
        "extension_counts": dict(sorted(extension_counts.items())),
        "parser_counts": dict(sorted(parser_counts.items())),
        "content_extract_status_counts": dict(sorted(content_status_counts.items())),
        "content_read_event_count": content_read_event_count,
        "metadata_only_event_count": metadata_only_event_count,
        "image_ocr_event_count": image_ocr_event_count,
        "screenshot_or_image_event_count": screenshot_or_image_event_count,
        "matched_symbol_event_count": matched_symbol_event_count,
        "path_event_count": path_event_count,
        "generic_filesystem_lens": True,
        "collector_writes_wiki_directly": False,
    }


def classify_research_document_surfaces(event: Dict[str, Any]) -> List[str]:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    extension = research_document_extension(event)
    text = " ".join(
        str(part)
        for part in (
            payload.get("title"),
            payload.get("name"),
            payload.get("path"),
            payload.get("content_preview"),
            payload.get("content"),
            payload.get("extension"),
        )
        if part not in (None, "")
    ).lower()
    surfaces: List[str] = []
    if extension in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".heic", ".heif"}:
        surfaces.append("screenshot_or_image")
    if extension in {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".numbers"}:
        surfaces.append("table_model")
    if any(token in text for token in ("估值", "dcf", "model", "模型", "roe", "pe", "pb", "安全边际")):
        surfaces.append("valuation_model")
    if any(token in text for token in ("财报", "年报", "季报", "现金流", "利润表", "资产负债", "业绩")):
        surfaces.append("financial_statement")
    if any(token in text for token in ("公告", "董秘", "投资者关系", "ir ")) or " ir" in text:
        surfaces.append("announcement_note")
    if any(token in text for token in ("复盘", "review", "交易总结", "买入理由", "卖出理由")):
        surfaces.append("review_note")
    if any(token in text for token in ("研报", "深度", "策略", "行业", "路演", "调研", "报告", "research report")):
        surfaces.append("research_report")
    ordered: List[str] = []
    for surface in RESEARCH_DOCUMENT_SURFACE_ORDER:
        if surface in surfaces and surface not in ordered:
            ordered.append(surface)
    return ordered or ["unclassified_research_document"]


def research_document_extension(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw_ref = event.get("raw_ref") or {}
    extension = payload.get("extension")
    if extension:
        return str(extension).lower()
    path = payload.get("path") or raw_ref.get("path")
    if path:
        return Path(str(path)).suffix.lower()
    return ""


def wechat_dialogue_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = [event for event in events if not is_gap_event(event)]
    surface_counts: Counter[str] = Counter()
    primary_surface_counts: Counter[str] = Counter()
    chat_counts: Counter[str] = Counter()
    sender_counts: Counter[str] = Counter()
    upstream_collector_counts: Counter[str] = Counter()
    owner_message_count = 0
    non_owner_message_count = 0
    group_chat_event_count = 0
    private_chat_event_count = 0
    events_with_time = 0
    events_with_text = 0
    events_with_source_policy = 0
    matched_symbol_event_count = 0
    for event in usable_events:
        data = event.get("data") or {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        raw_ref = event.get("raw_ref") or {}
        classification = data.get("classification") if isinstance(data.get("classification"), dict) else {}
        chat = wechat_chat_name(event)
        sender = wechat_sender_name(event)
        if chat:
            chat_counts[chat] += 1
        if sender:
            sender_counts[sender] += 1
        if payload.get("sender_is_owner") is True:
            owner_message_count += 1
        elif sender:
            non_owner_message_count += 1
        if wechat_is_group_chat(event):
            group_chat_event_count += 1
        else:
            private_chat_event_count += 1
        if event.get("time") or payload.get("time") or payload.get("upstream_time"):
            events_with_time += 1
        if value_present(payload.get("text")) or value_present(payload.get("content")) or value_present(payload.get("body")):
            events_with_text += 1
        if data.get("source_policy"):
            events_with_source_policy += 1
        if classification.get("matched_symbols"):
            matched_symbol_event_count += 1
        upstream_collector_counts[str(payload.get("upstream_collector") or raw_ref.get("upstream_collector") or "wechat")] += 1
        surfaces = classify_wechat_dialogue_surfaces(event)
        for surface in surfaces:
            surface_counts[surface] += 1
        primary_surface_counts[surfaces[0]] += 1
    return {
        "event_count": len(usable_events),
        "expected_wechat_dialogue_surfaces": list(WECHAT_DIALOGUE_SURFACE_ORDER[:-1]),
        "wechat_dialogue_surface_counts": ordered_counts(surface_counts, WECHAT_DIALOGUE_SURFACE_ORDER),
        "primary_wechat_dialogue_surface_counts": ordered_counts(primary_surface_counts, WECHAT_DIALOGUE_SURFACE_ORDER),
        "missing_expected_wechat_dialogue_surfaces": [
            surface for surface in WECHAT_DIALOGUE_SURFACE_ORDER[:-1] if surface_counts.get(surface, 0) == 0
        ],
        "chat_counts": dict(sorted(chat_counts.items())),
        "chat_count": len(chat_counts),
        "sender_counts": dict(sorted(sender_counts.items())),
        "sender_count": len(sender_counts),
        "owner_message_count": owner_message_count,
        "non_owner_message_count": non_owner_message_count,
        "group_chat_event_count": group_chat_event_count,
        "private_chat_event_count": private_chat_event_count,
        "events_with_time": events_with_time,
        "events_with_text": events_with_text,
        "events_with_source_policy": events_with_source_policy,
        "matched_symbol_event_count": matched_symbol_event_count,
        "upstream_collector_counts": dict(sorted(upstream_collector_counts.items())),
        "generic_wechat_lens": True,
        "collector_writes_wiki_directly": False,
    }


def classify_wechat_dialogue_surfaces(event: Dict[str, Any]) -> List[str]:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    text = " ".join(
        str(part)
        for part in (
            payload.get("text"),
            payload.get("content"),
            payload.get("body"),
            payload.get("summary"),
            payload.get("chat"),
            payload.get("sender"),
        )
        if part not in (None, "")
    ).lower()
    surfaces: List[str] = []
    if any(token in text for token in ("买入", "卖出", "加仓", "减仓", "建仓", "清仓", "调仓", "止损", "止盈", "定投", "申购", "赎回")):
        surfaces.append("trade_intention")
    if any(token in text for token in ("买入理由", "卖出理由", "投资逻辑", "逻辑", "估值", "低估", "高估", "安全边际", "催化", "风险点")):
        surfaces.append("buy_sell_reason")
    if any(token in text for token in ("仓位", "几成仓", "半仓", "满仓", "轻仓", "重仓", "组合", "持仓", "配比")):
        surfaces.append("position_sizing")
    if any(token in text for token in ("焦虑", "恐慌", "贪婪", "怕", "担心", "回撤", "亏损", "风险", "止损", "情绪", "睡不着")):
        surfaces.append("risk_emotion")
    if any(token in text for token in ("老师", "怎么看", "请教", "建议", "帮我看看", "投顾", "券商", "私募", "公募", "群里")):
        surfaces.append("consultation_network")
    if any(token in text for token in ("财报", "研报", "调研", "路演", "纪要", "行业", "基本面", "现金流", "roe", "pe", "pb", "dcf")):
        surfaces.append("research_discussion")
    if any(token in text for token in ("复盘", "回顾", "错了", "错因", "总结", "纪律", "执行", "交易计划")):
        surfaces.append("review_reflection")
    ordered: List[str] = []
    for surface in WECHAT_DIALOGUE_SURFACE_ORDER:
        if surface in surfaces and surface not in ordered:
            ordered.append(surface)
    return ordered or ["unclassified_wechat_dialogue"]


def wechat_chat_name(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw_ref = event.get("raw_ref") or {}
    upstream_raw_ref = raw_ref.get("upstream_raw_ref") if isinstance(raw_ref.get("upstream_raw_ref"), dict) else {}
    value = payload.get("chat") or payload.get("chat_name") or payload.get("conversation") or raw_ref.get("chat") or upstream_raw_ref.get("chat")
    return str(value or "")


def wechat_sender_name(event: Dict[str, Any]) -> str:
    data = event.get("data") or {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw_ref = event.get("raw_ref") or {}
    upstream_raw_ref = raw_ref.get("upstream_raw_ref") if isinstance(raw_ref.get("upstream_raw_ref"), dict) else {}
    value = payload.get("sender") or payload.get("from") or payload.get("author") or raw_ref.get("sender") or upstream_raw_ref.get("sender")
    return str(value or "")


def wechat_is_group_chat(event: Dict[str, Any]) -> bool:
    chat = wechat_chat_name(event)
    source = str(event.get("source") or "")
    if any(token in chat for token in ("群", "@chatroom")):
        return True
    return "群" in source or "@chatroom" in source


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
    events_with_time_zone = 0
    events_with_recurrence = 0
    recurrence_frequency_counts: Counter[str] = Counter()
    events_with_duration_minutes = 0
    multi_day_event_count = 0
    invalid_time_range_count = 0
    completed_task_count = 0
    overdue_task_count = 0
    events_with_checklist = 0
    checklist_item_total = 0
    checklist_item_completed_count = 0
    checklist_completion_rates: List[float] = []
    tasks_with_complete_checklist = 0
    tasks_with_incomplete_checklist = 0
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
        if payload.get("time_zone") or payload.get("timezone"):
            events_with_time_zone += 1
        if payload.get("recurrence"):
            events_with_recurrence += 1
        if payload.get("recurrence_frequency"):
            recurrence_frequency_counts[str(payload.get("recurrence_frequency"))] += 1
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
        if payload.get("has_checklist") is True or isinstance(payload.get("checklist_total"), int):
            total = int(payload.get("checklist_total") or 0)
            completed = int(payload.get("checklist_completed") or 0)
            pending = int(payload.get("checklist_pending") or max(total - completed, 0))
            if total > 0:
                events_with_checklist += 1
                checklist_item_total += total
                checklist_item_completed_count += completed
                if isinstance(payload.get("checklist_completion_rate"), (int, float)):
                    checklist_completion_rates.append(float(payload.get("checklist_completion_rate")))
                if pending == 0:
                    tasks_with_complete_checklist += 1
                else:
                    tasks_with_incomplete_checklist += 1
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
        "events_with_time_zone": events_with_time_zone,
        "events_with_recurrence": events_with_recurrence,
        "recurrence_frequency_counts": dict(sorted(recurrence_frequency_counts.items())),
        "events_with_duration_minutes": events_with_duration_minutes,
        "multi_day_event_count": multi_day_event_count,
        "invalid_time_range_count": invalid_time_range_count,
        "completed_task_count": completed_task_count,
        "overdue_task_count": overdue_task_count,
        "events_with_checklist": events_with_checklist,
        "checklist_item_total": checklist_item_total,
        "checklist_item_completed_count": checklist_item_completed_count,
        "checklist_item_pending_count": checklist_item_total - checklist_item_completed_count,
        "average_checklist_completion_rate": round(sum(checklist_completion_rates) / len(checklist_completion_rates), 4)
        if checklist_completion_rates
        else 0,
        "tasks_with_complete_checklist": tasks_with_complete_checklist,
        "tasks_with_incomplete_checklist": tasks_with_incomplete_checklist,
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
    participant_role_event_count = 0
    participant_role_counts: Counter[str] = Counter()
    decision_point_event_count = 0
    decision_point_count = 0
    action_item_event_count = 0
    action_item_count = 0
    risk_item_event_count = 0
    risk_item_count = 0
    mentioned_symbol_event_count = 0
    mentioned_symbol_count = 0
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
        roles = participant_roles_for_payload(payload)
        if roles:
            participant_role_event_count += 1
            participant_role_counts.update(roles)
        if value_present(first_payload_value(payload, ("meeting_url", "url", "link", "source_url", "会议链接"))):
            meeting_url_event_count += 1
        if value_present(first_payload_value(payload, ("attachment", "attachments", "attachment_refs", "file_refs", "files", "附件"))):
            attachment_ref_event_count += 1
        if value_present(first_payload_value(payload, ("recording", "recording_ref", "recording_refs", "recording_url", "录制"))):
            recording_ref_event_count += 1
        if event.get("time") or first_payload_value(payload, ("time", "date", "start_time", "timestamp", "upstream_time", "会议时间")):
            events_with_time += 1
        decision_count = len(meeting_text_items(payload, ("decision_points", "decisions", "conclusions", "结论", "决策点"), ("决策", "决定", "结论", "通过")))
        if decision_count:
            decision_point_event_count += 1
            decision_point_count += decision_count
        action_count = len(meeting_text_items(payload, ("action_items", "actions", "todos", "follow_ups", "next_steps", "待办", "行动项"), ("行动", "待办", "跟进", "下一步", "action", "todo", "follow", "负责", "会后")))
        if action_count:
            action_item_event_count += 1
            action_item_count += action_count
        risk_count = len(meeting_text_items(payload, ("risk_items", "risks", "risk_points", "风险", "风险点"), ("风险", "下行", "回撤", "止损", "高估", "不确定", "警惕")))
        if risk_count:
            risk_item_event_count += 1
            risk_item_count += risk_count
        symbol_count = len(meeting_symbols_for_payload(payload))
        if symbol_count:
            mentioned_symbol_event_count += 1
            mentioned_symbol_count += symbol_count
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
        "participant_role_event_count": participant_role_event_count,
        "participant_role_counts": dict(sorted(participant_role_counts.items())),
        "meeting_url_event_count": meeting_url_event_count,
        "attachment_ref_event_count": attachment_ref_event_count,
        "recording_ref_event_count": recording_ref_event_count,
        "events_with_time": events_with_time,
        "decision_point_event_count": decision_point_event_count,
        "decision_point_count": decision_point_count,
        "action_item_event_count": action_item_event_count,
        "action_item_count": action_item_count,
        "risk_item_event_count": risk_item_event_count,
        "risk_item_count": risk_item_count,
        "mentioned_symbol_event_count": mentioned_symbol_event_count,
        "mentioned_symbol_count": mentioned_symbol_count,
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


def participant_roles_for_payload(payload: Dict[str, Any]) -> List[str]:
    explicit_counts = payload.get("participant_role_counts")
    if isinstance(explicit_counts, dict):
        roles: List[str] = []
        for role, count in explicit_counts.items():
            try:
                roles.extend([str(role)] * int(count))
            except (TypeError, ValueError):
                continue
        return roles
    refs = first_payload_value(payload, ("participant_refs", "participants", "attendees", "speakers", "参会人"))
    names: List[str] = []
    roles = []
    if isinstance(refs, list):
        for item in refs:
            if isinstance(item, dict):
                role = item.get("role") or item.get("title") or item.get("position")
                name = item.get("name") or item.get("display_name") or item.get("username")
                if role:
                    roles.append(normalize_meeting_role(str(role)))
                elif name:
                    names.append(str(name))
            elif item not in (None, ""):
                names.append(str(item))
    elif isinstance(refs, str):
        names.extend(part.strip() for part in re_split_people(refs) if part.strip())
    roles.extend(infer_meeting_role(name) for name in names)
    return [role for role in roles if role]


def normalize_meeting_role(value: str) -> str:
    text = value.strip().lower()
    if any(token in text for token in ("portfolio", "fund", "基金", "组合", "投资经理")):
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
    return "unknown"


def infer_meeting_role(name: str) -> str:
    return normalize_meeting_role(name) if name else "unknown"


def re_split_people(text: str) -> List[str]:
    import re

    return re.split(r"[,，、;；|\n]+", text)


def meeting_text_items(payload: Dict[str, Any], keys: Iterable[str], tokens: Iterable[str]) -> List[str]:
    items: List[str] = []
    for key in keys:
        items.extend(payload_text_values(payload.get(key)))
    body = first_payload_value(payload, ("text_preview", "content_preview", "text", "content", "summary", "minutes", "transcript", "正文", "纪要"))
    if isinstance(body, str):
        lowered_tokens = tuple(token.lower() for token in tokens)
        for segment in meeting_text_segments(body):
            lowered = segment.lower()
            if any(token in lowered for token in lowered_tokens):
                items.append(segment)
    return dedupe_payload_text(items, limit=40)


def payload_text_values(value: Any) -> List[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [part.strip() for part in re_split_lines(value) if part.strip()]
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                item_value = first_payload_value(item, ("text", "title", "content", "name", "summary", "内容"))
            else:
                item_value = item
            if item_value not in (None, ""):
                items.append(str(item_value).strip())
        return items
    if isinstance(value, dict):
        item_value = first_payload_value(value, ("text", "title", "content", "name", "summary", "内容"))
        return [str(item_value).strip()] if item_value not in (None, "") else []
    return [str(value).strip()]


def re_split_lines(text: str) -> List[str]:
    import re

    return re.split(r"[\n;；]+", text)


def meeting_text_segments(text: str) -> List[str]:
    import re

    parts: List[str] = []
    for line in str(text or "").splitlines():
        for segment in re.split(r"[。！？!?；;]", line):
            cleaned = segment.strip(" -\t\r\n")
            if cleaned:
                parts.append(cleaned[:300])
    return parts


def dedupe_payload_text(items: Iterable[str], *, limit: int) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = " ".join(str(item).split()).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned[:300])
        if len(result) >= limit:
            break
    return result


def meeting_symbols_for_payload(payload: Dict[str, Any]) -> List[str]:
    import re

    explicit = payload_text_values(
        payload.get("mentioned_symbols")
        or payload.get("symbols")
        or payload.get("symbol")
        or payload.get("tickers")
        or payload.get("security_code")
        or payload.get("证券代码")
    )
    body = first_payload_value(payload, ("text_preview", "content_preview", "text", "content", "summary", "minutes", "transcript", "title"))
    found = re.findall(r"(?<!\d)(?:[036]\d{5})(?!\d)", str(body or ""))
    return dedupe_payload_text([*explicit, *found], limit=50)


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
