"""Build CollectorX events for WeChat favorites and public-account articles."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import parse_qs, urlparse


COLLECTOR = "wechat-favorites"
DATA_QUALITY_TARGET = "collectorx.data_quality.collection_gaps"
CN_TZ = timezone(timedelta(hours=8))
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "key")
EXPECTED_WECHAT_ACTIONS = ("favorite", "read", "share", "saved_file")
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
WECHAT_FAVORITE_RECOMMENDED_FIELDS = (
    "item_type",
    "action_type",
    "title",
    "source_account",
    "source_account_type",
    "url",
    "article_id",
    "action_time",
    "tags",
    "symbols",
    "favorite_reason",
    "share_target",
    "read_duration_seconds",
    "read_progress",
    "engagement",
    "text_preview",
    "time",
)
TEXT_PREVIEW_MAX_CHARS = 2000


def split_policy_terms(values: Optional[Iterable[str]]) -> List[str]:
    terms: List[str] = []
    for value in values or []:
        for item in re.split(r"[,，;；|\n]+", str(value)):
            cleaned = item.strip()
            if cleaned:
                terms.append(cleaned)
    return terms


def build_wechat_favorites_scope_policy(
    *,
    allow_source_accounts: Optional[Iterable[str]] = None,
    deny_source_accounts: Optional[Iterable[str]] = None,
    allow_source_account_types: Optional[Iterable[str]] = None,
    deny_source_account_types: Optional[Iterable[str]] = None,
    allow_actions: Optional[Iterable[str]] = None,
    deny_actions: Optional[Iterable[str]] = None,
    allow_tags: Optional[Iterable[str]] = None,
    deny_tags: Optional[Iterable[str]] = None,
    allow_domains: Optional[Iterable[str]] = None,
    deny_domains: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "allow_source_accounts": split_policy_terms(allow_source_accounts),
        "deny_source_accounts": split_policy_terms(deny_source_accounts),
        "allow_source_account_types": split_policy_terms(allow_source_account_types),
        "deny_source_account_types": split_policy_terms(deny_source_account_types),
        "allow_actions": split_policy_terms(allow_actions),
        "deny_actions": split_policy_terms(deny_actions),
        "allow_tags": split_policy_terms(allow_tags),
        "deny_tags": split_policy_terms(deny_tags),
        "allow_domains": split_policy_terms(allow_domains),
        "deny_domains": split_policy_terms(deny_domains),
        "allow_keywords": split_policy_terms(allow_keywords),
        "deny_keywords": split_policy_terms(deny_keywords),
        "filtered_record_count": 0,
        "filter_reason_counts": {},
        "policy_does_not_assert_investment_relevance": True,
    }
    policy["enabled"] = any(
        policy[key]
        for key in (
            "allow_source_accounts",
            "deny_source_accounts",
            "allow_source_account_types",
            "deny_source_account_types",
            "allow_actions",
            "deny_actions",
            "allow_tags",
            "deny_tags",
            "allow_domains",
            "deny_domains",
            "allow_keywords",
            "deny_keywords",
        )
    )
    return policy


def wechat_favorites_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy or not policy.get("enabled"):
        return None
    if policy.get("deny_source_accounts") and policy_hit(policy["deny_source_accounts"], wechat_account_surface(event)):
        return "source_account_denied"
    if policy.get("allow_source_accounts") and not policy_hit(policy["allow_source_accounts"], wechat_account_surface(event)):
        return "source_account_not_allowed"
    if policy.get("deny_source_account_types") and policy_hit(policy["deny_source_account_types"], wechat_account_type_surface(event)):
        return "source_account_type_denied"
    if policy.get("allow_source_account_types") and not policy_hit(policy["allow_source_account_types"], wechat_account_type_surface(event)):
        return "source_account_type_not_allowed"
    if policy.get("deny_actions") and policy_hit(policy["deny_actions"], wechat_action_surface(event)):
        return "action_denied"
    if policy.get("allow_actions") and not policy_hit(policy["allow_actions"], wechat_action_surface(event)):
        return "action_not_allowed"
    if policy.get("deny_tags") and policy_hit(policy["deny_tags"], wechat_tag_surface(event)):
        return "tag_denied"
    if policy.get("allow_tags") and not policy_hit(policy["allow_tags"], wechat_tag_surface(event)):
        return "tag_not_allowed"
    if policy.get("deny_domains") and policy_hit(policy["deny_domains"], wechat_domain_surface(event)):
        return "domain_denied"
    if policy.get("allow_domains") and not policy_hit(policy["allow_domains"], wechat_domain_surface(event)):
        return "domain_not_allowed"
    if policy.get("deny_keywords") and policy_hit(policy["deny_keywords"], wechat_keyword_surface(event)):
        return "keyword_denied"
    if policy.get("allow_keywords") and not policy_hit(policy["allow_keywords"], wechat_keyword_surface(event)):
        return "keyword_not_allowed"
    return None


def finalize_wechat_favorites_scope_policy_audit(audit: Dict[str, Any]) -> Dict[str, Any]:
    policy = audit.get("wechat_favorites_scope_policy") or {}
    if policy:
        policy["filter_reason_counts"] = dict(sorted((policy.get("filter_reason_counts") or {}).items()))
    audit["scope_policy_filtered_record_count"] = int(policy.get("filtered_record_count") or 0)
    audit["scope_policy_filter_reason_counts"] = policy.get("filter_reason_counts") or {}
    candidate_count = int(audit.get("candidate_record_count") or 0)
    emitted_count = int(audit.get("wechat_favorite_event_count", audit.get("emitted_event_count") or 0) or 0)
    audit["wechat_favorites_scope_policy_filtered_all"] = bool(
        policy.get("enabled")
        and candidate_count > 0
        and int(policy.get("filtered_record_count") or 0) == candidate_count
        and emitted_count == 0
    )
    return audit


def wechat_account_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    return [data.get("source_account"), raw_ref.get("source_account")]


def wechat_account_type_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    return [data.get("source_account_type"), raw_ref.get("source_account_type")]


def wechat_action_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    return [data.get("action_type"), data.get("item_type")]


def wechat_tag_surface(event: Dict[str, Any]) -> List[Any]:
    return list((event.get("data") or {}).get("tags") or [])


def wechat_domain_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    return [host_for(data.get("url")), host_for(raw_ref.get("url"))]


def wechat_keyword_surface(event: Dict[str, Any]) -> List[Any]:
    data = event.get("data") or {}
    raw_ref = event.get("raw_ref") or {}
    surface: List[Any] = [
        data.get("title"),
        data.get("source_account"),
        data.get("url"),
        data.get("article_id"),
        data.get("favorite_reason"),
        data.get("share_target"),
        data.get("text_preview"),
        raw_ref.get("path"),
        raw_ref.get("archive_member"),
    ]
    for key in ("tags", "symbols", "engagement"):
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


def host_for(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    host = urlparse(str(url)).netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    return host.split(":", 1)[0] or None


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def favorite_to_event(
    record: Dict[str, Any],
    *,
    path: Path,
    row: int,
    collected_at: Optional[str] = None,
) -> Dict[str, Any]:
    path_label = first(record, ["path", "file", "source_path"]) or str(path)
    title = first(record, ["title", "name", "subject", "标题", "文章标题"]) or Path(path_label).stem
    url = first(record, ["url", "link", "href", "article_url", "原文链接", "链接"])
    account = first(record, ["source_account", "account", "author", "publisher", "公众号", "作者", "来源"])
    account_type = first(record, ["source_account_type", "account_type", "公众号类型", "来源类型"]) or source_account_type_for(account)
    action_type = normalize_action(first(record, ["action_type", "action", "event", "type", "动作", "行为"]) or infer_action(record, path))
    item_type = first(record, ["item_type", "content_type", "kind", "类型"]) or infer_item_type(record, path)
    action_time = first(record, ["saved_at", "favorited_at", "read_at", "shared_at", "time", "date", "created_at", "收藏时间", "阅读时间", "转发时间", "时间"])
    text = first(record, ["text", "content", "body", "summary", "abstract", "note", "正文", "内容", "摘要", "备注"]) or ""
    tags = tags_for(record)
    article_id = first(record, ["article_id", "mid", "msgid", "文章ID", "文章编号"]) or article_id_from_url(url)
    share_target = first(record, ["share_target", "shared_to", "to", "receiver", "转发对象", "分享给"])
    favorite_reason = first(record, ["favorite_reason", "reason", "note", "comment", "收藏理由", "收藏备注", "备注"])
    read_duration_seconds = int_value(
        first(record, ["read_duration_seconds", "read_duration", "duration_seconds", "duration", "阅读时长", "停留时长", "阅读秒数"])
    )
    read_progress = progress_value(first(record, ["read_progress", "progress", "read_percent", "阅读进度", "阅读比例"]))
    symbols = symbols_for(record, title=title, text=text, url=url)
    engagement = engagement_for(record)
    collection_time = collected_at or now_iso()
    event_time = action_time or collection_time
    data = {
        "item_type": item_type,
        "action_type": action_type,
        "title": title,
        "source_account": account,
        "source_account_type": account_type,
        "url": url,
        "article_id": article_id,
        "action_time": action_time,
        "tags": tags,
        "symbols": symbols,
        "favorite_reason": favorite_reason,
        "share_target": share_target,
        "read_duration_seconds": read_duration_seconds,
        "read_progress": read_progress,
        "engagement": engagement,
        "text_preview": text[:TEXT_PREVIEW_MAX_CHARS],
        "has_text": bool(text),
        "text_length": len(text),
        "raw": sanitized(record),
    }
    data = {key: value for key, value in data.items() if value not in (None, "", [], {})}
    raw_ref = {
        "path": path_label,
        "row": row,
        "url": url,
        "source_account": account,
        "source_account_type": account_type,
        "article_id": article_id,
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [], {})}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_label, row, title, url, action_time or event_time, action_type),
        "collector": COLLECTOR,
        "source": "微信收藏/公众号文章",
        "owner_scope": "personal",
        "kind": "file",
        "time": event_time,
        "collected_at": collection_time,
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message"],
        },
        "wiki_targets": ["internal.knowledge.saved_articles"],
    }


def gap_event(
    *,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_time = collected_at or now_iso()
    audit = collection_audit or {}
    policy = audit.get("wechat_favorites_scope_policy") or {}
    status_by_reason = {
        "wechat_favorites_scope_policy_filtered_all": "scope_policy_filtered_all",
        "wechat_favorites_input_missing": "needs_wechat_favorites_input",
        "wechat_favorites_no_readable_records": "no_readable_wechat_favorites_records",
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "微信收藏授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": event_time,
        "collected_at": event_time,
        "data": {
            "subtype": "collector_gap",
            "action_type": "collector_gap",
            "gap": reason,
            "status": status_by_reason.get(reason, reason),
            "profile_type": "wechat_favorites_collection_gap",
            "message": gap_message(reason),
            "candidate_record_count": int(audit.get("candidate_record_count") or 0),
            "parsed_record_count": int(audit.get("parsed_record_count") or 0),
            "wechat_favorite_event_count": 0,
            "scope_policy_filtered_record_count": int(
                audit.get("scope_policy_filtered_record_count")
                or policy.get("filtered_record_count")
                or 0
            ),
            "scope_policy_filter_reason_counts": (
                audit.get("scope_policy_filter_reason_counts")
                or policy.get("filter_reason_counts")
                or {}
            ),
            "wechat_favorites_scope_policy_filtered_all": bool(
                audit.get("wechat_favorites_scope_policy_filtered_all")
            ),
            "policy_is_user_authorization_scope": bool(policy.get("enabled")),
            "policy_does_not_assert_investment_relevance": True,
            "business_records_written": False,
            "read_only": True,
            "collector_writes_investor_wiki_directly": False,
            "can_feed_wechat_article_favorites_lens": False,
            "public_account_full_crawl_claimed": False,
            "public_article_body_mirrored": False,
        },
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "scope_policy_enabled": bool(policy.get("enabled")),
        },
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["personal_message", "collection_gap"],
        },
        "wiki_targets": [DATA_QUALITY_TARGET],
    }


def gap_message(reason: str) -> str:
    messages = {
        "wechat_favorites_scope_policy_filtered_all": "All user-authorized WeChat favorites/article records were excluded by the authorization scope policy.",
        "wechat_favorites_input_missing": "No user-authorized WeChat favorites or public-account article export was provided.",
        "wechat_favorites_no_readable_records": "The authorized WeChat favorites input did not contain readable favorite or article records.",
    }
    return messages.get(reason, "WeChat favorites collection produced a traceable data-quality gap.")


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = usable_wechat_favorite_events(events)
    wechat_favorite_event_count = len(usable_events)
    favorite_event_count = sum(1 for event in usable_events if (event.get("data") or {}).get("action_type") == "favorite")
    gap_event_count = len(events) - wechat_favorite_event_count
    can_enter_wechat_favorites_lake = wechat_favorite_event_count > 0 and not bool(
        (collection_audit or {}).get("wechat_favorites_scope_policy_filtered_all")
    )
    kind_counts = Counter(event["kind"] for event in events)
    action_counts = Counter((event.get("data") or {}).get("action_type", "unknown") for event in usable_events)
    item_counts = Counter((event.get("data") or {}).get("item_type", "unknown") for event in usable_events)
    source_accounts = {
        str((event.get("data") or {}).get("source_account"))
        for event in usable_events
        if (event.get("data") or {}).get("source_account")
    }
    gap_only = bool(events) and wechat_favorite_event_count == 0 and gap_event_count == len(events)
    scope_policy_filtered_all = bool((collection_audit or {}).get("wechat_favorites_scope_policy_filtered_all"))
    no_events = not events
    gap_reason = next(((event.get("data") or {}).get("gap") for event in events if (event.get("data") or {}).get("gap")), None)
    observed_actions = sorted(action for action, count in action_counts.items() if count and action != "unknown")
    observed_expected = [action for action in EXPECTED_WECHAT_ACTIONS if action_counts.get(action)]
    missing_expected = [action for action in EXPECTED_WECHAT_ACTIONS if not action_counts.get(action)]
    unknown_action_count = sum(count for action, count in action_counts.items() if action not in EXPECTED_WECHAT_ACTIONS)
    return {
        "schema": "collectorx.wechat_favorites.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "usable_event_count": wechat_favorite_event_count,
        "wechat_favorite_event_count": wechat_favorite_event_count,
        "favorite_event_count": favorite_event_count,
        "gap_event_count": gap_event_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "action_type_counts": dict(sorted(action_counts.items())),
        "item_type_counts": dict(sorted(item_counts.items())),
        "source_account_count": len(source_accounts),
        "action_coverage": {
            "expected_p1_actions": list(EXPECTED_WECHAT_ACTIONS),
            "observed_actions": observed_actions,
            "observed_expected_actions": observed_expected,
            "missing_expected_actions": missing_expected,
            "action_type_counts": dict(sorted(action_counts.items())),
            "unknown_action_count": unknown_action_count,
            "real_account_validation": False,
        },
        "field_coverage": field_coverage(events),
        "article_surface_summary": article_surface_summary(events),
        "article_behavior_summary": article_behavior_summary(events),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "content_policy": {
            "full_public_account_crawl": False,
            "full_content_included_by_default": False,
            "text_preview_max_chars": TEXT_PREVIEW_MAX_CHARS,
            "investment_article_classification_done": False,
        },
        "evidence_policy": {
            "generic_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "investment_article_classification_done": False,
            "required_lens": "wechat-article-favorites",
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": wechat_favorites_readiness_status(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
                gap_reason=gap_reason,
            ),
            "usable_event_count": wechat_favorite_event_count,
            "wechat_favorite_event_count": wechat_favorite_event_count,
            "favorite_event_count": favorite_event_count,
            "gap_event_count": gap_event_count,
            "can_enter_finclaw": can_enter_wechat_favorites_lake,
            "can_enter_wechat_favorites_lake": can_enter_wechat_favorites_lake,
            "can_enter_data_quality_lake": gap_event_count > 0,
            "can_feed_wechat_article_favorites_lens": can_enter_wechat_favorites_lake,
            "can_feed_investor_wiki_directly": False,
            "can_claim_investment_article_favorites": False,
            "source_collection_scope": wechat_favorites_source_collection_scope(
                gap_only=gap_only,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "action_coverage_status": action_coverage_status(events, missing_expected),
            "next_action": wechat_favorites_next_action(
                gap_only=gap_only,
                scope_policy_filtered_all=scope_policy_filtered_all,
                gap_reason=gap_reason,
            ),
        },
    }


def wechat_favorites_readiness_status(
    *,
    gap_only: bool,
    no_events: bool,
    scope_policy_filtered_all: bool,
    gap_reason: Optional[str],
) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_filtered_all"
    if gap_only and gap_reason == "wechat_favorites_no_readable_records":
        return "no_readable_wechat_favorites_records"
    if gap_only:
        return "needs_wechat_favorites_input"
    if no_events:
        return "records_empty"
    return "events_collected"


def wechat_favorites_source_collection_scope(*, gap_only: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_excluded_all"
    if gap_only:
        return "none"
    return "partial_authorized_input"


def wechat_favorites_next_action(
    *,
    gap_only: bool,
    scope_policy_filtered_all: bool,
    gap_reason: Optional[str],
) -> str:
    if scope_policy_filtered_all:
        return "Broaden WeChat favorites scope policy or provide authorized article records inside the allowed scope."
    if gap_only and gap_reason == "wechat_favorites_no_readable_records":
        return "Provide a readable WeChat favorites/public-account article export in JSON, CSV, HTML, Markdown, text, or ZIP format."
    if gap_only:
        return "Provide authorized WeChat favorites or public-account article exports."
    return "Feed events into wechat-article-favorites lens."


def action_coverage_status(events: List[Dict[str, Any]], missing_expected: List[str]) -> str:
    if not events or all((event.get("data") or {}).get("gap") for event in events):
        return "no_action_observed"
    if not missing_expected:
        return "all_expected_actions_observed"
    return "partial_expected_actions_observed"


def field_coverage(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    favorite_events = usable_wechat_favorite_events(events)
    field_counts = {
        field: sum(1 for event in favorite_events if favorite_field_present(event, field))
        for field in WECHAT_FAVORITE_RECOMMENDED_FIELDS
    }
    return {
        "recommended_fields": list(WECHAT_FAVORITE_RECOMMENDED_FIELDS),
        "field_counts": dict(sorted(field_counts.items())),
        "missing_recommended_fields": [field for field, count in field_counts.items() if count == 0],
        "events_with_text": sum(1 for event in favorite_events if (event.get("data") or {}).get("has_text")),
    }


def favorite_field_present(event: Dict[str, Any], field: str) -> bool:
    if field == "time":
        return bool(event.get("time"))
    value = (event.get("data") or {}).get(field)
    return value not in (None, "", [], {})


def article_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    favorite_events = usable_wechat_favorite_events(events)
    source_account_type_counts = Counter(
        str((event.get("data") or {}).get("source_account_type"))
        for event in favorite_events
        if (event.get("data") or {}).get("source_account_type")
    )
    symbols = {
        str(symbol)
        for event in favorite_events
        for symbol in ((event.get("data") or {}).get("symbols") or [])
        if symbol not in (None, "")
    }
    return {
        "article_event_count": len(favorite_events),
        "events_with_url": sum(1 for event in favorite_events if (event.get("data") or {}).get("url")),
        "events_with_source_account": sum(1 for event in favorite_events if (event.get("data") or {}).get("source_account")),
        "events_with_source_account_type": sum(1 for event in favorite_events if (event.get("data") or {}).get("source_account_type")),
        "events_with_article_id": sum(1 for event in favorite_events if (event.get("data") or {}).get("article_id")),
        "events_with_tags": sum(1 for event in favorite_events if (event.get("data") or {}).get("tags")),
        "events_with_text": sum(1 for event in favorite_events if (event.get("data") or {}).get("has_text")),
        "events_with_symbols": sum(1 for event in favorite_events if (event.get("data") or {}).get("symbols")),
        "symbol_count": len(symbols),
        "source_account_type_counts": dict(sorted(source_account_type_counts.items())),
        "public_account_article_count": sum(
            1
            for event in favorite_events
            if (event.get("data") or {}).get("item_type") == "public_account_article"
        ),
    }


def article_behavior_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    favorite_events = usable_wechat_favorite_events(events)
    durations = [
        int((event.get("data") or {}).get("read_duration_seconds"))
        for event in favorite_events
        if (event.get("data") or {}).get("read_duration_seconds") not in (None, "")
    ]
    progress_values = [
        float((event.get("data") or {}).get("read_progress"))
        for event in favorite_events
        if (event.get("data") or {}).get("read_progress") not in (None, "")
    ]
    return {
        "events_with_favorite_reason": sum(1 for event in favorite_events if (event.get("data") or {}).get("favorite_reason")),
        "events_with_share_target": sum(1 for event in favorite_events if (event.get("data") or {}).get("share_target")),
        "events_with_read_duration": len(durations),
        "events_with_read_progress": len(progress_values),
        "events_with_engagement": sum(1 for event in favorite_events if (event.get("data") or {}).get("engagement")),
        "events_with_symbols": sum(1 for event in favorite_events if (event.get("data") or {}).get("symbols")),
        "average_read_duration_seconds": round(sum(durations) / len(durations), 2) if durations else None,
        "average_read_progress": round(sum(progress_values) / len(progress_values), 4) if progress_values else None,
    }


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    audit = {
        "source_ref_count": sum(
            1
            for event in events
            if (event.get("raw_ref") or {}).get("path") or (event.get("raw_ref") or {}).get("url")
        ),
        "archive_member_event_count": sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "archive_path_traversal_members_collected": False,
    }
    if collection_audit:
        audit.update(collection_audit)
        audit["usable_event_count"] = len(usable_wechat_favorite_events(events))
        audit["wechat_favorite_event_count"] = len(usable_wechat_favorite_events(events))
        audit["gap_event_count"] = len(events) - len(usable_wechat_favorite_events(events))
        audit["source_ref_count"] = max(
            int(audit.get("source_ref_count") or 0),
            sum(1 for event in events if (event.get("raw_ref") or {}).get("path") or (event.get("raw_ref") or {}).get("url")),
        )
        audit["archive_member_event_count"] = max(
            int(audit.get("archive_member_event_count") or 0),
            sum(1 for event in events if (event.get("raw_ref") or {}).get("archive_member")),
        )
        audit["archive_path_traversal_members_collected"] = False
        audit["windows_drive_archive_members_collected"] = False
    return audit


def usable_wechat_favorite_events(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("collector") == COLLECTOR
        and event.get("kind") == "file"
        and not (event.get("data") or {}).get("gap")
        and (event.get("data") or {}).get("action_type") != "collector_gap"
    ]


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
        f"- usable_event_count: {manifest['usable_event_count']}",
        f"- wechat_favorite_event_count: {manifest['wechat_favorite_event_count']}",
        f"- gap_event_count: {manifest['gap_event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- wechat_favorites_lake_ready: `{manifest['collection_readiness']['can_enter_wechat_favorites_lake']}`",
        f"- data_quality_lake_ready: `{manifest['collection_readiness']['can_enter_data_quality_lake']}`",
        f"- article_favorites_lens_ready: `{manifest['collection_readiness']['can_feed_wechat_article_favorites_lens']}`",
        f"- investor_wiki_direct_ready: `{manifest['collection_readiness']['can_feed_investor_wiki_directly']}`",
        f"- observed_actions: `{', '.join(manifest['action_coverage']['observed_actions']) or 'none'}`",
        f"- missing_expected_actions: `{', '.join(manifest['action_coverage']['missing_expected_actions']) or 'none'}`",
        f"- field_coverage_missing: `{', '.join(manifest['field_coverage']['missing_recommended_fields']) or 'none'}`",
        f"- behavior_fields: favorite_reason={manifest['article_behavior_summary']['events_with_favorite_reason']}, "
        f"read_progress={manifest['article_behavior_summary']['events_with_read_progress']}, "
        f"share_target={manifest['article_behavior_summary']['events_with_share_target']}",
        f"- archive_member_events: {manifest['source_audit']['archive_member_event_count']}",
        f"- skipped_archive_members: {manifest['source_audit'].get('skipped_archive_member_count', 0)}",
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


def source_account_type_for(source_account: Optional[str]) -> Optional[str]:
    if not source_account:
        return None
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


def article_id_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(str(url))
    if parsed.netloc.endswith("mp.weixin.qq.com"):
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == "s":
            return path_parts[1]
        query = parse_qs(parsed.query)
        for key in ("mid", "sn", "__biz"):
            values = query.get(key)
            if values:
                return values[0]
    return None


def int_value(value: Optional[str]) -> Optional[int]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    if "小时" in text or "hour" in text.lower():
        number *= 3600
    elif "分钟" in text or "min" in text.lower():
        number *= 60
    return max(0, int(round(number)))


def progress_value(value: Optional[str]) -> Optional[float]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    if "%" in text or number > 1:
        number /= 100
    return round(min(max(number, 0.0), 1.0), 4)


def symbols_for(record: Dict[str, Any], *, title: str, text: str, url: Optional[str]) -> List[str]:
    values: List[str] = []
    for key in ("symbols", "symbol", "ticker", "tickers", "security_code", "code", "证券代码", "股票代码", "基金代码", "标的代码"):
        values.extend(text_values(record.get(key)))
    body = " ".join([title or "", text or "", str(url or "")])
    values.extend(re.findall(r"(?<!\d)(?:[036]\d{5})(?!\d)", body))
    return dedupe(values, limit=50)


def engagement_for(record: Dict[str, Any]) -> Dict[str, int]:
    mapping = {
        "read_count": ("read_count", "view_count", "阅读数", "浏览数"),
        "like_count": ("like_count", "likes", "点赞数", "在看数"),
        "favorite_count": ("favorite_count", "收藏数"),
        "share_count": ("share_count", "转发数", "分享数"),
        "comment_count": ("comment_count", "comments", "评论数"),
    }
    raw_engagement = record.get("engagement") if isinstance(record.get("engagement"), dict) else {}
    result: Dict[str, int] = {}
    for normalized_key, keys in mapping.items():
        value = None
        for key in keys:
            value = raw_engagement.get(key) if key in raw_engagement else record.get(key)
            if value not in (None, ""):
                break
        parsed = int_value(str(value)) if value not in (None, "") else None
        if parsed is not None:
            result[normalized_key] = parsed
    return result


def text_values(value: Any) -> List[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, dict):
        result: List[str] = []
        for item in value.values():
            result.extend(text_values(item))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            result.extend(text_values(item))
        return result
    return [part.strip() for part in re.split(r"[,，、\s]+", str(value)) if part.strip()]


def dedupe(values: Iterable[str], *, limit: int) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


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
