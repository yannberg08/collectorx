"""Investor Wiki evidence contract helpers.

Collectors should emit local evidence packages first. SoulMirror/FinClaw owns
the final Wiki writing step, but these helpers keep the package shape stable.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


EVIDENCE_SCHEMA = "finclaw.investor_wiki_evidence.v1"
EVENT_SCHEMA = "collectorx.event.v1"
SOULMIRROR_TARGET_SCHEMA = "external.investor / 7 dimensions / 20 subdimensions"

INVESTOR_DIMENSIONS: List[Dict[str, Any]] = [
    {
        "dimension_id": "inv-philosophy",
        "dimension_name": "投资哲学与信念",
        "children": [
            ("inv-market-view", "市场观"),
            ("inv-risk-view", "风险观"),
            ("inv-value-preference", "价值偏好"),
        ],
    },
    {
        "dimension_id": "inv-circle",
        "dimension_name": "能力圈定义",
        "children": [
            ("inv-industry-circle", "行业能力圈"),
            ("inv-analysis-ability", "分析能力"),
            ("inv-information-learning-style", "信息处理与学习风格"),
        ],
    },
    {
        "dimension_id": "inv-style",
        "dimension_name": "投资风格与策略",
        "children": [
            ("inv-style-profile", "风格画像"),
            ("inv-buy-framework", "买入决策框架"),
            ("inv-sell-framework", "卖出决策框架"),
        ],
    },
    {
        "dimension_id": "inv-behavior",
        "dimension_name": "行为特征与偏差画像",
        "children": [
            ("inv-cognitive-bias", "认知偏差档案"),
            ("inv-emotion-pattern", "情绪模式"),
            ("inv-decision-adaptation-style", "决策与适应风格"),
        ],
    },
    {
        "dimension_id": "inv-review",
        "dimension_name": "决策记录与复盘系统",
        "children": [
            ("inv-decision-log", "决策日志"),
            ("inv-review-record", "复盘记录"),
            ("inv-rules-library", "投资规则库"),
        ],
    },
    {
        "dimension_id": "inv-portfolio",
        "dimension_name": "组合与执行",
        "children": [
            ("inv-portfolio-preference", "组合管理偏好"),
            ("inv-execution-discipline", "执行纪律"),
            ("inv-time-preference", "时间偏好"),
        ],
    },
    {
        "dimension_id": "inv-network",
        "dimension_name": "信息网络与人脉",
        "children": [
            ("inv-information-source", "信息源"),
            ("inv-consultation-network", "咨询对象"),
        ],
    },
]

SUPPORT_LEVELS = {"strong", "medium", "weak", "none"}
MATURITY_BY_SUPPORT = {
    "strong": "basic",
    "medium": "hint",
    "weak": "hint",
    "none": "empty",
}
CHILD_REQUIRED_KEYS = {
    "subdimension_id",
    "subdimension_name",
    "support_level",
    "suggested_maturity",
    "evidence_count",
    "evidence_kinds",
    "route_targets",
    "signals",
    "gaps",
    "privacy",
}


def augment_evidence_with_dimensions(
    evidence: Dict[str, Any],
    events: Sequence[Dict[str, Any]],
    subdimension_rules: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Return evidence with a canonical 7/20 Investor Wiki dimension tree."""

    augmented = copy.deepcopy(evidence)
    dimensions = build_dimensions(events, subdimension_rules)
    summary = augmented.setdefault("coverage_summary", {})
    summary.update(coverage_summary_for_dimensions(dimensions))
    augmented["dimension_model"] = {
        "schema_parent": "external.investor",
        "major_dimension_count": 7,
        "product_subdimension_count": 20,
    }
    augmented["dimensions"] = dimensions
    generated_from = augmented.setdefault("generated_from", {})
    generated_from.setdefault("event_schema", EVENT_SCHEMA)
    generated_from.setdefault("soulmirror_target_schema", SOULMIRROR_TARGET_SCHEMA)
    policy = augmented.setdefault("wiki_write_policy", {})
    policy.setdefault("collector_writes_wiki_directly", False)
    policy.setdefault("raw_json_writes_wiki_directly", False)
    policy.setdefault(
        "required_flow",
        [
            EVENT_SCHEMA,
            EVIDENCE_SCHEMA,
            "SoulMirror investor-portrait distill/organize",
            "schema-controlled markdown wiki",
        ],
    )
    return augmented


