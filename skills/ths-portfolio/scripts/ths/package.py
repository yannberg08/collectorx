"""
ths.package - Build FinClaw/SoulMirror-ready Tonghuashun collection packages.

This module writes evidence to a local lake-style package. It intentionally does
not write final SoulMirror Wiki pages; the investor-portrait app owns distill
and organize.
"""

from __future__ import annotations

import json
import hashlib
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


COLLECTOR = "ths-portfolio"
CN_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def write_collection_package(
    output_dir: Path,
    *,
    events: List[Dict[str, Any]],
    collected_at: Optional[str] = None,
    records: Optional[List[Dict[str, Any]]] = None,
    holdings: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    gui_snapshot: Optional[Dict[str, Any]] = None,
    probe_report: Optional[Dict[str, Any]] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    lake_dir = output_dir / "lake" / COLLECTOR
    lake_dir.mkdir(parents=True, exist_ok=True)
    collected = collected_at or _first_collected_at(events) or now_iso()
    if (collection_audit or {}).get("ths_scope_policy_filtered_all"):
        events = [build_scope_policy_filtered_all_event(collection_audit or {}, collected)]

    event_file = lake_dir / "events.jsonl"
    write_jsonl(event_file, events)

    if records is not None:
        write_json(output_dir / "trades.normalized.json", records)
    if holdings is not None:
        write_json(output_dir / "estimated_holdings.json", holdings)
    if metadata is not None:
        write_json(output_dir / "metadata.json", metadata)
    if gui_snapshot is not None:
        write_json(output_dir / "gui_snapshot.json", gui_snapshot)
    if probe_report is not None:
        write_json(output_dir / "probe.json", probe_report)

    evidence = build_investor_wiki_evidence(
        events,
        generated_at=collected,
        source_event_file=str(event_file),
    )
    write_json(output_dir / "investor_wiki_evidence.v1.json", evidence)

    manifest = build_manifest(
        events,
        collected_at=collected,
        output_dir=output_dir,
        source_event_file=event_file,
        evidence=evidence,
        collection_audit=collection_audit,
    )
    write_json(output_dir / "manifest.json", manifest)
    write_summary(output_dir / "SUMMARY.md", manifest, evidence)
    return manifest


def sync_package_to_soulmirror(
    output_dir: Path,
    soulmirror_home: Optional[Path] = None,
) -> Dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    soulmirror_root = (soulmirror_home or Path.home() / ".soulmirror").expanduser()
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collected_at = str(manifest.get("collected_at") or now_iso())
    run_id = re.sub(r"[^0-9A-Za-z_.-]+", "-", collected_at).strip("-")
    lake_root = soulmirror_root / "lake" / COLLECTOR
    run_dir = lake_root / run_id
    latest_dir = lake_root / "latest"
    root_event_file = lake_root / "events.jsonl"
    files = [
        output_dir / "manifest.json",
        output_dir / "investor_wiki_evidence.v1.json",
        output_dir / "SUMMARY.md",
        output_dir / "lake" / COLLECTOR / "events.jsonl",
    ]
    copied: List[str] = []
    for dest_root in (run_dir, latest_dir):
        dest_root.mkdir(parents=True, exist_ok=True)
        for source in files:
            if not source.exists():
                continue
            dest = dest_root / source.name
            shutil.copy2(source, dest)
            copied.append(str(dest))

    event_source = output_dir / "lake" / COLLECTOR / "events.jsonl"
    if event_source.exists():
        lake_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(event_source, root_event_file)
        copied.append(str(root_event_file))

    bridge_manifest = {
        "schema": "finclaw.soulmirror_bridge.v1",
        "collector": COLLECTOR,
        "synced_at": now_iso(),
        "source_output": str(output_dir),
        "soulmirror_home": str(soulmirror_root),
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
        "root_event_file": str(root_event_file),
        "copied_files": sorted(set(copied)),
        "note": "Copied collector evidence into SoulMirror lake, including the native lake/<collector>/events.jsonl entrypoint; final wiki organization remains app-controlled.",
    }
    write_json(output_dir / "soulmirror_sync.json", bridge_manifest)
    write_json(latest_dir / "soulmirror_sync.json", bridge_manifest)
    return bridge_manifest


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: str,
    output_dir: Path,
    source_event_file: Path,
    evidence: Dict[str, Any],
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event.get("kind", "unknown") for event in events)
    gap_count = sum(1 for event in events if _is_gap_profile_event(event))
    has_asset = kind_counts.get("asset_snapshot", 0) > 0
    has_current_holding = any(
        event.get("kind") == "holding" and (event.get("data") or {}).get("is_confirmed")
        for event in events
    )
    strong_count = (
        kind_counts.get("asset_snapshot", 0)
        + sum(1 for event in events if event.get("kind") in {"execution", "order", "cashflow"})
        + sum(
            1
            for event in events
            if event.get("kind") == "holding" and (event.get("data") or {}).get("is_confirmed")
        )
    )
    ths_scope_policy = (collection_audit or {}).get("ths_scope_policy") or {}
    scope_filtered_all = bool((collection_audit or {}).get("ths_scope_policy_filtered_all"))
    if scope_filtered_all:
        status = "scope_policy_filtered_all"
        next_action = "输入已读取，但全部被同花顺授权范围策略排除；请检查事件类型、证券代码、账户、来源和关键词范围。"
    elif has_asset and has_current_holding:
        status = "ready_for_investor_avatar"
        next_action = "可进入投资分身蒸馏；继续补买卖理由、投研笔记、复盘和投资讨论。"
    elif events:
        status = "events_ready_but_current_snapshot_incomplete"
        next_action = "事件已可进入 lake；如需更强画像，请打开交易页并启用 --include-gui-events 采集当前资产/持仓/成交。"
    else:
        status = "empty"
        next_action = "未形成事件；请提供本机扫描、CSV 或 GUI 快照。"

    return {
        "schema": "collectorx.ths_package.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at,
        "output_dir": str(output_dir),
        "source_event_file": str(source_event_file),
        "event_count": len(events),
        "kind_counts": dict(kind_counts),
        "collection_audit": collection_audit
        or {
            "ths_scope_policy": {
                "enabled": False,
                "candidate_event_count": len(events),
                "retained_event_count": len(events),
                "filtered_event_count": 0,
                "filter_reason_counts": {},
                "filtered_all": False,
                "policy_is_user_authorization_scope": True,
                "policy_does_not_assert_investment_relevance": True,
                "exact_business_numbers_preserved": True,
                "read_only": True,
            },
            "ths_scope_policy_filtered_all": False,
        },
        "collection_readiness": {
            "status": status,
            "can_enter_soulmirror_lake": bool(events),
            "can_enter_finclaw": bool(events) and not scope_filtered_all,
            "can_claim_current_trade_collection": bool(has_asset and has_current_holding),
            "strong_current_event_count": strong_count,
            "gap_count": gap_count,
            "scope_policy_filtered_all": scope_filtered_all,
            "next_action": next_action,
        },
        "ths_portfolio_boundary_proof": {
            "source_type": "broker_trade_and_local_behavior_evidence",
            "event_count": len(events),
            "kind_counts": dict(kind_counts),
            "strong_current_event_count": strong_count,
            "authorization_scope_boundary": ths_scope_policy,
            "read_only": True,
            "exact_business_numbers_preserved": True,
            "order_mutation_performed": False,
            "credentials_collected": False,
            "complete_account_boundary_claimed": bool(has_asset and has_current_holding),
            "complete_broker_history_claimed": False,
            "policy_does_not_assert_investment_relevance": True,
        },
        "investor_wiki_evidence": {
            "schema": evidence.get("schema"),
            "dimension_count": len(evidence.get("dimensions", [])),
            "subdimension_count": evidence.get("coverage_summary", {}).get("subdimension_count"),
            "support_level_counts": evidence.get("coverage_summary", {}).get("support_level_counts", {}),
        },
        "privacy": {
            "local_only": True,
            "sensitive": True,
            "raw_private_outputs_not_for_git": True,
        },
}


