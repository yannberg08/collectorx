"""Parse professional terminal usage exports into CollectorX events."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency for runtime installs
    openpyxl = None

try:
    from collectorx.investor_wiki import augment_evidence_with_dimensions
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution outside repo cwd
    for parent in Path(__file__).resolve().parents:
        if (parent / "collectorx").exists():
            sys.path.insert(0, str(parent))
            break
    from collectorx.investor_wiki import augment_evidence_with_dimensions


COLLECTOR = "pro-terminal-usage"
CN_TZ = timezone(timedelta(hours=8))
SUPPORTED_RECORD_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".ndjson",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xlsm",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
    ".ini",
    ".conf",
    ".log",
}
SUPPORTED_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS | {".zip"}
SUPPORTED_ZIP_EXTENSIONS = SUPPORTED_RECORD_EXTENSIONS
SECRET_KEY_FRAGMENTS = ("password", "passwd", "cookie", "token", "secret", "credential", "authorization", "session", "license")
CONTENT_KEY_FRAGMENTS = ("content", "body", "正文", "全文", "payload", "result")
EXPECTED_PRO_TERMINALS = ("wind", "choice", "ifind", "bloomberg")
EXPECTED_TERMINAL_ACTIVITY_TYPES = ("workspace", "watchlist", "search", "download", "model_template", "factor_attention")
INVESTOR_WIKI_SUBDIMENSION_RULES = {
    "inv-market-view": {
        "support_level": "weak",
        "route_targets": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "signals": ["终端搜索、下载和工作区主题可作为市场关注线索。"],
        "gaps": ["终端使用痕迹不等于用户市场信念，需要笔记/对话/复盘解释。"],
    },
    "inv-industry-circle": {
        "support_level": "medium",
        "route_targets": ["investor.capability_circle.attention_universe", "investor.capability_circle.factor_attention"],
        "data_matches": {"workflow_topics": ["industry_theme", "company_fundamental"]},
        "signals": ["自选、行业/公司主题、因子与数据集使用可刻画关注宇宙。"],
        "gaps": ["关注某行业或数据集不等于真正能力圈，需要研究产物验证。"],
    },
    "inv-analysis-ability": {
        "support_level": "medium",
        "route_targets": [
            "investor.capability_circle.analysis_ability",
            "investor.capability_circle.factor_attention",
            "investor.decision_framework.strategy_rules",
            "investor.decision_framework.monitoring_rules",
        ],
        "signals": ["函数、模板、因子、字段和数据集使用能描述分析工具栈。"],
        "gaps": ["工具使用不能直接证明分析质量或结论正确性。"],
    },
    "inv-information-learning-style": {
        "support_level": "medium",
        "route_targets": ["investor.research_consumption.workflow", "investor.information_sources.news_consumption"],
        "signals": ["搜索、下载、工作区和模板记录可刻画信息处理流程。"],
        "gaps": ["缺少用户如何吸收、验证和更新观点的文本证据。"],
    },
    "inv-style-profile": {
        "support_level": "weak",
        "route_targets": ["investor.capability_circle.factor_attention", "investor.decision_framework.strategy_rules"],
        "signals": ["模型模板、因子关注和自选结构可作为风格侧影。"],
        "gaps": ["终端配置可能是工作默认环境，不能单独证明投资风格。"],
    },
    "inv-rules-library": {
        "support_level": "medium",
        "route_targets": ["investor.decision_framework.strategy_rules", "investor.decision_framework.monitoring_rules"],
        "signals": ["模型模板、监控规则、字段和因子组合可形成规则库候选。"],
        "gaps": ["需要区分用户主动规则和软件/机构默认模板。"],
    },
    "inv-review-record": {
        "support_level": "weak",
        "route_targets": ["investor.record_review.review_record", "investor.research_consumption.workflow"],
        "signals": ["下载和工作流记录可作为复盘材料来源。"],
        "gaps": ["终端导出本身不是复盘结论，仍需笔记或会议纪要。"],
    },
    "inv-execution-discipline": {
        "support_level": "weak",
        "route_targets": ["investor.execution.watchlist_alerts", "investor.decision_framework.monitoring_rules"],
        "signals": ["自选提醒、监控规则和终端工作流可作为执行前监控线索。"],
        "gaps": ["专业终端不提供真实下单执行结果，需要券商数据验证。"],
    },
    "inv-information-source": {
        "support_level": "medium",
        "route_targets": ["investor.information_sources.news_consumption", "investor.research_consumption.workflow"],
        "signals": ["终端、数据集、栏目、函数和下载记录可明确专业信息源。"],
        "gaps": ["厂商内容许可边界必须保留，不镜像数据库或研报全文。"],
    },
}
SOURCE_ARCHIVE_KEY = "_collectorx_source_archive"
SOURCE_MEMBER_KEY = "_collectorx_archive_member"
CONTENT_PREVIEW_MAX_CHARS = 800
RECOMMENDED_WORKFLOW_FIELDS = (
    "workflow_topics",
    "primary_workflow_topic",
    "workspace",
    "project",
    "module",
    "function_code",
    "menu_path",
    "query",
    "query_terms",
    "parameters",
    "symbols",
    "symbol_count",
    "universe",
    "industries",
    "regions",
    "factors",
    "factor_count",
    "datasets",
    "dataset_count",
    "fields",
    "field_count",
    "workspace_id",
    "template_name",
    "template_id",
    "frequency",
    "date_range",
    "download_format",
    "file_name",
    "export_path",
    "row_count",
    "watchlist_size",
    "lineage_ref",
)
TERMINAL_WORKFLOW_TOPIC_ORDER = (
    "macro_policy",
    "market_strategy",
    "industry_theme",
    "company_fundamental",
    "valuation_model",
    "credit_fixed_income",
    "factor_quant",
    "portfolio_monitoring",
    "data_export",
    "hk_us_market",
    "unclassified_workflow_topic",
)
TERMINAL_WORKFLOW_TOPIC_TERMS = {
    "macro_policy": {
        "宏观",
        "政策",
        "利率",
        "汇率",
        "央行",
        "货币",
        "财政",
        "美联储",
        "社融",
        "十年国债",
        "M2",
        "CPI",
        "PPI",
        "EDB",
    },
    "market_strategy": {
        "策略",
        "配置",
        "仓位",
        "风格",
        "择时",
        "红利",
        "market strategy",
        "allocation",
        "style",
    },
    "industry_theme": {
        "行业",
        "产业链",
        "景气",
        "主题",
        "半导体",
        "新能源",
        "医药",
        "互联网",
        "设备",
        "国产化",
        "AI",
        "semiconductor",
    },
    "company_fundamental": {
        "财务",
        "财报",
        "基本面",
        "收入",
        "利润",
        "现金流",
        "毛利率",
        "ROE",
        "revenue",
        "EBITDA",
        "cash flow",
        "FA",
    },
    "valuation_model": {
        "估值",
        "估值表",
        "DCF",
        "PE",
        "PB",
        "PS",
        "EV/EBITDA",
        "valuation",
        "model",
        "template",
    },
    "credit_fixed_income": {
        "信用",
        "利差",
        "债券",
        "固收",
        "转债",
        "违约",
        "credit",
        "spread",
        "bond",
        "OAS",
    },
    "factor_quant": {
        "因子",
        "指标",
        "量化",
        "alpha",
        "momentum",
        "factor",
    },
    "portfolio_monitoring": {
        "自选",
        "组合",
        "盯盘",
        "监控",
        "提醒",
        "watchlist",
        "portfolio",
        "monitor",
        "alert",
    },
    "data_export": {
        "下载",
        "导出",
        "数据集",
        "字段",
        "download",
        "export",
        "xlsx",
        "csv",
        "dataset",
        "field",
    },
    "hk_us_market": {
        "港股",
        "美股",
        "中概股",
        "恒生",
        "纳斯达克",
        "HK",
        "US",
        "NVDA",
        "00700",
        "09988",
    },
}
SECTION_ACTIVITY_TYPES = {
    "usage": None,
    "workspaces": "workspace",
    "dashboards": "workspace",
    "watchlists": "watchlist",
    "searches": "search",
    "queries": "search",
    "downloads": "download",
    "exports": "download",
    "templates": "model_template",
    "models": "model_template",
    "factors": "factor_attention",
    "indicators": "factor_attention",
}
ACTIVITY_SCOPE_ALIASES = {
    "workspace": "workspace",
    "workspaces": "workspace",
    "dashboard": "workspace",
    "dashboards": "workspace",
    "watchlist": "watchlist",
    "watchlists": "watchlist",
    "search": "search",
    "searches": "search",
    "query": "search",
    "queries": "search",
    "download": "download",
    "downloads": "download",
    "export": "download",
    "exports": "download",
    "model": "model_template",
    "models": "model_template",
    "template": "model_template",
    "templates": "model_template",
    "model_template": "model_template",
    "model_templates": "model_template",
    "factor": "factor_attention",
    "factors": "factor_attention",
    "indicator": "factor_attention",
    "indicators": "factor_attention",
    "factor_attention": "factor_attention",
}
VENDOR_TERMS = {
    "wind": ("wind", "万得"),
    "choice": ("choice", "东方财富choice"),
    "ifind": ("ifind", "同花顺ifind", "同花顺 iFinD", "同花顺ifind"),
    "bloomberg": ("bloomberg", "彭博"),
}


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def collect_from_inputs(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_terminals: Optional[Iterable[str]] = None,
    deny_terminals: Optional[Iterable[str]] = None,
    allow_activities: Optional[Iterable[str]] = None,
    deny_activities: Optional[Iterable[str]] = None,
    allow_workspaces: Optional[Iterable[str]] = None,
    deny_workspaces: Optional[Iterable[str]] = None,
    allow_projects: Optional[Iterable[str]] = None,
    deny_projects: Optional[Iterable[str]] = None,
    allow_datasets: Optional[Iterable[str]] = None,
    deny_datasets: Optional[Iterable[str]] = None,
    allow_fields: Optional[Iterable[str]] = None,
    deny_fields: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    events, _audit = collect_from_inputs_with_audit(
        inputs,
        collected_at=collected_at,
        limit=limit,
        allow_terminals=allow_terminals,
        deny_terminals=deny_terminals,
        allow_activities=allow_activities,
        deny_activities=deny_activities,
        allow_workspaces=allow_workspaces,
        deny_workspaces=deny_workspaces,
        allow_projects=allow_projects,
        deny_projects=deny_projects,
        allow_datasets=allow_datasets,
        deny_datasets=deny_datasets,
        allow_fields=allow_fields,
        deny_fields=deny_fields,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    return events


def collect_from_inputs_with_audit(
    inputs: Iterable[str],
    *,
    collected_at: Optional[str] = None,
    limit: Optional[int] = None,
    allow_terminals: Optional[Iterable[str]] = None,
    deny_terminals: Optional[Iterable[str]] = None,
    allow_activities: Optional[Iterable[str]] = None,
    deny_activities: Optional[Iterable[str]] = None,
    allow_workspaces: Optional[Iterable[str]] = None,
    deny_workspaces: Optional[Iterable[str]] = None,
    allow_projects: Optional[Iterable[str]] = None,
    deny_projects: Optional[Iterable[str]] = None,
    allow_datasets: Optional[Iterable[str]] = None,
    deny_datasets: Optional[Iterable[str]] = None,
    allow_fields: Optional[Iterable[str]] = None,
    deny_fields: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    input_list = list(inputs)
    events: List[Dict[str, Any]] = []
    extension_counts: Counter[str] = Counter()
    skipped_extension_counts: Counter[str] = Counter()
    skipped_reason_counts: Counter[str] = Counter()
    skipped_archive_member_reason_counts: Counter[str] = Counter()
    scope_policy_filter_reason_counts: Counter[str] = Counter()
    candidate_record_count = 0
    scope_policy_filtered_record_count = 0
    policy = build_pro_terminal_scope_policy(
        allow_terminals=allow_terminals,
        deny_terminals=deny_terminals,
        allow_activities=allow_activities,
        deny_activities=deny_activities,
        allow_workspaces=allow_workspaces,
        deny_workspaces=deny_workspaces,
        allow_projects=allow_projects,
        deny_projects=deny_projects,
        allow_datasets=allow_datasets,
        deny_datasets=deny_datasets,
        allow_fields=allow_fields,
        deny_fields=deny_fields,
        allow_keywords=allow_keywords,
        deny_keywords=deny_keywords,
    )
    audit: Dict[str, Any] = {
        "source_type": "authorized_pro_terminal_usage_export",
        "input_count": len(input_list),
        "requested_inputs": [str(Path(raw).expanduser()) for raw in input_list],
        "resolved_input_file_count": 0,
        "input_missing_count": 0,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "limit": limit,
        "limit_reached": False,
        "extension_counts": {},
        "skipped_extension_counts": {},
        "skipped_reason_counts": {},
        "skipped_file_count": 0,
        "archive_count": 0,
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
        "candidate_record_count": 0,
        "scope_policy_filtered_record_count": 0,
        "scope_policy_filter_reason_counts": {},
        "pro_terminal_scope_policy": policy,
        "pro_terminal_scope_policy_filtered_all": False,
        "parsed_record_count": 0,
        "emitted_event_count": 0,
        "path_results": [],
    }

    for raw in input_list:
        if limit is not None and len(events) >= limit:
            audit["limit_reached"] = True
            break
        input_path = Path(raw).expanduser()
        if not input_path.exists():
            audit["input_missing_count"] += 1
            skipped_reason_counts["input_missing"] += 1
            audit["path_results"].append(path_result(input_path, status="missing", reason="input_missing"))
            continue
        if input_path.is_dir():
            files = sorted(child for child in input_path.rglob("*") if child.is_file())
        elif input_path.is_file():
            files = [input_path]
        else:
            skipped_reason_counts["unsupported_input_kind"] += 1
            audit["path_results"].append(path_result(input_path, status="skipped", reason="unsupported_input_kind"))
            continue

        for path in files:
            if limit is not None and len(events) >= limit:
                audit["limit_reached"] = True
                break
            ext = extension_label(path)
            extension_counts[ext] += 1
            if not is_supported_path(path):
                audit["skipped_file_count"] += 1
                skipped_extension_counts[ext] += 1
                skipped_reason_counts["unsupported_extension"] += 1
                audit["path_results"].append(path_result(path, status="skipped", reason="unsupported_extension"))
                continue
            audit["resolved_input_file_count"] += 1
            result = path_result(path, status="pending")
            try:
                if path.suffix.lower() == ".zip":
                    zip_limit = None if policy["enabled"] else remaining_limit(limit, events)
                    parsed, archive_audit = parse_zip_with_audit(path, limit=zip_limit)
                    merge_archive_audit(audit, archive_audit, skipped_archive_member_reason_counts)
                    result.update(
                        {
                            "status": "parsed" if parsed else "no_records_parsed",
                            "parser": "zip",
                            "parsed_record_count": len(parsed),
                            "archive_member_count": archive_audit["archive_member_count"],
                            "skipped_archive_member_count": archive_audit["skipped_archive_member_count"],
                        }
                    )
                else:
                    parsed = parse_path(path)
                    result.update(
                        {
                            "status": "parsed" if parsed else "no_records_parsed",
                            "parser": parser_name_for_path(path),
                            "parsed_record_count": len(parsed),
                        }
                    )
            except Exception:
                parsed = []
                audit["skipped_file_count"] += 1
                skipped_extension_counts[ext] += 1
                skipped_reason_counts["parse_error"] += 1
                result.update({"status": "parse_error", "reason": "parse_error", "parsed_record_count": 0})
            audit["path_results"].append(result)
            row = 0
            path_candidate_count = 0
            path_filtered_count = 0
            path_emitted_count = 0
            for record in parsed:
                if not isinstance(record, dict):
                    continue
                row += 1
                candidate_record_count += 1
                path_candidate_count += 1
                event = record_to_event(record, path=path, row=row, collected_at=collected_at)
                filter_reason = pro_terminal_scope_policy_filter_reason(event, policy)
                if filter_reason:
                    scope_policy_filtered_record_count += 1
                    path_filtered_count += 1
                    scope_policy_filter_reason_counts[filter_reason] += 1
                    continue
                events.append(event)
                path_emitted_count += 1
                if limit is not None and len(events) >= limit:
                    audit["limit_reached"] = True
                    break
            if path_candidate_count:
                result["candidate_record_count"] = path_candidate_count
                result["scope_policy_filtered_record_count"] = path_filtered_count
                result["emitted_record_count"] = path_emitted_count
                if policy["enabled"] and path_filtered_count == path_candidate_count and path_emitted_count == 0:
                    result["status"] = "filtered_by_scope_policy"
                    result["reason"] = "scope_policy_excluded_all_records"
                elif path_filtered_count:
                    result["scope_policy_filter_status"] = "partially_filtered"
        if limit is not None and len(events) >= limit:
            break

    audit["candidate_record_count"] = candidate_record_count
    audit["scope_policy_filtered_record_count"] = scope_policy_filtered_record_count
    audit["scope_policy_filter_reason_counts"] = dict(sorted(scope_policy_filter_reason_counts.items()))
    scope_policy_filtered_all = (
        policy["enabled"]
        and candidate_record_count > 0
        and scope_policy_filtered_record_count == candidate_record_count
        and not events
    )
    audit["pro_terminal_scope_policy_filtered_all"] = scope_policy_filtered_all
    audit["parsed_record_count"] = candidate_record_count
    audit["extension_counts"] = dict(sorted(extension_counts.items()))
    audit["skipped_extension_counts"] = dict(sorted(skipped_extension_counts.items()))
    audit["skipped_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_archive_member_reason_counts.items()))

    if not events:
        if scope_policy_filtered_all:
            reason = "pro_terminal_scope_policy_filtered_all"
        elif not input_list or (audit["input_missing_count"] and audit["resolved_input_file_count"] == 0):
            reason = "pro_terminal_usage_authorized_input_missing"
        else:
            reason = "pro_terminal_usage_records_empty"
        events = [gap_event(collected_at=collected_at, reason=reason, collection_audit=audit)]

    audit["emitted_event_count"] = len(events)
    audit["archive_member_event_count"] = sum(1 for event in usable_terminal_events(events) if (event.get("raw_ref") or {}).get("archive_member"))
    return events, audit


def build_pro_terminal_scope_policy(
    *,
    allow_terminals: Optional[Iterable[str]] = None,
    deny_terminals: Optional[Iterable[str]] = None,
    allow_activities: Optional[Iterable[str]] = None,
    deny_activities: Optional[Iterable[str]] = None,
    allow_workspaces: Optional[Iterable[str]] = None,
    deny_workspaces: Optional[Iterable[str]] = None,
    allow_projects: Optional[Iterable[str]] = None,
    deny_projects: Optional[Iterable[str]] = None,
    allow_datasets: Optional[Iterable[str]] = None,
    deny_datasets: Optional[Iterable[str]] = None,
    allow_fields: Optional[Iterable[str]] = None,
    deny_fields: Optional[Iterable[str]] = None,
    allow_keywords: Optional[Iterable[str]] = None,
    deny_keywords: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    policy = {
        "allow_terminals": normalize_scope_terms(allow_terminals, normalizer=normalize_terminal_scope_term),
        "deny_terminals": normalize_scope_terms(deny_terminals, normalizer=normalize_terminal_scope_term),
        "allow_activities": normalize_scope_terms(allow_activities, normalizer=normalize_activity_scope_term),
        "deny_activities": normalize_scope_terms(deny_activities, normalizer=normalize_activity_scope_term),
        "allow_workspaces": normalize_scope_terms(allow_workspaces),
        "deny_workspaces": normalize_scope_terms(deny_workspaces),
        "allow_projects": normalize_scope_terms(allow_projects),
        "deny_projects": normalize_scope_terms(deny_projects),
        "allow_datasets": normalize_scope_terms(allow_datasets),
        "deny_datasets": normalize_scope_terms(deny_datasets),
        "allow_fields": normalize_scope_terms(allow_fields),
        "deny_fields": normalize_scope_terms(deny_fields),
        "allow_keywords": normalize_scope_terms(allow_keywords, keep_case=True),
        "deny_keywords": normalize_scope_terms(deny_keywords, keep_case=True),
    }
    policy["enabled"] = any(bool(values) for values in policy.values())
    return policy


def normalize_scope_terms(
    values: Optional[Iterable[str]],
    *,
    normalizer: Optional[Any] = None,
    keep_case: bool = False,
) -> List[str]:
    cleaned: List[str] = []
    for term in split_policy_terms(values):
        normalized = normalizer(term) if normalizer else term.strip()
        if not normalized:
            continue
        cleaned.append(normalized if keep_case else normalized.lower())
    return sorted(dict.fromkeys(cleaned))


def split_policy_terms(values: Optional[Iterable[str]]) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    terms: List[str] = []
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, (list, tuple, set)):
            terms.extend(split_policy_terms(value))
            continue
        terms.extend(item.strip() for item in re.split(r"[,，、;；|\n]+", str(value)) if item.strip())
    return terms


def normalize_terminal_scope_term(term: str) -> str:
    inferred = infer_terminal({"terminal": term}, term)
    return inferred if inferred != "unknown" else term.strip().lower()


def normalize_activity_scope_term(term: str) -> str:
    normalized = re.sub(r"[\s\-]+", "_", term.strip().lower())
    return ACTIVITY_SCOPE_ALIASES.get(normalized, normalized)


def pro_terminal_scope_policy_filter_reason(event: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    if not policy.get("enabled"):
        return None
    data = event.get("data") or {}
    terminal = normalize_terminal_scope_term(str(data.get("terminal") or ""))
    activity = normalize_activity_scope_term(str(data.get("activity_type") or ""))
    workspace = str(data.get("workspace") or "").strip().lower()
    project = str(data.get("project") or "").strip().lower()
    datasets = normalize_policy_values(data.get("datasets") or [])
    fields = normalize_policy_values(data.get("fields") or [])
    if terminal and terminal in policy.get("deny_terminals", []):
        return "terminal_denied"
    if activity and activity in policy.get("deny_activities", []):
        return "activity_denied"
    if workspace and workspace in policy.get("deny_workspaces", []):
        return "workspace_denied"
    if project and project in policy.get("deny_projects", []):
        return "project_denied"
    if datasets and set(datasets).intersection(policy.get("deny_datasets", [])):
        return "dataset_denied"
    if fields and set(fields).intersection(policy.get("deny_fields", [])):
        return "field_denied"
    if policy_hit(policy.get("deny_keywords", []), flatten_pro_terminal_policy_surface(data)):
        return "keyword_denied"
    if policy.get("allow_terminals") and terminal not in policy["allow_terminals"]:
        return "terminal_not_allowed"
    if policy.get("allow_activities") and activity not in policy["allow_activities"]:
        return "activity_not_allowed"
    if policy.get("allow_workspaces") and workspace not in policy["allow_workspaces"]:
        return "workspace_not_allowed"
    if policy.get("allow_projects") and project not in policy["allow_projects"]:
        return "project_not_allowed"
    if policy.get("allow_datasets") and not set(datasets).intersection(policy["allow_datasets"]):
        return "dataset_not_allowed"
    if policy.get("allow_fields") and not set(fields).intersection(policy["allow_fields"]):
        return "field_not_allowed"
    if policy.get("allow_keywords") and not policy_hit(policy["allow_keywords"], flatten_pro_terminal_policy_surface(data)):
        return "keyword_not_allowed"
    return None


def normalize_policy_values(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        values = value
    else:
        values = split_terms(str(value))
    return sorted({str(item).strip().lower() for item in values if str(item).strip()})


def policy_hit(needles: Sequence[str], values: Iterable[Any]) -> bool:
    if not needles:
        return False
    haystack = "\n".join(str(value) for value in values if value not in (None, "", [], {})).lower()
    return any(str(needle).lower() in haystack for needle in needles if str(needle).strip())


def flatten_pro_terminal_policy_surface(data: Dict[str, Any]) -> List[Any]:
    values: List[Any] = []
    for key in (
        "activity_type",
        "terminal",
        "workflow_topics",
        "primary_workflow_topic",
        "title",
        "source_section",
        "workspace",
        "project",
        "module",
        "function_code",
        "menu_path",
        "query",
        "query_terms",
        "parameters",
        "symbols",
        "universe",
        "industries",
        "regions",
        "factors",
        "datasets",
        "fields",
        "workspace_id",
        "template_name",
        "template_id",
        "frequency",
        "date_range",
        "download_format",
        "file_name",
        "export_path",
        "lineage_ref",
    ):
        value = data.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif isinstance(value, dict):
            values.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        else:
            values.append(value)
    return values


def iter_paths(inputs: Iterable[str]) -> Iterator[Path]:
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and is_supported_path(child):
                    yield child
        elif path.is_file() and is_supported_path(path):
            yield path


def is_supported_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def extension_label(path: Path) -> str:
    return path.suffix.lower() or "<none>"


def parse_path(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return parse_zip(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_table(path)
    if suffix in {".xlsx", ".xlsm"}:
        return parse_workbook(path, path_label=str(path))
    if suffix in {".html", ".htm"}:
        return [parse_html(path)]
    return [parse_text(path)]


def parse_json(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    return parse_json_text(text, suffix=path.suffix.lower(), path_label=str(path))


def parse_json_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_records(json.loads(text))
    records = [row if isinstance(row, dict) else {"value": row} for row in rows]
    for record in records:
        record.setdefault("_source_path", path_label)
    return records


def extract_records(loaded: Any) -> List[Any]:
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"value": loaded}]
    context = {
        str(key): value
        for key, value in loaded.items()
        if not isinstance(value, (list, dict)) and value not in (None, "")
    }
    collected: List[Any] = []
    for key in (
        "usage",
        "workspaces",
        "dashboards",
        "watchlists",
        "searches",
        "queries",
        "downloads",
        "exports",
        "templates",
        "models",
        "factors",
        "indicators",
        "records",
        "items",
        "data",
        "list",
    ):
        value = loaded.get(key)
        if isinstance(value, list):
            collected.extend(with_section_context(item, key, context) for item in value)
        elif isinstance(value, dict):
            collected.extend(with_section_context(item, key, context) for item in extract_records(value))
    if collected:
        return collected
    return [loaded]


def with_section_context(item: Any, section: str, context: Dict[str, Any]) -> Any:
    activity_type = SECTION_ACTIVITY_TYPES.get(section)
    if not isinstance(item, dict):
        return {"value": item, "source_section": section, "activity_type": activity_type}
    record = {**context, **item}
    record.setdefault("source_section", section)
    if activity_type:
        record.setdefault("activity_type", activity_type)
    return record


def parse_table(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_text(text, suffix=path.suffix.lower(), path_label=str(path))


def parse_table_text(text: str, *, suffix: str, path_label: str) -> List[Dict[str, Any]]:
    if not text.strip():
        return []
    delimiter = "\t" if suffix == ".tsv" else sniff_delimiter(text)
    records = [dict(row) for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]
    for record in records:
        record.setdefault("_source_path", path_label)
    return records


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def parse_workbook(path_or_stream: Any, *, path_label: Optional[str] = None) -> List[Dict[str, Any]]:
    if openpyxl is None:
        return []
    workbook = openpyxl.load_workbook(path_or_stream, read_only=True, data_only=True)
    records: List[Dict[str, Any]] = []
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            header_index = next((idx for idx, row in enumerate(rows) if any(cell not in (None, "") for cell in row)), None)
            if header_index is None:
                continue
            headers = [str(cell).strip() if cell not in (None, "") else f"column_{idx + 1}" for idx, cell in enumerate(rows[header_index])]
            for row in rows[header_index + 1 :]:
                record = {
                    headers[idx]: value
                    for idx, value in enumerate(row)
                    if idx < len(headers) and value not in (None, "")
                }
                if record:
                    record["sheet"] = sheet.title
                    if path_label:
                        record.setdefault("_source_path", path_label)
                    record.setdefault("source_section", sheet.title)
                    records.append(record)
    finally:
        workbook.close()
    return records


def parse_html(path: Path) -> Dict[str, Any]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_html_text(html, path_label=str(path), default_title=path.stem)


def parse_html_text(html: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    text = html_to_text(html)
    return {
        "activity_type": "workspace",
        "title": title_tag(html) or infer_title(default_title, text),
        "source": meta_content(html, "application-name") or meta_content(html, "og:site_name"),
        "content": text,
        "_source_path": path_label,
    }


def parse_text(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_text_text(text, path_label=str(path), default_title=path.stem)


def parse_text_text(text: str, *, path_label: str, default_title: str) -> Dict[str, Any]:
    return {
        "activity_type": infer_activity_from_text(text, path_label),
        "title": infer_title(default_title, text),
        "content": text,
        "_source_path": path_label,
    }


def parse_zip(path: Path) -> List[Dict[str, Any]]:
    records, _audit = parse_zip_with_audit(path)
    return records


def parse_zip_with_audit(path: Path, *, limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    skipped_reason_counts: Counter[str] = Counter()
    audit: Dict[str, Any] = {
        "archive": str(path),
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "limit_reached": False,
        "member_results": [],
    }
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.infolist(), key=lambda item: normalize_zip_member_name(item.filename))
        for member in members:
            audit["archive_member_count"] += 1
            member_name = normalize_zip_member_name(member.filename)
            skip_reason = zip_member_skip_reason(member)
            if skip_reason:
                audit["skipped_archive_member_count"] += 1
                skipped_reason_counts[skip_reason] += 1
                audit["member_results"].append({"member": member_name, "status": "skipped", "reason": skip_reason})
                continue
            suffix = Path(member_name).suffix.lower()
            path_label = f"{path}::{member_name}"
            try:
                if suffix in {".json", ".jsonl", ".ndjson"}:
                    parsed = parse_json_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".csv", ".tsv"}:
                    parsed = parse_table_text(archive.read(member).decode("utf-8-sig", errors="replace"), suffix=suffix, path_label=path_label)
                elif suffix in {".xlsx", ".xlsm"}:
                    parsed = parse_workbook(io.BytesIO(archive.read(member)), path_label=path_label)
                elif suffix in {".html", ".htm"}:
                    parsed = [parse_html_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member_name).stem)]
                else:
                    parsed = [parse_text_text(archive.read(member).decode("utf-8-sig", errors="replace"), path_label=path_label, default_title=Path(member_name).stem)]
            except Exception:
                parsed = []
                audit["skipped_archive_member_count"] += 1
                skipped_reason_counts["parse_error"] += 1
                audit["member_results"].append({"member": member_name, "status": "parse_error", "reason": "parse_error"})
                continue
            remaining = None if limit is None else max(limit - len(records), 0)
            emittable = parsed if remaining is None else parsed[:remaining]
            audit["member_results"].append(
                {
                    "member": member_name,
                    "status": "parsed" if parsed else "no_records_parsed",
                    "parsed_record_count": len(parsed),
                    "emitted_record_count": len(emittable),
                }
            )
            for record in emittable:
                if isinstance(record, dict):
                    record[SOURCE_ARCHIVE_KEY] = str(path)
                    record[SOURCE_MEMBER_KEY] = member_name
                    audit["archive_member_event_count"] += 1
            records.extend(emittable)
            if limit is not None and len(records) >= limit:
                audit["limit_reached"] = True
                audit["unvisited_archive_member_count_due_limit"] = max(0, len(members) - audit["archive_member_count"])
                audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
                return records, audit
    audit["unvisited_archive_member_count_due_limit"] = 0
    audit["skipped_archive_member_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    return records, audit


def should_skip_zip_member(member: zipfile.ZipInfo) -> bool:
    return zip_member_skip_reason(member) is not None


def zip_member_skip_reason(member: zipfile.ZipInfo) -> Optional[str]:
    member_name = normalize_zip_member_name(member.filename)
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(member.filename)
    if member.is_dir():
        return "directory"
    if member_path.is_absolute() or windows_path.drive or ".." in member_path.parts:
        return "unsafe_path"
    if Path(member_name).suffix.lower() not in SUPPORTED_ZIP_EXTENSIONS:
        return "unsupported_extension"
    return None


def normalize_zip_member_name(name: str) -> str:
    return name.replace("\\", "/")


def remaining_limit(limit: Optional[int], events: List[Dict[str, Any]]) -> Optional[int]:
    if limit is None:
        return None
    return max(limit - len(events), 0)


def parser_name_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix in {".xlsx", ".xlsm"}:
        return "workbook"
    if suffix in {".csv", ".tsv"}:
        return "table"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
    return "text"


def path_result(path: Path, *, status: str, reason: Optional[str] = None) -> Dict[str, Any]:
    result = {
        "path": str(path),
        "extension": extension_label(path),
        "status": status,
    }
    if reason:
        result["reason"] = reason
    return result


def merge_archive_audit(audit: Dict[str, Any], archive_audit: Dict[str, Any], skipped_reason_counts: Counter[str]) -> None:
    audit["archive_count"] += 1
    audit["archive_member_count"] += int(archive_audit.get("archive_member_count") or 0)
    audit["archive_member_event_count"] += int(archive_audit.get("archive_member_event_count") or 0)
    audit["skipped_archive_member_count"] += int(archive_audit.get("skipped_archive_member_count") or 0)
    if archive_audit.get("limit_reached"):
        audit["limit_reached"] = True
    for reason, count in (archive_audit.get("skipped_archive_member_reason_counts") or {}).items():
        skipped_reason_counts[str(reason)] += int(count)


def record_to_event(record: Dict[str, Any], *, path: Path, row: int, collected_at: Optional[str]) -> Dict[str, Any]:
    path_label = str(record.get("_source_path") or first(record, ["source_path", "file"]) or path)
    activity_type = infer_activity_type(record, path_label)
    terminal = infer_terminal(record, path_label)
    title = first(record, ["title", "name", "workspace", "template", "model", "标题", "名称", "工作区", "模板"]) or Path(path_label).stem
    text = first(record, ["text", "content", "description", "note", "summary", "正文", "内容", "备注", "说明"]) or ""
    query = first(record, ["query", "keyword", "search", "搜索词", "关键词"])
    symbols = symbols_for(record)
    query_terms = query_terms_for(record, query)
    factors = list_values(record, ["factors", "factor", "因子", "指标"])
    datasets = list_values(record, ["datasets", "dataset", "database", "table", "数据集", "数据库", "表"])
    fields = list_values(record, ["fields", "field", "columns", "indicators", "字段", "列", "指标"])
    workflow_topics, workflow_topic_terms = classify_workflow_topics(
        record,
        title=title,
        text=text,
        query=query,
        symbols=symbols,
        activity_type=activity_type,
        terminal=terminal,
    )
    event_time_value = first(record, ["time", "date", "created_at", "updated_at", "used_at", "downloaded_at", "时间", "日期", "使用时间", "下载时间"])
    event_time = str(event_time_value) if event_time_value not in (None, "") else (collected_at or now_iso())
    data = {
        "activity_type": activity_type,
        "terminal": terminal,
        "workflow_topics": workflow_topics,
        "primary_workflow_topic": workflow_topics[0] if workflow_topics else "unclassified_workflow_topic",
        "workflow_topic_terms": workflow_topic_terms,
        "title": title,
        "source_section": first(record, ["source_section", "sheet"]),
        "workspace": first(record, ["workspace", "workspace_name", "工作区", "工作台"]),
        "project": first(record, ["project", "project_name", "strategy", "portfolio", "项目", "策略", "组合"]),
        "module": first(record, ["module", "function", "page", "screen", "模块", "功能", "页面"]),
        "function_code": first(record, ["function_code", "command", "api", "formula", "函数", "命令", "公式"]),
        "menu_path": first(record, ["menu_path", "navigation", "path", "菜单路径", "导航路径"]),
        "query": query,
        "query_terms": query_terms,
        "parameters": parameters_for(record),
        "symbols": symbols,
        "symbol_count": numeric_value(record, ["symbol_count", "security_count", "securities_count", "ticker_count", "证券数", "代码数"])
        or (len(symbols) if symbols else None),
        "universe": list_values(record, ["universe", "scope", "stock_pool", "股票池", "样本空间"]),
        "industries": list_values(record, ["industries", "industry", "行业"]),
        "regions": list_values(record, ["regions", "region", "markets", "market", "地区", "市场"]),
        "factors": factors,
        "factor_count": numeric_value(record, ["factor_count", "indicator_count", "因子数", "指标数"])
        or (len(factors) if factors else None),
        "datasets": datasets,
        "dataset_count": numeric_value(record, ["dataset_count", "database_count", "table_count", "数据集数", "数据库数", "表数"])
        or (len(datasets) if datasets else None),
        "fields": fields,
        "field_count": numeric_value(record, ["field_count", "column_count", "indicator_count", "字段数", "列数", "指标数"])
        or (len(fields) if fields else None),
        "workspace_id": first(record, ["workspace_id", "workspace_code", "workbook_id", "工作区ID", "工作区编号"]),
        "template_name": first(record, ["template_name", "template", "model_name", "模板名称", "模型名称"]),
        "template_id": first(record, ["template_id", "model_id", "模板ID", "模型ID"]),
        "frequency": first(record, ["frequency", "freq", "周期", "频率"]),
        "date_range": first(record, ["date_range", "range", "区间", "日期区间"]),
        "start_date": first(record, ["start_date", "from_date", "开始日期"]),
        "end_date": first(record, ["end_date", "to_date", "结束日期"]),
        "download_format": first(record, ["download_format", "format", "file_type", "文件格式", "格式"]),
        "file_name": first(record, ["file_name", "filename", "export_name", "文件名", "导出文件"]),
        "export_path": first(record, ["export_path", "output_path", "save_path", "saved_path", "download_path", "保存路径", "导出路径", "输出路径", "下载路径"]),
        "row_count": numeric_value(record, ["row_count", "rows", "record_count", "result_count", "行数", "记录数", "结果数"]),
        "watchlist_size": numeric_value(record, ["watchlist_size", "watchlist_count", "自选数量", "关注数量"])
        or (len(symbols) if activity_type == "watchlist" and symbols else None),
        "file_path_hint": first(record, ["file_path", "local_path", "path_hint", "文件路径"]),
        "content_preview": text[:CONTENT_PREVIEW_MAX_CHARS],
        "has_content_preview": bool(text),
        "content_length": len(text),
        "raw": sanitized(record),
    }
    data["lineage_ref"] = lineage_ref_for(data)
    data = {key: value for key, value in data.items() if value not in (None, "", [])}
    raw_ref = {
        "path": path_label,
        "row": row,
        "terminal": terminal,
        "activity_type": activity_type,
        "source_section": data.get("source_section"),
        "source_archive": first(record, [SOURCE_ARCHIVE_KEY]),
        "archive_member": first(record, [SOURCE_MEMBER_KEY]),
    }
    raw_ref = {key: value for key, value in raw_ref.items() if value not in (None, "", [])}
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(path_label, row, terminal, activity_type, title, query, event_time),
        "collector": COLLECTOR,
        "source": "专业终端用户工作流痕迹",
        "owner_scope": "personal",
        "kind": kind_for_activity(activity_type),
        "time": event_time,
        "collected_at": collected_at or event_time or now_iso(),
        "data": data,
        "raw_ref": raw_ref,
        "privacy": {
            "sensitive": True,
            "local_only": True,
            "contains": ["work_confidential"],
        },
        "wiki_targets": wiki_targets_for_activity(activity_type),
    }


def gap_event(
    *,
    collected_at: Optional[str],
    reason: str,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_time = collected_at or now_iso()
    audit = collection_audit or {}
    status_by_reason = {
        "pro_terminal_scope_policy_filtered_all": "scope_policy_filtered_all",
        "pro_terminal_usage_authorized_input_missing": "needs_pro_terminal_usage_input",
        "pro_terminal_usage_records_empty": "no_terminal_workflow_records",
    }
    return {
        "schema": "collectorx.event.v1",
        "id": stable_id(COLLECTOR, reason),
        "collector": COLLECTOR,
        "source": "专业终端使用痕迹授权状态",
        "owner_scope": "personal",
        "kind": "profile",
        "time": event_time,
        "collected_at": event_time,
        "data": {
            "subtype": "collector_gap",
            "activity_type": "collector_gap",
            "gap": reason,
            "status": status_by_reason.get(reason, reason),
            "profile_type": "pro_terminal_usage_collection_gap",
            "message": gap_message(reason),
            "candidate_record_count": int(audit.get("candidate_record_count") or 0),
            "workflow_event_count": 0,
            "retained_event_count": 0,
            "scope_policy_filtered_record_count": int(audit.get("scope_policy_filtered_record_count") or 0),
            "scope_policy_filter_reason_counts": audit.get("scope_policy_filter_reason_counts") or {},
            "policy_is_user_authorization_scope": bool((audit.get("pro_terminal_scope_policy") or {}).get("enabled")),
            "policy_does_not_assert_investment_relevance": True,
            "terminal_workflow_fact_claimed": False,
            "complete_terminal_usage_history_claimed": False,
            "vendor_database_mirrored": False,
            "licensed_content_body_mirrored": False,
            "public_market_data_mirrored": False,
            "terminal_credentials_collected": False,
            "license_keys_collected": False,
            "order_mutation_supported": False,
        },
        "raw_ref": {
            "preflight": True,
            "reason": reason,
            "scope_policy_enabled": bool((audit.get("pro_terminal_scope_policy") or {}).get("enabled")),
        },
        "privacy": {"sensitive": True, "local_only": True, "contains": ["work_confidential", "collection_gap"]},
        "wiki_targets": ["investor.data_quality.collection_gaps"],
    }


def gap_message(reason: str) -> str:
    messages = {
        "pro_terminal_scope_policy_filtered_all": "All user-authorized professional terminal workflow records were excluded by the authorization scope policy.",
        "pro_terminal_usage_authorized_input_missing": "No user-authorized professional terminal workflow export was provided.",
        "pro_terminal_usage_records_empty": "The authorized professional terminal input did not contain usable workflow records.",
    }
    return messages.get(reason, "Professional terminal usage collection produced a traceable gap.")


def infer_activity_type(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["activity_type", "type", "kind", "action", "event", "类型", "动作", "行为"])
    text = json.dumps(record, ensure_ascii=False).lower() + " " + str(path_label).lower()
    probe = (explicit or text).lower()
    if any(token in probe for token in ("watchlist", "自选", "关注证券", "portfolio list")):
        return "watchlist"
    if any(token in probe for token in ("search", "query", "搜索", "检索")):
        return "search"
    if any(token in probe for token in ("download", "export", "导出", "下载")):
        return "download"
    if any(token in probe for token in ("template", "model", "模型", "模板", "估值表")):
        return "model_template"
    if any(token in probe for token in ("factor", "因子", "指标", "roe", "pe", "pb")):
        return "factor_attention"
    if any(token in probe for token in ("workspace", "dashboard", "workbench", "工作区", "工作台", "看板")):
        return "workspace"
    return infer_activity_from_text(text, path_label)


def infer_activity_from_text(text: str, path_label: str) -> str:
    lowered = (text + " " + str(path_label)).lower()
    if any(token in lowered for token in ("自选", "watchlist")):
        return "watchlist"
    if any(token in lowered for token in ("搜索", "search")):
        return "search"
    if any(token in lowered for token in ("下载", "导出", "download", "export")):
        return "download"
    if any(token in lowered for token in ("模型", "模板", "model", "template")):
        return "model_template"
    if any(token in lowered for token in ("因子", "roe", "pe", "pb", "factor")):
        return "factor_attention"
    return "workspace"


def infer_terminal(record: Dict[str, Any], path_label: str) -> str:
    explicit = first(record, ["terminal", "platform", "app", "source_app", "终端", "平台", "应用"])
    text = (explicit or "") + " " + json.dumps(record, ensure_ascii=False) + " " + str(path_label)
    lowered = text.lower()
    for terminal, terms in VENDOR_TERMS.items():
        if any(term.lower() in lowered for term in terms):
            return terminal
    return "unknown"


def kind_for_activity(activity_type: str) -> str:
    if activity_type == "watchlist":
        return "watchlist"
    if activity_type in {"workspace", "model_template", "factor_attention"}:
        return "note"
    return "other"


def wiki_targets_for_activity(activity_type: str) -> List[str]:
    targets = {
        "workspace": ["investor.research_consumption.workflow", "investor.capability_circle.analysis_ability"],
        "watchlist": ["investor.capability_circle.attention_universe", "investor.execution.watchlist_alerts"],
        "search": ["investor.research_consumption.workflow", "investor.information_sources.news_consumption"],
        "download": ["investor.research_consumption.workflow", "investor.record_review.review_record"],
        "model_template": ["investor.decision_framework.strategy_rules", "investor.capability_circle.analysis_ability"],
        "factor_attention": ["investor.capability_circle.analysis_ability", "investor.decision_framework.monitoring_rules"],
    }
    return targets.get(activity_type, ["investor.data_quality.collection_gaps"])


def build_manifest(
    events: List[Dict[str, Any]],
    *,
    collected_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = usable_terminal_events(events)
    workflow_event_count = len(usable_events)
    gap_event_count = len(events) - workflow_event_count
    kind_counts = Counter(event["kind"] for event in events)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in usable_events)
    terminal_counts = Counter((event.get("data") or {}).get("terminal", "unknown") for event in usable_events)
    collection_audit = collection_audit or {}
    gap_only = bool(events) and workflow_event_count == 0 and gap_event_count == len(events)
    scope_policy_filtered_all = bool(collection_audit.get("pro_terminal_scope_policy_filtered_all"))
    no_events = not events
    observed_terminals = sorted(terminal for terminal, count in terminal_counts.items() if count and terminal != "unknown")
    observed_expected_terminals = [terminal for terminal in EXPECTED_PRO_TERMINALS if terminal_counts.get(terminal)]
    missing_expected_terminals = [terminal for terminal in EXPECTED_PRO_TERMINALS if not terminal_counts.get(terminal)]
    unknown_terminal_count = sum(count for terminal, count in terminal_counts.items() if terminal not in EXPECTED_PRO_TERMINALS)
    observed_activities = sorted(activity for activity, count in activity_counts.items() if count and activity not in {"collector_gap", "unknown"})
    observed_expected_activities = [activity for activity in EXPECTED_TERMINAL_ACTIVITY_TYPES if activity_counts.get(activity)]
    missing_expected_activities = [activity for activity in EXPECTED_TERMINAL_ACTIVITY_TYPES if not activity_counts.get(activity)]
    unknown_activity_count = sum(count for activity, count in activity_counts.items() if activity not in EXPECTED_TERMINAL_ACTIVITY_TYPES and activity != "collector_gap")
    field_counts = Counter(
        field
        for event in events
        for field in RECOMMENDED_WORKFLOW_FIELDS
        if (event.get("data") or {}).get(field) not in (None, "", [])
    )
    observed_recommended_fields = [field for field in RECOMMENDED_WORKFLOW_FIELDS if field_counts.get(field)]
    missing_recommended_fields = [field for field in RECOMMENDED_WORKFLOW_FIELDS if not field_counts.get(field)]
    return {
        "schema": "pro_terminal.usage.manifest.v1",
        "collector": COLLECTOR,
        "collected_at": collected_at or now_iso(),
        "event_count": len(events),
        "workflow_event_count": workflow_event_count,
        "gap_event_count": gap_event_count,
        "kind_counts": dict(sorted(kind_counts.items())),
        "activity_counts": dict(sorted(activity_counts.items())),
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "terminal_coverage": {
            "expected_p2_terminals": list(EXPECTED_PRO_TERMINALS),
            "observed_terminals": observed_terminals,
            "observed_expected_terminals": observed_expected_terminals,
            "missing_expected_terminals": missing_expected_terminals,
            "terminal_counts": dict(sorted(terminal_counts.items())),
            "unknown_terminal_count": unknown_terminal_count,
            "real_account_validation": False,
        },
        "activity_coverage": {
            "expected_activity_types": list(EXPECTED_TERMINAL_ACTIVITY_TYPES),
            "observed_activities": observed_activities,
            "observed_expected_activities": observed_expected_activities,
            "missing_expected_activities": missing_expected_activities,
            "activity_counts": dict(sorted(activity_counts.items())),
            "unknown_activity_count": unknown_activity_count,
            "real_account_validation": False,
        },
        "workflow_field_coverage": {
            "recommended_workflow_fields": list(RECOMMENDED_WORKFLOW_FIELDS),
            "observed_recommended_fields": observed_recommended_fields,
            "missing_recommended_fields": missing_recommended_fields,
            "field_counts": dict(sorted(field_counts.items())),
            "real_account_validation": False,
        },
        "workflow_surface_summary": workflow_surface_summary(events),
        "workflow_intensity_summary": workflow_intensity_summary(events),
        "workflow_boundary_proof": workflow_boundary_proof(events, collection_audit=collection_audit),
        "source_audit": source_audit(events, collection_audit=collection_audit),
        "license_policy": {
            "license_boundary": "workflow_metadata_only",
            "licensed_content_mirrored": False,
            "vendor_database_mirror": False,
            "content_preview_max_chars": CONTENT_PREVIEW_MAX_CHARS,
            "credentials_collected": False,
            "license_keys_collected": False,
            "real_account_validation": False,
        },
        "evidence_policy": {
            "vertical_collector": True,
            "collector_writes_investor_wiki_directly": False,
            "personal_workflow_only": True,
            "licensed_content_mirrored": False,
            "vendor_database_mirror": False,
            "real_account_validation": False,
        },
        "collection_readiness": {
            "status": collection_readiness_status(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "can_enter_finclaw": bool(events) and not gap_only and not scope_policy_filtered_all,
            "can_claim_complete_terminal_usage": False,
            "source_collection_scope": source_collection_scope_for_readiness(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
            "license_boundary": "workflow_metadata_only",
            "terminal_coverage_status": coverage_status(events, missing_expected_terminals, "terminal"),
            "activity_coverage_status": coverage_status(events, missing_expected_activities, "activity_type"),
            "workflow_field_coverage_status": coverage_status(events, missing_recommended_fields, "workflow_field"),
            "next_action": collection_next_action(
                gap_only=gap_only,
                no_events=no_events,
                scope_policy_filtered_all=scope_policy_filtered_all,
            ),
        },
    }


def collection_readiness_status(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_filtered_all"
    if gap_only or no_events:
        return "needs_pro_terminal_usage_input"
    return "events_collected"


def source_collection_scope_for_readiness(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "scope_policy_excluded_all"
    if gap_only or no_events:
        return "none"
    return "partial_authorized_input"


def collection_next_action(*, gap_only: bool, no_events: bool, scope_policy_filtered_all: bool) -> str:
    if scope_policy_filtered_all:
        return "Broaden the user authorization scope or provide terminal workflow records that match the current policy."
    if gap_only or no_events:
        return "Provide authorized Wind/Choice/iFinD/Bloomberg workflow export."
    return "Use as investor workflow evidence; continue licensed platform validation."


def coverage_status(events: List[Dict[str, Any]], missing_expected: List[str], noun: str) -> str:
    if not events or all((event.get("data") or {}).get("activity_type") == "collector_gap" for event in events):
        return f"no_{noun}_observed"
    if not missing_expected:
        return f"all_expected_{noun}s_observed"
    return f"partial_expected_{noun}s_observed"


def usable_terminal_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [event for event in events if (event.get("data") or {}).get("activity_type") != "collector_gap"]


def workflow_surface_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_terminal_events(events)
    workflow_topic_counts: Counter[str] = Counter()
    primary_topic_counts: Counter[str] = Counter()
    terminal_topic_counts: Counter[str] = Counter()
    activity_topic_counts: Counter[str] = Counter()
    for event in usable_events:
        data = event.get("data") or {}
        topics = data.get("workflow_topics") if isinstance(data.get("workflow_topics"), list) else []
        if not topics:
            topics = ["unclassified_workflow_topic"]
        for topic in topics:
            topic_value = str(topic)
            workflow_topic_counts[topic_value] += 1
            terminal_topic_counts[f"{data.get('terminal', 'unknown')}:{topic_value}"] += 1
            activity_topic_counts[f"{data.get('activity_type', 'unknown')}:{topic_value}"] += 1
        primary_topic_counts[str(data.get("primary_workflow_topic") or topics[0])] += 1
    return {
        "workflow_event_count": len(usable_events),
        "expected_workflow_topics": list(TERMINAL_WORKFLOW_TOPIC_ORDER[:-1]),
        "workflow_topic_counts": ordered_counts(workflow_topic_counts, TERMINAL_WORKFLOW_TOPIC_ORDER),
        "primary_workflow_topic_counts": ordered_counts(primary_topic_counts, TERMINAL_WORKFLOW_TOPIC_ORDER),
        "missing_expected_workflow_topics": [
            topic for topic in TERMINAL_WORKFLOW_TOPIC_ORDER[:-1] if workflow_topic_counts.get(topic, 0) == 0
        ],
        "terminal_topic_counts": dict(sorted(terminal_topic_counts.items())),
        "activity_topic_counts": dict(sorted(activity_topic_counts.items())),
        "events_with_workflow_topics": sum(1 for event in usable_events if (event.get("data") or {}).get("workflow_topics")),
        "events_with_workspace": sum(1 for event in usable_events if (event.get("data") or {}).get("workspace")),
        "events_with_project": sum(1 for event in usable_events if (event.get("data") or {}).get("project")),
        "events_with_module": sum(1 for event in usable_events if (event.get("data") or {}).get("module")),
        "events_with_function_code": sum(1 for event in usable_events if (event.get("data") or {}).get("function_code")),
        "events_with_menu_path": sum(1 for event in usable_events if (event.get("data") or {}).get("menu_path")),
        "events_with_query": sum(1 for event in usable_events if (event.get("data") or {}).get("query")),
        "events_with_query_terms": sum(1 for event in usable_events if (event.get("data") or {}).get("query_terms")),
        "events_with_parameters": sum(1 for event in usable_events if (event.get("data") or {}).get("parameters")),
        "events_with_symbols": sum(1 for event in usable_events if (event.get("data") or {}).get("symbols")),
        "events_with_symbol_count": sum(1 for event in usable_events if (event.get("data") or {}).get("symbol_count") is not None),
        "events_with_universe": sum(1 for event in usable_events if (event.get("data") or {}).get("universe")),
        "events_with_industries": sum(1 for event in usable_events if (event.get("data") or {}).get("industries")),
        "events_with_regions": sum(1 for event in usable_events if (event.get("data") or {}).get("regions")),
        "events_with_factors": sum(1 for event in usable_events if (event.get("data") or {}).get("factors")),
        "events_with_factor_count": sum(1 for event in usable_events if (event.get("data") or {}).get("factor_count") is not None),
        "events_with_datasets": sum(1 for event in usable_events if (event.get("data") or {}).get("datasets")),
        "events_with_dataset_count": sum(1 for event in usable_events if (event.get("data") or {}).get("dataset_count") is not None),
        "events_with_fields": sum(1 for event in usable_events if (event.get("data") or {}).get("fields")),
        "events_with_field_count": sum(1 for event in usable_events if (event.get("data") or {}).get("field_count") is not None),
        "events_with_workspace_id": sum(1 for event in usable_events if (event.get("data") or {}).get("workspace_id")),
        "events_with_template_name": sum(1 for event in usable_events if (event.get("data") or {}).get("template_name")),
        "events_with_template_id": sum(1 for event in usable_events if (event.get("data") or {}).get("template_id")),
        "events_with_download_format": sum(1 for event in usable_events if (event.get("data") or {}).get("download_format")),
        "events_with_export_path": sum(1 for event in usable_events if (event.get("data") or {}).get("export_path")),
        "events_with_row_count": sum(1 for event in usable_events if (event.get("data") or {}).get("row_count") is not None),
        "events_with_watchlist_size": sum(1 for event in usable_events if (event.get("data") or {}).get("watchlist_size") is not None),
        "events_with_content_preview": sum(1 for event in usable_events if (event.get("data") or {}).get("has_content_preview")),
        "events_with_source_section": sum(1 for event in usable_events if (event.get("data") or {}).get("source_section")),
    }


def workflow_intensity_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable_events = usable_terminal_events(events)
    query_terms: Counter[str] = Counter()
    parameter_keys: Counter[str] = Counter()
    function_codes: Counter[str] = Counter()
    datasets: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    factors: Counter[str] = Counter()
    templates: Counter[str] = Counter()
    workspaces: Counter[str] = Counter()
    workspace_ids: Counter[str] = Counter()
    template_ids: Counter[str] = Counter()
    download_formats: Counter[str] = Counter()
    activity_totals: Dict[str, Counter[str]] = defaultdict(Counter)
    total_export_rows = 0
    max_export_rows = 0
    for event in usable_events:
        data = event.get("data") or {}
        activity = str(data.get("activity_type") or "unknown")
        for term in data.get("query_terms") or []:
            query_terms[str(term)] += 1
        parameters = data.get("parameters")
        if isinstance(parameters, dict):
            for key in parameters:
                parameter_keys[str(key)] += 1
        elif parameters not in (None, "", []):
            parameter_keys["<unstructured>"] += 1
        if data.get("function_code"):
            function_codes[str(data["function_code"])] += 1
        for value in data.get("datasets") or []:
            datasets[str(value)] += 1
        for value in data.get("fields") or []:
            fields[str(value)] += 1
        for value in data.get("factors") or []:
            factors[str(value)] += 1
        if data.get("template_name"):
            templates[str(data["template_name"])] += 1
        if data.get("workspace"):
            workspaces[str(data["workspace"])] += 1
        if data.get("workspace_id"):
            workspace_ids[str(data["workspace_id"])] += 1
        if data.get("template_id"):
            template_ids[str(data["template_id"])] += 1
        if data.get("download_format"):
            download_formats[str(data["download_format"])] += 1
        for field in ("row_count", "symbol_count", "field_count", "dataset_count", "factor_count", "watchlist_size"):
            amount = number_from_data(data.get(field))
            if amount is not None:
                activity_totals[activity][field] += amount
                if field == "row_count":
                    total_export_rows += amount
                    max_export_rows = max(max_export_rows, amount)
    return {
        "workflow_event_count": len(usable_events),
        "events_with_query_terms": sum(1 for event in usable_events if (event.get("data") or {}).get("query_terms")),
        "unique_query_term_count": len(query_terms),
        "query_term_counts": top_counts(query_terms),
        "events_with_parameters": sum(1 for event in usable_events if (event.get("data") or {}).get("parameters")),
        "parameter_key_counts": top_counts(parameter_keys),
        "events_with_export_path": sum(1 for event in usable_events if (event.get("data") or {}).get("export_path")),
        "events_with_row_count": sum(1 for event in usable_events if (event.get("data") or {}).get("row_count") is not None),
        "total_export_rows": total_export_rows,
        "max_export_rows": max_export_rows,
        "events_with_workspace_id": sum(1 for event in usable_events if (event.get("data") or {}).get("workspace_id")),
        "events_with_template_id": sum(1 for event in usable_events if (event.get("data") or {}).get("template_id")),
        "total_symbol_refs": sum(number_from_data((event.get("data") or {}).get("symbol_count")) or 0 for event in usable_events),
        "total_field_refs": sum(number_from_data((event.get("data") or {}).get("field_count")) or 0 for event in usable_events),
        "total_dataset_refs": sum(number_from_data((event.get("data") or {}).get("dataset_count")) or 0 for event in usable_events),
        "total_factor_refs": sum(number_from_data((event.get("data") or {}).get("factor_count")) or 0 for event in usable_events),
        "total_watchlist_size": sum(number_from_data((event.get("data") or {}).get("watchlist_size")) or 0 for event in usable_events),
        "function_code_counts": top_counts(function_codes),
        "dataset_counts": top_counts(datasets),
        "field_counts": top_counts(fields),
        "factor_counts": top_counts(factors),
        "template_counts": top_counts(templates),
        "workspace_counts": top_counts(workspaces),
        "workspace_id_counts": top_counts(workspace_ids),
        "template_id_counts": top_counts(template_ids),
        "download_format_counts": top_counts(download_formats),
        "activity_intensity_totals": {activity: dict(sorted(counter.items())) for activity, counter in sorted(activity_totals.items())},
    }


def workflow_boundary_proof(
    events: List[Dict[str, Any]],
    *,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    usable_events = usable_terminal_events(events)
    activity_counts = Counter((event.get("data") or {}).get("activity_type", "unknown") for event in usable_events)
    terminal_counts = Counter((event.get("data") or {}).get("terminal", "unknown") for event in usable_events)
    field_counts = Counter(
        field
        for event in usable_events
        for field in RECOMMENDED_WORKFLOW_FIELDS
        if (event.get("data") or {}).get(field) not in (None, "", [])
    )
    observed_expected_terminals = [terminal for terminal in EXPECTED_PRO_TERMINALS if terminal_counts.get(terminal)]
    missing_expected_terminals = [terminal for terminal in EXPECTED_PRO_TERMINALS if not terminal_counts.get(terminal)]
    observed_expected_activities = [activity for activity in EXPECTED_TERMINAL_ACTIVITY_TYPES if activity_counts.get(activity)]
    missing_expected_activities = [activity for activity in EXPECTED_TERMINAL_ACTIVITY_TYPES if not activity_counts.get(activity)]
    observed_recommended_fields = [field for field in RECOMMENDED_WORKFLOW_FIELDS if field_counts.get(field)]
    missing_recommended_fields = [field for field in RECOMMENDED_WORKFLOW_FIELDS if not field_counts.get(field)]
    surface = workflow_surface_summary(events)
    intensity = workflow_intensity_summary(events)
    audit = source_audit(events, collection_audit=collection_audit)
    expected_topics = list(TERMINAL_WORKFLOW_TOPIC_ORDER[:-1])
    observed_topics = [topic for topic in expected_topics if surface["workflow_topic_counts"].get(topic)]
    missing_topics = list(surface["missing_expected_workflow_topics"])
    all_expected_terminals = bool(observed_expected_terminals) and not missing_expected_terminals
    all_expected_activities = bool(observed_expected_activities) and not missing_expected_activities
    all_recommended_fields = bool(observed_recommended_fields) and not missing_recommended_fields
    all_expected_topics = bool(observed_topics) and not missing_topics
    if audit.get("pro_terminal_scope_policy_filtered_all"):
        proof_level = "scope_policy_filtered_all"
    elif not usable_events:
        gap_reason = None
        if events:
            gap_reason = (events[0].get("data") or {}).get("gap")
        if gap_reason == "pro_terminal_usage_authorized_input_missing" or audit.get("input_missing_count") or not audit.get("input_count"):
            proof_level = "no_authorized_terminal_input"
        else:
            proof_level = "no_usable_terminal_workflow_records"
    elif all_expected_terminals and all_expected_activities and all_recommended_fields and all_expected_topics:
        proof_level = "strong_partial_workflow_boundary"
    elif len(observed_expected_terminals) >= 2 and len(observed_expected_activities) >= 3 and surface["events_with_workflow_topics"] > 0:
        proof_level = "medium_partial_workflow_boundary"
    else:
        proof_level = "weak_partial_workflow_boundary"
    blockers = []
    if not usable_events:
        blockers.append("authorized_terminal_workflow_export_missing")
    if audit.get("pro_terminal_scope_policy_filtered_all"):
        blockers.append("authorization_scope_excluded_all_records")
    if missing_expected_terminals:
        blockers.append("missing_expected_terminals:" + ",".join(missing_expected_terminals))
    if missing_expected_activities:
        blockers.append("missing_expected_activities:" + ",".join(missing_expected_activities))
    if missing_recommended_fields:
        blockers.append("missing_recommended_workflow_fields:" + ",".join(missing_recommended_fields))
    if missing_topics:
        blockers.append("missing_workflow_topics:" + ",".join(missing_topics))
    if surface["events_with_workflow_topics"] == 0:
        blockers.append("workflow_topic_classification_missing")
    if not audit.get("path_results"):
        blockers.append("path_level_source_audit_missing")
    if audit.get("limit_reached"):
        blockers.append("collection_limit_reached")
    blockers.extend(
        [
            "real_wind_choice_ifind_bloomberg_validation_missing",
            "license_safe_account_review_missing",
            "complete_terminal_usage_history_not_proven",
            "workflow_topic_false_positive_review_missing",
        ]
    )
    return {
        "proof_level": proof_level,
        "authorized_input_observed": bool(usable_events),
        "personal_workflow_only": True,
        "workflow_metadata_only": True,
        "can_enter_finclaw_lake": bool(usable_events),
        "can_feed_investor_wiki_evidence": bool(usable_events),
        "observed_event_count": len(usable_events),
        "terminal_boundary": {
            "observed_terminals": observed_expected_terminals,
            "missing_expected_terminals": missing_expected_terminals,
            "terminal_counts": dict(sorted(terminal_counts.items())),
            "real_account_validation": False,
        },
        "activity_boundary": {
            "observed_activities": observed_expected_activities,
            "missing_expected_activities": missing_expected_activities,
            "activity_counts": dict(sorted(activity_counts.items())),
            "complete_activity_history_claimed": False,
        },
        "workflow_field_boundary": {
            "observed_recommended_fields": observed_recommended_fields,
            "missing_recommended_fields": missing_recommended_fields,
        },
        "workflow_topic_boundary": {
            "expected_workflow_topics": expected_topics,
            "observed_workflow_topics": observed_topics,
            "missing_expected_workflow_topics": missing_topics,
            "workflow_topic_counts": surface["workflow_topic_counts"],
            "events_with_workflow_topics": surface["events_with_workflow_topics"],
            "workflow_topic_false_positive_reviewed": False,
        },
        "workflow_surface_boundary": {
            "events_with_workspace": surface["events_with_workspace"],
            "events_with_project": surface["events_with_project"],
            "events_with_module": surface["events_with_module"],
            "events_with_function_code": surface["events_with_function_code"],
            "events_with_menu_path": surface["events_with_menu_path"],
            "events_with_query": surface["events_with_query"],
            "events_with_query_terms": surface["events_with_query_terms"],
            "events_with_parameters": surface["events_with_parameters"],
            "events_with_symbols": surface["events_with_symbols"],
            "events_with_datasets": surface["events_with_datasets"],
            "events_with_fields": surface["events_with_fields"],
            "events_with_export_path": surface["events_with_export_path"],
            "events_with_row_count": surface["events_with_row_count"],
            "events_with_content_preview": surface["events_with_content_preview"],
        },
        "workflow_intensity_boundary": {
            "query_terms_observed": intensity["events_with_query_terms"] > 0,
            "parameters_observed": intensity["events_with_parameters"] > 0,
            "export_paths_observed": intensity["events_with_export_path"] > 0,
            "row_counts_observed": intensity["events_with_row_count"] > 0,
            "total_export_rows": intensity["total_export_rows"],
            "total_symbol_refs": intensity["total_symbol_refs"],
            "total_field_refs": intensity["total_field_refs"],
            "total_dataset_refs": intensity["total_dataset_refs"],
            "total_factor_refs": intensity["total_factor_refs"],
            "total_watchlist_size": intensity["total_watchlist_size"],
        },
        "source_boundary": {
            "requested_input_count": int(audit.get("input_count") or 0),
            "resolved_input_file_count": int(audit.get("resolved_input_file_count") or 0),
            "input_missing_count": int(audit.get("input_missing_count") or 0),
            "skipped_file_count": int(audit.get("skipped_file_count") or 0),
            "archive_count": int(audit.get("archive_count") or 0),
            "archive_member_count": int(audit.get("archive_member_count") or 0),
            "archive_member_event_count": int(audit.get("archive_member_event_count") or 0),
            "skipped_archive_member_count": int(audit.get("skipped_archive_member_count") or 0),
            "limit_reached": bool(audit.get("limit_reached")),
            "path_level_audit_available": bool(audit.get("path_results")),
            "archive_path_traversal_members_collected": False,
            "windows_drive_archive_members_collected": False,
        },
        "authorization_scope_boundary": {
            "policy": audit.get("pro_terminal_scope_policy", {}),
            "candidate_record_count": audit.get("candidate_record_count", audit.get("parsed_record_count", len(usable_events))),
            "scope_policy_filtered_record_count": audit.get("scope_policy_filtered_record_count", 0),
            "scope_policy_filter_reason_counts": audit.get("scope_policy_filter_reason_counts", {}),
            "pro_terminal_scope_policy_filtered_all": audit.get("pro_terminal_scope_policy_filtered_all", False),
        },
        "license_boundary": {
            "license_boundary": "workflow_metadata_only",
            "licensed_content_mirrored": False,
            "vendor_database_mirror": False,
            "public_market_data_mirror": False,
            "content_preview_max_chars": CONTENT_PREVIEW_MAX_CHARS,
            "credentials_collected": False,
            "license_keys_collected": False,
            "license_safe_account_reviewed": False,
        },
        "wiki_boundary": {
            "event_schema": "collectorx.event.v1",
            "evidence_schema": "finclaw.investor_wiki_evidence.v1",
            "collector_writes_wiki_directly": False,
            "required_flow": [
                "pro-terminal-usage collector",
                "collectorx.event.v1",
                "finclaw.investor_wiki_evidence.v1",
                "SoulMirror investor-portrait distill/organize",
            ],
        },
        "false_claims": {
            "complete_terminal_usage_history_claimed": False,
            "real_account_validation_claimed": False,
            "license_safe_account_review_claimed": False,
            "vendor_database_mirrored": False,
            "licensed_content_body_mirrored": False,
            "public_market_data_mirrored": False,
            "terminal_credentials_collected": False,
            "license_keys_collected": False,
            "order_mutation_supported": False,
            "collector_writes_wiki_directly": False,
        },
        "completion_blockers": blockers,
    }


def source_audit(events: List[Dict[str, Any]], *, collection_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    usable_events = usable_terminal_events(events)
    archives = [
        (event.get("raw_ref") or {}).get("source_archive")
        for event in usable_events
        if (event.get("raw_ref") or {}).get("source_archive")
    ]
    audit = {
        "source_ref_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("path")),
        "archive_member_event_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("archive_member")),
        "archive_count": len(set(archives)),
        "source_section_event_count": sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("source_section")),
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
    }
    if collection_audit:
        audit.update(collection_audit)
        audit["source_ref_count"] = max(
            int(audit.get("source_ref_count") or 0),
            sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("path")),
        )
        audit["archive_member_event_count"] = max(
            int(audit.get("archive_member_event_count") or 0),
            sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("archive_member")),
        )
        audit["archive_count"] = max(int(audit.get("archive_count") or 0), len(set(archives)))
        audit["source_section_event_count"] = max(
            int(audit.get("source_section_event_count") or 0),
            sum(1 for event in usable_events if (event.get("raw_ref") or {}).get("source_section")),
        )
        audit["archive_path_traversal_members_collected"] = False
        audit["windows_drive_archive_members_collected"] = False
    return audit


def build_evidence(
    events: List[Dict[str, Any]],
    *,
    generated_at: Optional[str] = None,
    collection_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    by_target: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    usable_event_list = usable_terminal_events(events)
    for event in usable_event_list:
        for target in event.get("wiki_targets", []):
            by_target[target].append(event)
    evidence = {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": generated_at or now_iso(),
        "generated_from": {
            "collector": COLLECTOR,
            "event_schema": "collectorx.event.v1",
            "event_count": len(usable_event_list),
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
        },
        "coverage_summary": {
            "licensed_content_mirrored": False,
            "personal_workflow_only": True,
            "workflow_metadata_only": True,
            "vendor_database_mirror": False,
            "workflow_surface_summary": workflow_surface_summary(usable_event_list),
            "workflow_intensity_summary": workflow_intensity_summary(usable_event_list),
            "workflow_boundary_proof": workflow_boundary_proof(usable_event_list, collection_audit=collection_audit),
            "route_counts": {target: len(items) for target, items in sorted(by_target.items())},
        },
    }
    return augment_evidence_with_dimensions(evidence, usable_event_list, INVESTOR_WIKI_SUBDIMENSION_RULES)


def classify_workflow_topics(
    record: Dict[str, Any],
    *,
    title: str,
    text: str,
    query: Optional[str],
    symbols: List[str],
    activity_type: str,
    terminal: str,
) -> Tuple[List[str], Dict[str, List[str]]]:
    parts: List[str] = [
        title,
        text,
        query or "",
        activity_type,
        terminal,
        " ".join(symbols),
        " ".join(list_values(record, ["universe", "scope", "stock_pool", "股票池", "样本空间"])),
        " ".join(list_values(record, ["industries", "industry", "行业"])),
        " ".join(list_values(record, ["regions", "region", "markets", "market", "地区", "市场"])),
        " ".join(list_values(record, ["factors", "factor", "因子", "指标"])),
        " ".join(list_values(record, ["datasets", "dataset", "database", "table", "数据集", "数据库", "表"])),
        " ".join(list_values(record, ["fields", "field", "columns", "indicators", "字段", "列", "指标"])),
    ]
    for key in (
        "workspace",
        "workspace_name",
        "project",
        "project_name",
        "strategy",
        "portfolio",
        "module",
        "function",
        "page",
        "screen",
        "function_code",
        "command",
        "api",
        "formula",
        "menu_path",
        "navigation",
        "template_name",
        "template",
        "model_name",
        "download_format",
        "format",
        "file_name",
        "filename",
        "工作区",
        "项目",
        "策略",
        "组合",
        "模块",
        "函数",
        "命令",
        "菜单路径",
        "模板名称",
        "文件名",
    ):
        value = first(record, [key])
        if value:
            parts.append(value)
    searchable = "\n".join(parts)
    lowered = searchable.lower()
    matches: Dict[str, List[str]] = {}
    for topic in TERMINAL_WORKFLOW_TOPIC_ORDER[:-1]:
        hits = topic_term_hits(TERMINAL_WORKFLOW_TOPIC_TERMS[topic], searchable, lowered)
        if hits:
            matches[topic] = hits
    if activity_type == "download":
        matches.setdefault("data_export", []).append("activity:download")
    if activity_type == "watchlist":
        matches.setdefault("portfolio_monitoring", []).append("activity:watchlist")
    if activity_type == "factor_attention":
        matches.setdefault("factor_quant", []).append("activity:factor_attention")
    if activity_type == "model_template" and "valuation_model" not in matches:
        matches.setdefault("valuation_model", []).append("activity:model_template")
    if any(re.search(r"(\.|\s)(hk|us)\b", symbol.lower()) or " hk " in f" {symbol.lower()} " for symbol in symbols):
        matches.setdefault("hk_us_market", []).append("symbol_market")
    topics = [topic for topic in TERMINAL_WORKFLOW_TOPIC_ORDER[:-1] if topic in matches]
    return topics, {topic: matches[topic][:8] for topic in topics}


def topic_term_hits(terms: Iterable[str], text: str, lowered: str) -> List[str]:
    hits: List[str] = []
    for term in sorted(terms):
        if term.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", lowered):
                hits.append(term)
        elif term in text:
            hits.append(term)
    return hits


def ordered_counts(counts: Counter[str], order: Iterable[str]) -> Dict[str, int]:
    result = {key: counts[key] for key in order if counts.get(key)}
    for key, value in sorted(counts.items()):
        if key not in result:
            result[key] = value
    return result


def first(record: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    normalized = {normalize_key(key): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(normalize_key(key))
        if value not in (None, ""):
            return str(value)
    return None


def normalize_key(value: Any) -> str:
    return re.sub(r"[\s_\-/%()（）]+", "", str(value).lower())


def list_values(record: Dict[str, Any], keys: Iterable[str]) -> List[str]:
    for key in keys:
        value = first_raw(record, key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            return split_terms(value)
        if isinstance(value, list):
            return clean_list_items(value)
    return []


def first_raw_any(record: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = first_raw(record, key)
        if value not in (None, ""):
            return value
    return None


def first_raw(record: Dict[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    normalized_key = normalize_key(key)
    for candidate, value in record.items():
        if normalize_key(candidate) == normalized_key:
            return value
    return None


def split_terms(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,，、;；|\n]+", text) if item.strip()]


def split_query_terms(text: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,，、;；|\n\t ]+", text) if item.strip()]


def dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def query_terms_for(record: Dict[str, Any], query: Optional[str]) -> List[str]:
    explicit = list_values(
        record,
        [
            "query_terms",
            "search_terms",
            "keywords",
            "keyword_list",
            "terms",
            "tags",
            "查询词",
            "检索词",
            "关键词列表",
            "标签",
        ],
    )
    if explicit:
        return dedupe(explicit)
    if query:
        return dedupe(split_query_terms(query))
    return []


def parameters_for(record: Dict[str, Any]) -> Any:
    value = first_raw_any(record, ["parameters", "params", "query_params", "filters", "screening", "筛选条件", "参数", "条件"])
    if value in (None, ""):
        return None
    return sanitized(value)


def numeric_value(record: Dict[str, Any], keys: Iterable[str]) -> Optional[int]:
    return number_from_data(first_raw_any(record, keys))


def number_from_data(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[,，\s]", "", value)
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match:
            return int(float(match.group(0)))
    return None


def lineage_ref_for(data: Dict[str, Any]) -> str:
    parts = [
        str(data.get("terminal") or "unknown"),
        str(data.get("workspace_id") or data.get("workspace") or ""),
        str(data.get("project") or ""),
        str(data.get("module") or ""),
        str(data.get("template_id") or data.get("template_name") or ""),
        str(data.get("function_code") or ""),
        str(data.get("file_name") or data.get("export_path") or ""),
        str(data.get("query") or ""),
    ]
    return stable_id(*[part for part in parts if part])


def top_counts(counts: Counter[str], limit: int = 20) -> Dict[str, int]:
    return {key: value for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]}


def clean_list_items(items: List[Any]) -> List[str]:
    cleaned: List[str] = []
    for item in items:
        if isinstance(item, dict):
            value = first(item, ["name", "title", "code", "symbol", "field", "字段", "名称"])
        else:
            value = str(item)
        if value and value != "None":
            cleaned.append(value.strip())
    return cleaned


def symbols_for(record: Dict[str, Any]) -> List[str]:
    return list_values(record, ["symbols", "codes", "tickers", "securities", "证券", "代码", "股票"])


def sanitized(value: Any, key_hint: str = "") -> Any:
    lowered_hint = key_hint.lower()
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            clean[str(key)] = sanitized(item, str(key))
        return clean
    if isinstance(value, list):
        return [sanitized(item, key_hint) for item in value[:200]]
    if isinstance(value, str):
        cap = 800 if any(fragment in lowered_hint for fragment in CONTENT_KEY_FRAGMENTS) else 4000
        return value[:cap]
    return value


def title_tag(html: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(strip_tags(match.group(1))) if match else None


def meta_content(html: str, name: str) -> Optional[str]:
    pattern = (
        r"<meta[^>]+(?:name|property)=[\"']"
        + re.escape(name)
        + r"[\"'][^>]+content=[\"']([^\"']+)[\"'][^>]*>"
    )
    match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(unescape(match.group(1))) if match else None


def html_to_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return normalize_space(strip_tags(html))


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(value))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def infer_title(default_title: str, text: str) -> str:
    for line in text.splitlines()[:30]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return default_title


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{COLLECTOR}:{digest}"