def build_dimensions(
    events: Sequence[Dict[str, Any]],
    subdimension_rules: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    dimensions: List[Dict[str, Any]] = []
    for dimension in INVESTOR_DIMENSIONS:
        children = []
        for sub_id, sub_name in dimension["children"]:
            rule = subdimension_rules.get(sub_id, {})
            matching_events = matching_events_for_rule(events, rule)
            evidence_kinds = sorted({str(event.get("kind") or "unknown") for event in matching_events})
            support_level = str(rule.get("support_level") or "weak") if matching_events else "none"
            if support_level not in SUPPORT_LEVELS:
                support_level = "weak"
            children.append(
                {
                    "subdimension_id": sub_id,
                    "subdimension_name": sub_name,
                    "support_level": support_level,
                    "suggested_maturity": rule.get("suggested_maturity") or MATURITY_BY_SUPPORT[support_level],
                    "evidence_count": len(matching_events),
                    "evidence_kinds": evidence_kinds,
                    "route_targets": sorted(rule.get("route_targets") or []),
                    "signals": list(rule.get("signals") or []) if matching_events else [],
                    "gaps": list(rule.get("gaps") or []),
                    "privacy": {
                        "local_only": True,
                        "sensitive": any((event.get("privacy") or {}).get("sensitive") for event in matching_events),
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
    return dimensions


def matching_events_for_rule(events: Sequence[Dict[str, Any]], rule: Dict[str, Any]) -> List[Dict[str, Any]]:
    route_targets = set(str(target) for target in rule.get("route_targets") or [])
    kinds = set(str(kind) for kind in rule.get("kinds") or [])
    data_matches = rule.get("data_matches") or {}
    matched: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for event in events:
        if event_is_gap(event):
            continue
        if not rule_matches_event(event, route_targets, kinds, data_matches):
            continue
        event_id = str(event.get("id") or id(event))
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        matched.append(event)
    return matched


def rule_matches_event(
    event: Dict[str, Any],
    route_targets: set[str],
    kinds: set[str],
    data_matches: Dict[str, Iterable[Any]],
) -> bool:
    if data_matches:
        if not event_matches_data(event, data_matches):
            return False
        if not route_targets and not kinds:
            return True
    if route_targets and route_targets.intersection(str(target) for target in event.get("wiki_targets") or []):
        return True
    if kinds and str(event.get("kind") or "") in kinds:
        return True
    return False


def event_matches_data(event: Dict[str, Any], data_matches: Dict[str, Iterable[Any]]) -> bool:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    for key, expected_values in data_matches.items():
        value = data.get(key)
        expected = set(str(item) for item in expected_values)
        if isinstance(value, list):
            if expected.intersection(str(item) for item in value):
                return True
        elif str(value) in expected:
            return True
    return False


def event_is_gap(event: Dict[str, Any]) -> bool:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    markers = {
        data.get("subtype"),
        data.get("activity_type"),
        data.get("action_type"),
        data.get("gap"),
        data.get("signal_type"),
    }
    return "collector_gap" in markers or "collector_preflight_gap" in markers


def coverage_summary_for_dimensions(dimensions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    support_counts = Counter(
        str(child.get("support_level") or "none")
        for dimension in dimensions
        for child in dimension.get("children", [])
    )
    usable = [
        child["subdimension_id"]
        for dimension in dimensions
        for child in dimension.get("children", [])
        if child.get("support_level") in {"strong", "medium"}
    ]
    return {
        "dimension_count": len(dimensions),
        "subdimension_count": sum(len(d.get("children", [])) for d in dimensions),
        "support_level_counts": dict(sorted(support_counts.items())),
        "usable_for_wiki_now": usable,
    }


def validate_evidence_contract(evidence: Dict[str, Any], *, require_dimensions: bool = True) -> List[str]:
    errors: List[str] = []
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        errors.append(f"schema must be {EVIDENCE_SCHEMA}")
    generated_from = evidence.get("generated_from")
    if not isinstance(generated_from, dict):
        errors.append("generated_from must be an object")
    elif generated_from.get("event_schema") != EVENT_SCHEMA:
        errors.append(f"generated_from.event_schema must be {EVENT_SCHEMA}")
    policy = evidence.get("wiki_write_policy")
    if not isinstance(policy, dict):
        errors.append("wiki_write_policy must be an object")
    else:
        if policy.get("collector_writes_wiki_directly") is not False:
            errors.append("collector_writes_wiki_directly must be false")
        if policy.get("raw_json_writes_wiki_directly") is not False:
            errors.append("raw_json_writes_wiki_directly must be false")
        flow = " ".join(str(item) for item in policy.get("required_flow") or [])
        if EVENT_SCHEMA not in flow:
            errors.append("required_flow must include collectorx.event.v1")
        if "investor_wiki_evidence.v1" not in flow:
            errors.append("required_flow must include investor_wiki_evidence.v1")
    if require_dimensions:
        errors.extend(validate_dimensions(evidence.get("dimensions"), evidence.get("coverage_summary")))
    return errors


def validate_dimensions(dimensions: Any, coverage_summary: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(dimensions, list):
        return ["dimensions must be a list"]
    expected_dimension_ids = [dimension["dimension_id"] for dimension in INVESTOR_DIMENSIONS]
    actual_dimension_ids = [dimension.get("dimension_id") for dimension in dimensions if isinstance(dimension, dict)]
    if actual_dimension_ids != expected_dimension_ids:
        errors.append(f"dimension ids must be {expected_dimension_ids}")
    child_count = 0
    support_counts: Counter[str] = Counter()
    for dimension, expected_dimension in zip(dimensions, INVESTOR_DIMENSIONS):
        if not isinstance(dimension, dict):
            errors.append("dimension must be an object")
            continue
        children = dimension.get("children")
        if not isinstance(children, list):
            errors.append(f"{dimension.get('dimension_id')}: children must be a list")
            continue
        expected_child_ids = [child_id for child_id, _name in expected_dimension["children"]]
        actual_child_ids = [child.get("subdimension_id") for child in children if isinstance(child, dict)]
        if actual_child_ids != expected_child_ids:
            errors.append(f"{dimension.get('dimension_id')}: child ids must be {expected_child_ids}")
        child_count += len(children)
        for child in children:
            if not isinstance(child, dict):
                errors.append(f"{dimension.get('dimension_id')}: child must be an object")
                continue
            missing = CHILD_REQUIRED_KEYS.difference(child)
            if missing:
                errors.append(f"{child.get('subdimension_id')}: missing {sorted(missing)}")
            support_level = child.get("support_level")
            if support_level not in SUPPORT_LEVELS:
                errors.append(f"{child.get('subdimension_id')}: invalid support_level {support_level}")
            else:
                support_counts[str(support_level)] += 1
            if not isinstance(child.get("evidence_count"), int) or child.get("evidence_count", -1) < 0:
                errors.append(f"{child.get('subdimension_id')}: evidence_count must be a non-negative integer")
            privacy = child.get("privacy")
            if not isinstance(privacy, dict) or not isinstance(privacy.get("local_only"), bool):
                errors.append(f"{child.get('subdimension_id')}: privacy.local_only must be boolean")
    if len(dimensions) != 7:
        errors.append("dimension_count must be 7")
    if child_count != 20:
        errors.append("subdimension_count must be 20")
    if isinstance(coverage_summary, dict):
        if coverage_summary.get("dimension_count") != 7:
            errors.append("coverage_summary.dimension_count must be 7")
        if coverage_summary.get("subdimension_count") != 20:
            errors.append("coverage_summary.subdimension_count must be 20")
        declared = coverage_summary.get("support_level_counts")
        if isinstance(declared, dict):
            declared_normalized = {str(key): int(value) for key, value in declared.items()}
            if declared_normalized != dict(sorted(support_counts.items())):
                errors.append("coverage_summary.support_level_counts does not match dimensions")
    else:
        errors.append("coverage_summary must be an object")
    return errors


def validate_evidence_file(path: Path, *, require_dimensions: bool = True) -> List[str]:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    return validate_evidence_contract(evidence, require_dimensions=require_dimensions)