def build_scope_policy_filtered_all_event(
    collection_audit: Dict[str, Any],
    collected_at: str,
) -> Dict[str, Any]:
    policy = collection_audit.get("ths_scope_policy") or {}
    digest = hashlib_json(
        {
            "status": "ths_scope_policy_filtered_all",
            "candidate_event_count": policy.get("candidate_event_count", 0),
            "filtered_event_count": policy.get("filtered_event_count", 0),
            "filter_reason_counts": policy.get("filter_reason_counts", {}),
        }
    )
    return {
        "schema": "collectorx.event.v1",
        "id": f"{COLLECTOR}:scope-policy-filtered-all:{digest}",
        "collector": COLLECTOR,
        "source": "同花顺授权范围策略",
        "owner_scope": "personal",
        "kind": "profile",
        "time": collected_at,
        "collected_at": collected_at,
        "data": {
            "gap": "ths_scope_policy_filtered_all",
            "status": "scope_policy_filtered_all",
            "profile_type": "ths_scope_policy_filtered_all",
            "candidate_event_count": policy.get("candidate_event_count", 0),
            "retained_event_count": policy.get("retained_event_count", 0),
            "filtered_event_count": policy.get("filtered_event_count", 0),
            "filter_reason_counts": policy.get("filter_reason_counts", {}),
            "policy_is_user_authorization_scope": True,
            "policy_does_not_assert_investment_relevance": True,
            "exact_business_numbers_preserved": True,
            "read_only": True,
            "note": "输入已读取，但全部被同花顺授权范围策略排除；未把任何交易、持仓、委托、成交或资金流水事实写入 Lake。",
        },
        "raw_ref": {"scope_policy_enabled": True},
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["trade", "money", "portfolio"],
        },
        "wiki_targets": [
            "investor.data_quality.collection_gaps",
        ],
    }


