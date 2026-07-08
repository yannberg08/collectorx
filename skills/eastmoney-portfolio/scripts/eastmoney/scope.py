"""Authorization scope policy for EastMoney investor events."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


EASTMONEY_SCOPE_POLICY_KEYS = (
    "allow_event_kinds",
    "deny_event_kinds",
    "allow_symbols",
    "deny_symbols",
    "allow_accounts",
    "deny_accounts",
    "allow_sources",
    "deny_sources",
    "allow_keywords",
    "deny_keywords",
)


STANDARD_KIND_BY_SOURCE = {
    "watchlist": "watchlist",
    "recent_stock": "watchlist",
    "stock_note": "note",
    "chart_drawing": "note",
    "broker_asset_snapshot": "holding",
    "broker_position_detail": "holding",
    "broker_trade_execution": "trade",
    "broker_entrust_order": "trade",
    "broker_fund_flow": "trade",
}


def build_eastmoney_scope_policy(
    *,
    allow_event_kinds: Optional[Sequence[str]] = None,
    deny_event_kinds: Optional[Sequence[str]] = None,
    allow_symbols: Optional[Sequence[str]] = None,
    deny_symbols: Optional[Sequence[str]] = None,
    allow_accounts: Optional[Sequence[str]] = None,
    deny_accounts: Optional[Sequence[str]] = None,
    allow_sources: Optional[Sequence[str]] = None,
    deny_sources: Optional[Sequence[str]] = None,
    allow_keywords: Optional[Sequence[str]] = None,
    deny_keywords: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "enabled": False,
        "allow_event_kinds": normalize_lower_terms(allow_event_kinds),
        "deny_event_kinds": normalize_lower_terms(deny_event_kinds),
        "allow_symbols": normalize_symbol_terms(allow_symbols),
        "deny_symbols": normalize_symbol_terms(deny_symbols),
        "allow_accounts": split_patterns(allow_accounts),
        "deny_accounts": split_patterns(deny_accounts),
        "allow_sources": split_patterns(allow_sources),
        "deny_sources": split_patterns(deny_sources),
        "allow_keywords": split_patterns(allow_keywords),
        "deny_keywords": split_patterns(deny_keywords),
        "candidate_event_count": 0,
        "retained_event_count": 0,
        "filtered_event_count": 0,
        "filter_reason_counts": {},
        "filtered_all": False,
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "exact_business_numbers_preserved": True,
        "read_only": True,
    }
    policy["enabled"] = any(policy.get(key) for key in EASTMONEY_SCOPE_POLICY_KEYS)
    return policy


def default_eastmoney_scope_audit(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    event_list = list(events)
    policy = build_eastmoney_scope_policy()
    policy["candidate_event_count"] = len(event_list)
    policy["retained_event_count"] = len(event_list)
    return {
        "eastmoney_scope_policy": policy,
        "eastmoney_scope_policy_filtered_all": False,
    }


def filter_events_with_scope(
    events: Iterable[Dict[str, Any]],
    scope_policy: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    policy = deepcopy(scope_policy or build_eastmoney_scope_policy())
    retained: List[Dict[str, Any]] = []
    counts: Counter[str] = Counter()
    event_list = list(events)
    policy["candidate_event_count"] = len(event_list)

    if not policy.get("enabled"):
        policy["retained_event_count"] = len(event_list)
        return event_list, {
            "eastmoney_scope_policy": policy,
            "eastmoney_scope_policy_filtered_all": False,
        }

    for event in event_list:
        allowed, match = eastmoney_scope_policy_match(event, policy)
        if allowed:
            updated = deepcopy(event)
            data = updated.setdefault("data", {})
            if isinstance(data, dict):
                data["eastmoney_scope_policy"] = match
            retained.append(updated)
            continue
        reason = str(match.get("reason") or "scope_policy_filtered")
        counts[reason] += 1

    policy["retained_event_count"] = len(retained)
    policy["filtered_event_count"] = len(event_list) - len(retained)
    policy["filter_reason_counts"] = dict(sorted(counts.items()))
    policy["filtered_all"] = bool(event_list) and not retained
    return retained, {
        "eastmoney_scope_policy": policy,
        "eastmoney_scope_policy_filtered_all": bool(policy["filtered_all"]),
    }


def eastmoney_scope_policy_match(event: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not policy.get("enabled"):
        return True, {"enabled": False}

    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    raw_ref = event.get("raw_ref") if isinstance(event.get("raw_ref"), dict) else {}
    kind_terms = event_kind_terms(event, data)
    symbol = event_symbol(data)
    account_surface = account_policy_surface(data)
    source_surface = source_policy_surface(event, data, raw_ref)
    keyword_surface = "\n".join(
        [
            source_surface,
            account_surface,
            symbol,
            "\n".join(flatten_values(data)),
            "\n".join(flatten_values(raw_ref)),
        ]
    ).lower()

    deny_kind = first_exact_any(policy.get("deny_event_kinds", []), kind_terms)
    if deny_kind:
        return False, {"enabled": True, "allowed": False, "reason": "deny_event_kind", "matched_pattern": deny_kind}
    allow_kinds = policy.get("allow_event_kinds", [])
    allow_kind = first_exact_any(allow_kinds, kind_terms)
    if allow_kinds and not allow_kind:
        return False, {"enabled": True, "allowed": False, "reason": "allow_event_kind_not_matched"}

    deny_symbol = first_symbol_hit(policy.get("deny_symbols", []), symbol)
    if deny_symbol:
        return False, {"enabled": True, "allowed": False, "reason": "deny_symbol", "matched_pattern": deny_symbol}
    allow_symbols = policy.get("allow_symbols", [])
    allow_symbol = first_symbol_hit(allow_symbols, symbol)
    if allow_symbols and not allow_symbol:
        return False, {"enabled": True, "allowed": False, "reason": "allow_symbol_not_matched", "symbol": symbol}

    deny_account = first_pattern_hit(policy.get("deny_accounts", []), account_surface)
    if deny_account:
        return False, {"enabled": True, "allowed": False, "reason": "deny_account", "matched_pattern": deny_account}
    allow_accounts = policy.get("allow_accounts", [])
    allow_account = first_pattern_hit(allow_accounts, account_surface)
    if allow_accounts and not allow_account:
        return False, {"enabled": True, "allowed": False, "reason": "allow_account_not_matched"}

    deny_source = first_pattern_hit(policy.get("deny_sources", []), source_surface)
    if deny_source:
        return False, {"enabled": True, "allowed": False, "reason": "deny_source", "matched_pattern": deny_source}
    allow_sources = policy.get("allow_sources", [])
    allow_source = first_pattern_hit(allow_sources, source_surface)
    if allow_sources and not allow_source:
        return False, {"enabled": True, "allowed": False, "reason": "allow_source_not_matched"}

    deny_keyword = first_pattern_hit(policy.get("deny_keywords", []), keyword_surface)
    if deny_keyword:
        return False, {"enabled": True, "allowed": False, "reason": "deny_keyword", "matched_pattern": deny_keyword}
    allow_keywords = policy.get("allow_keywords", [])
    allow_keyword = first_pattern_hit(allow_keywords, keyword_surface)
    if allow_keywords and not allow_keyword:
        return False, {"enabled": True, "allowed": False, "reason": "allow_keyword_not_matched"}

    return True, {
        "enabled": True,
        "allowed": True,
        "matched_allow_event_kind": allow_kind,
        "matched_allow_symbol": allow_symbol,
        "matched_allow_account": allow_account,
        "matched_allow_source": allow_source,
        "matched_allow_keyword": allow_keyword,
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "exact_business_numbers_preserved": True,
    }


def event_kind_terms(event: Dict[str, Any], data: Dict[str, Any]) -> List[str]:
    source_kind = str(event.get("kind") or data.get("source_kind") or "").lower()
    standard_kind = STANDARD_KIND_BY_SOURCE.get(source_kind, source_kind)
    terms = [source_kind, standard_kind]
    if data.get("source_kind"):
        terms.append(str(data.get("source_kind")).lower())
    return stable_unique(term for term in terms if term)


def event_symbol(data: Dict[str, Any]) -> str:
    for key in ("symbol", "code", "stock_code", "证券代码"):
        value = data.get(key)
        if value not in (None, ""):
            return normalize_symbol(str(value))
    return ""


def account_policy_surface(data: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in (
        "account_id",
        "fund_account",
        "shareholder_account",
        "shareholder_account_id",
        "account_label",
        "account_suffix",
        "account_display_hash",
    ):
        parts.extend(flatten_values(data.get(key)))
    return "\n".join(parts).lower()


def source_policy_surface(event: Dict[str, Any], data: Dict[str, Any], raw_ref: Dict[str, Any]) -> str:
    parts: List[str] = [
        str(event.get("source") or ""),
        str(event.get("kind") or ""),
        *event_kind_terms(event, data),
    ]
    for key in ("path_redacted", "capture_method", "ui_tab", "file_sha256", "row", "container"):
        if raw_ref.get(key) not in (None, ""):
            parts.append(str(raw_ref.get(key)))
    for key in ("source_kind", "snapshot_type", "evidence_level", "status", "profile_type", "gap"):
        if data.get(key) not in (None, ""):
            parts.append(str(data.get(key)))
    return "\n".join(parts).lower()


def split_patterns(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return stable_unique(out)


def normalize_lower_terms(values: Optional[Sequence[str]]) -> List[str]:
    return stable_unique(value.lower().strip() for value in split_patterns(values) if value.strip())


def normalize_symbol_terms(values: Optional[Sequence[str]]) -> List[str]:
    return stable_unique(normalize_symbol(value) for value in split_patterns(values) if value.strip())


def normalize_symbol(value: str) -> str:
    return value.strip().upper().split(".", 1)[0]


def stable_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def first_exact_any(patterns: Iterable[str], values: Iterable[str]) -> Optional[str]:
    normalized_values = {str(value).lower().strip() for value in values}
    for pattern in patterns:
        if pattern.lower().strip() in normalized_values:
            return pattern
    return None


def first_symbol_hit(patterns: Iterable[str], value: str) -> Optional[str]:
    normalized = normalize_symbol(value)
    for pattern in patterns:
        if normalize_symbol(pattern) == normalized:
            return pattern
    return None


def first_pattern_hit(patterns: Iterable[str], surface: str) -> Optional[str]:
    lowered = surface.lower()
    for pattern in patterns:
        if pattern.lower() in lowered:
            return pattern
    return None


def flatten_values(value: Any) -> List[str]:
    parts: List[str] = []
    if value in (None, ""):
        return parts
    if isinstance(value, (str, int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"password", "token", "cookie", "authorization", "session", "secret", "sign"}:
                continue
            parts.append(str(key))
            parts.extend(flatten_values(item))
        return parts
    if isinstance(value, (list, tuple, set)):
        for item in list(value)[:100]:
            parts.extend(flatten_values(item))
        return parts
    return [str(value)]
