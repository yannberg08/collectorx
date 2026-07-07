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


def build_manifest(source_id: str, events: List[Dict[str, Any]], *, collected_at: Optional[str] = None) -> Dict[str, Any]:
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
        "collection_readiness": {
            "status": status,
            "can_enter_finclaw": bool(events) and not only_gap,
            "can_claim_complete_source_collection": not only_gap,
            "next_action": next_action_for_status(status),
        },
        "privacy": {
            "local_only": True,
            "sensitive": True,
            "contains": profile.get("contains", []),
        },
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
            "usable_for_wiki_now": [
                child["subdimension_id"]
                for dimension in dimensions
                for child in dimension["children"]
                if child["support_level"] in {"strong", "medium"}
            ],
        },
    }


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