def _is_gap_profile_event(event: Dict[str, Any]) -> bool:
    if event.get("kind") != "profile":
        return False
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    profile_type = str(data.get("profile_type") or "")
    status = str(data.get("status") or "")
    return bool(
        data.get("gap")
        or profile_type.startswith("ths_gui_empty_")
        or profile_type.endswith("_gap")
        or status.endswith("_gap")
        or status == "scope_policy_filtered_all"
    )


def hashlib_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]


def build_investor_wiki_evidence(
    events: List[Dict[str, Any]],
    *,
    generated_at: Optional[str] = None,
    source_event_file: Optional[str] = None,
) -> Dict[str, Any]:
    kind_counts = Counter(event.get("kind", "unknown") for event in events)
    by_kind: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_kind[event.get("kind", "unknown")].append(event)
        for target in event.get("wiki_targets") or []:
            by_target[str(target)].append(event)

    side_counts = Counter()
    for event in by_kind.get("trade", []):
        data = event.get("data") or {}
        side_counts[data.get("side") or data.get("raw_side") or "unknown"] += 1

    def target_count(*targets: str) -> Tuple[int, List[str]]:
        seen = set()
        kinds = Counter()
        for target in targets:
            for event in by_target.get(target, []):
                event_id = event.get("id")
                if event_id in seen:
                    continue
                seen.add(event_id)
                kinds[event.get("kind", "unknown")] += 1
        return len(seen), sorted(kinds)

    def kind_count(*kinds: str) -> Tuple[int, List[str]]:
        seen = set()
        present = Counter()
        for kind in kinds:
            for event in by_kind.get(kind, []):
                event_id = event.get("id")
                if event_id in seen:
                    continue
                seen.add(event_id)
                present[event.get("kind", "unknown")] += 1
        return len(seen), sorted(present)

    decision_log_count, decision_log_kinds = target_count("investor.record_review.decision_log")
    portfolio_count, portfolio_kinds = target_count(
        "investor.risk_portfolio.portfolio_constraints",
        "investor.risk_portfolio.current_positions",
        "investor.risk_portfolio.current_assets",
        "external.capital.assets",
    )
    style_count, style_kinds = kind_count("trade", "execution", "holding", "asset_snapshot")
    watch_count, watch_kinds = target_count(
        "investor.opportunity_watchlist.watchlist",
        "investor.capability_circle.attention_universe",
        "investor.capability_circle.theme_attention",
    )
    analysis_count, analysis_kinds = target_count(
        "investor.decision_framework.strategy_rules",
        "investor.decision_framework.monitoring_rules",
        "investor.capability_circle.factor_attention",
    )
    workflow_count, workflow_kinds = target_count(
        "investor.research_consumption.workflow",
        "investor.information_sources.news_consumption",
    )
    rule_count, rule_kinds = target_count(
        "investor.decision_framework.strategy_rules",
        "investor.decision_framework.monitoring_rules",
    )
    execution_count, execution_kinds = target_count(
        "investor.execution.orders",
        "investor.record_review.decision_log",
        "external.capital.cashflows",
    )
    info_count, info_kinds = target_count(
        "investor.information_sources.news_consumption",
        "investor.research_consumption.workflow",
    )

    def node(
        sub_id: str,
        sub_name: str,
        level: str,
        maturity: str,
        count: int,
        kinds: List[str],
        signals: List[str],
        gaps: List[str],
        routes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "subdimension_id": sub_id,
            "subdimension_name": sub_name,
            "support_level": level,
            "suggested_maturity": maturity,
            "evidence_count": count,
            "evidence_kinds": kinds,
            "route_targets": routes or [],
            "signals": signals,
            "gaps": gaps,
            "privacy": {"local_only": True, "sensitive": True},
        }

    dimensions = [
        {
            "dimension_id": "inv-philosophy",
            "dimension_name": "投资哲学与信念",
            "children": [
                node("inv-market-view", "市场观", "weak", "hint", watch_count, watch_kinds, ["有主题关注、自选池和资讯消费线索"], ["缺少用户对市场机制、周期和机会来源的明确表达"]),
                node("inv-risk-view", "风险观", "medium", "basic", portfolio_count, portfolio_kinds, ["有资产、持仓、仓位和交易金额等风险暴露证据"], ["行为能说明风险暴露，不能直接说明风险信念和红线"]),
                node("inv-value-preference", "价值偏好", "weak", "hint", watch_count + kind_counts.get("holding", 0), sorted(set(watch_kinds + ["holding"])), ["有自选、持仓或因子标签侧影"], ["缺少为什么偏好这些资产/行业/因子的文本理由"]),
            ],
        },
        {
            "dimension_id": "inv-circle",
            "dimension_name": "能力圈定义",
            "children": [
                node("inv-industry-circle", "行业能力圈", "medium", "basic", watch_count + kind_counts.get("holding", 0), sorted(set(watch_kinds + ["holding"])), ["自选、持仓、历史标的和主题关注能形成关注宇宙"], ["关注不等于懂，需要投研笔记和复盘验证"]),
                node("inv-analysis-ability", "分析能力", "weak", "hint", analysis_count, analysis_kinds, ["有策略规则、因子标签和工具配置线索"], ["可能混入软件默认配置，不能直接证明分析质量"]),
                node("inv-information-learning-style", "信息处理与学习风格", "medium", "hint", workflow_count, workflow_kinds, ["有组件布局、自定义页面和资讯阅读标记"], ["缺少筛选、验证、学习迭代的过程记录"]),
            ],
        },
        {
            "dimension_id": "inv-style",
            "dimension_name": "投资风格与策略",
            "children": [
                node("inv-style-profile", "风格画像", "strong", "basic", style_count, style_kinds, ["交易、成交、持仓和资产快照可分析频率、集中度和持仓周期"], ["缺少交易理由，成熟度不应过高"]),
                node("inv-buy-framework", "买入决策框架", "medium", "hint", side_counts.get("buy", 0) + analysis_count, sorted(set(["trade"] + analysis_kinds)), ["有买入行为、仓位行为和策略配置线索"], ["缺少买入理由、触发条件和备选方案"]),
                node("inv-sell-framework", "卖出决策框架", "medium", "hint", side_counts.get("sell", 0) + analysis_count, sorted(set(["trade"] + analysis_kinds)), ["有卖出行为、成交结果和可能的止盈止损线索"], ["缺少卖出理由、止盈止损或换仓规则说明"]),
            ],
        },
        {
            "dimension_id": "inv-behavior",
            "dimension_name": "行为特征与偏差画像",
            "children": [
                node("inv-cognitive-bias", "认知偏差档案", "weak", "hint", kind_counts.get("trade", 0), ["trade"] if kind_counts.get("trade") else [], ["交易序列可后验观察频繁交易、亏损持有等模式"], ["仅凭交易记录不能轻易定性偏差，需要市场背景和用户解释"]),
                node("inv-emotion-pattern", "情绪模式", "none", "empty", 0, [], [], ["同花顺数据没有情绪表达，需要聊天、语音、笔记或复盘"]),
                node("inv-decision-adaptation-style", "决策与适应风格", "medium", "basic", style_count, style_kinds, ["交易节奏、分批/集中、仓位变化可形成决策风格线索"], ["缺少决策过程文本和复盘迭代证据"]),
            ],
        },
        {
            "dimension_id": "inv-review",
            "dimension_name": "决策记录与复盘系统",
            "children": [
                node("inv-decision-log", "决策日志", "strong", "basic", decision_log_count, decision_log_kinds, ["历史交易和当日成交可形成交易时间线"], ["缺少每笔交易的意图、假设和事后评价"]),
                node("inv-review-record", "复盘记录", "none", "empty", 0, [], [], ["当前采集包没有盘后复盘文本、错误归因和总结记录"]),
                node("inv-rules-library", "投资规则库", "medium", "hint", rule_count, rule_kinds, ["有策略规则和短线监控规则等配置线索"], ["需区分用户主动配置和软件默认规则"]),
            ],
        },
        {
            "dimension_id": "inv-portfolio",
            "dimension_name": "组合与执行",
            "children": [
                node("inv-portfolio-preference", "组合管理偏好", "strong", "basic", portfolio_count, portfolio_kinds, ["资产快照、当前持仓、历史组合线索能支撑组合偏好"], ["需要长期目标、最大仓位和行业暴露红线等显性约束"]),
                node("inv-execution-discipline", "执行纪律", "medium", "hint", execution_count, execution_kinds, ["有成交、委托/空表、资金明细和交易频率线索"], ["缺少计划单、目标价、撤单原因和计划 vs 实际"]),
                node("inv-time-preference", "时间偏好", "strong", "basic", kind_counts.get("trade", 0) + kind_counts.get("holding", 0), sorted(k for k in ["trade", "holding"] if kind_counts.get(k)), ["交易日期、成交节奏和持仓周期可分析短中长期偏好"], ["需要结合交易理由确认是主动偏好还是被动持有"]),
            ],
        },
        {
            "dimension_id": "inv-network",
            "dimension_name": "信息网络与人脉",
            "children": [
                node("inv-information-source", "信息源", "medium", "hint", info_count, info_kinds, ["有同花顺内资讯阅读、组件布局和工作台入口"], ["缺少站外信息源、研报来源、公众号/社群/专家来源"]),
                node("inv-consultation-network", "咨询对象", "none", "empty", 0, [], [], ["同花顺没有人际咨询证据，需要微信/飞书/会议纪要/投研社群"]),
            ],
        },
    ]

    levels = Counter(
        child["support_level"]
        for dimension in dimensions
        for child in dimension["children"]
    )
    return {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "source_event_file": source_event_file,
            "event_count": len(events),
            "kind_counts": dict(kind_counts),
            "soulmirror_target_schema": "external.investor / 7 dimensions / 20 subdimensions",
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": [
                "collectorx.event.v1",
                "investor_wiki_evidence.v1",
                "SoulMirror app distill/organize",
                "schema-controlled markdown wiki",
            ],
            "sensitive_detail_policy": "Raw holdings, amounts, account identifiers, contract numbers and screenshots remain in the local evidence package; wiki should contain distilled facts and evidence indexes.",
        },
        "dimensions": dimensions,
        "coverage_summary": {
            "dimension_count": len(dimensions),
            "subdimension_count": sum(len(d["children"]) for d in dimensions),
            "support_level_counts": dict(levels),
            "usable_for_wiki_now": [
                child["subdimension_id"]
                for dimension in dimensions
                for child in dimension["children"]
                if child["support_level"] in {"strong", "medium"}
            ],
            "needs_extra_explanatory_collectors": [
                "wechat-investment-dialogue",
                "research-notes",
                "review-notes",
                "announcement-and-report-annotations",
                "meeting-minutes",
            ],
        },
    }


def write_summary(path: Path, manifest: Dict[str, Any], evidence: Dict[str, Any]) -> None:
    coverage = evidence.get("coverage_summary", {})
    lines = [
        "# 同花顺投资分身采集包",
        "",
        f"采集时间：{manifest.get('collected_at')}",
        "",
        "## 事件概况",
        "",
        f"- 总事件数：{manifest.get('event_count', 0)}",
        f"- 事件类型：{json.dumps(manifest.get('kind_counts', {}), ensure_ascii=False)}",
        f"- readiness：`{manifest.get('collection_readiness', {}).get('status')}`",
        "",
        "## 投资 Wiki 证据覆盖",
        "",
        f"- 维度数：{coverage.get('dimension_count')}",
        f"- 子维度数：{coverage.get('subdimension_count')}",
        f"- 支持强度：{json.dumps(coverage.get('support_level_counts', {}), ensure_ascii=False)}",
        "",
        "## 写入边界",
        "",
        "- 本包可以同步到 SoulMirror lake。",
        "- 本包不直接写最终 Wiki；最终组织由 `investor-portrait` app 完成。",
        "- 原始金额、账户、合同号、截图和流水留在本地证据包，不应直接暴露在 Wiki 正文。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, events: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            f.write("\n")


def _first_collected_at(events: List[Dict[str, Any]]) -> Optional[str]:
    for event in events:
        if event.get("collected_at"):
            return str(event["collected_at"])
    return None
