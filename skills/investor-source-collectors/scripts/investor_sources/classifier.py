"""Lightweight investment evidence classifier for investor source lenses."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .profiles import get_profile


CODE_RE = re.compile(
    r"(?<!\d)(?:[0368]\d{5}|[159]\d{5}|[48]\d{5})(?:\.(?:SH|SZ|BJ|HK))?(?!\d)",
    re.IGNORECASE,
)
HK_US_RE = re.compile(r"(?<![A-Za-z0-9])(?:HK\.\d{5}|[A-Z]{1,5}\.(?:US|HK)|\$\w{1,8})(?![A-Za-z0-9])")

UNIVERSAL_TERMS = {
    "股票",
    "证券",
    "基金",
    "债券",
    "可转债",
    "ETF",
    "港股",
    "美股",
    "A股",
    "组合",
    "持仓",
    "仓位",
    "估值",
    "回撤",
    "收益",
    "亏损",
    "净值",
    "分红",
    "财报",
    "年报",
    "季报",
    "公告",
    "研报",
    "路演",
    "调研",
    "纪要",
    "行业",
    "赛道",
    "基本面",
    "现金流",
    "ROE",
    "PE",
    "PB",
    "DCF",
}

ACTION_TERMS = {
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "建仓",
    "清仓",
    "调仓",
    "止损",
    "止盈",
    "定投",
    "申购",
    "赎回",
    "打新",
    "换仓",
    "补仓",
    "撤单",
    "成交",
    "委托",
}

REASON_TERMS = {
    "投资逻辑",
    "买入理由",
    "卖出理由",
    "风险点",
    "催化",
    "拐点",
    "护城河",
    "安全边际",
    "复盘",
    "交易计划",
    "交易纪律",
    "能力圈",
    "看多",
    "看空",
    "高估",
    "低估",
}

SOURCE_TERMS = {
    "wechat-investment-dialogue": ACTION_TERMS | REASON_TERMS | {"老师", "券商", "私募", "公募", "投顾"},
    "research-documents": UNIVERSAL_TERMS | REASON_TERMS | {"模型", "估值表", "深度报告", "跟踪报告"},
    "email-research": UNIVERSAL_TERMS | {"晨会", "邀请函", "调研邀请", "路演邀请", "证券研究", "研究所", "首席"},
    "meeting-minutes": UNIVERSAL_TERMS | REASON_TERMS | {"投委会", "电话会", "专家会", "交流会"},
    "investment-notes": UNIVERSAL_TERMS | ACTION_TERMS | REASON_TERMS | {"checklist", "watchlist"},
    "task-calendar-investor": ACTION_TERMS | {"复盘", "盯盘", "财报日", "预约调研", "研究任务", "跟踪"},
    "wechat-article-favorites": UNIVERSAL_TERMS | REASON_TERMS | {"财经", "券商", "研究所", "投研", "投资公众号", "股票公众号"},
    "social-investment-influence": UNIVERSAL_TERMS | {"大V", "财经博主", "投教", "实盘"},
}

BROKER_OR_RESEARCH_SENDERS = {
    "证券",
    "研究所",
    "research",
    "strategy",
    "morning",
    "晨会",
    "中信",
    "中金",
    "华泰",
    "国泰君安",
    "招商",
    "广发",
    "国金",
    "海通",
    "申万",
    "东方证券",
}

RESEARCH_FILE_HINTS = {
    "研报",
    "研究",
    "财报",
    "年报",
    "季报",
    "公告",
    "估值",
    "模型",
    "估值表",
    "复盘",
    "调研",
    "纪要",
    "路演",
    "深度报告",
    "跟踪报告",
    "股票池",
    "基金池",
    "持仓分析",
    "交易复盘",
    "DCF",
}


def classify_record(source_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """Return investment-match metadata for one normalized candidate record."""

    profile = get_profile(source_id)
    collector_class = profile.get("collector_class")
    text = searchable_text(record)
    lowered = text.lower()
    reasons: List[str] = []
    matched_terms: List[str] = []
    score = 0.0

    code_matches = sorted(set(CODE_RE.findall(text) + HK_US_RE.findall(text)))
    if code_matches:
        score += 0.35
        reasons.append("matched_security_code")

    universal_hits = term_hits(UNIVERSAL_TERMS, text, lowered)
    if universal_hits:
        score += min(0.40, len(universal_hits) * 0.08)
        reasons.append("matched_financial_terms")
        matched_terms.extend(universal_hits[:8])

    action_hits = term_hits(ACTION_TERMS, text, lowered)
    if action_hits:
        score += min(0.54, len(action_hits) * 0.18)
        reasons.append("matched_trade_action_terms")
        matched_terms.extend(action_hits[:8])

    reason_hits = term_hits(REASON_TERMS, text, lowered)
    if reason_hits:
        score += min(0.36, len(reason_hits) * 0.12)
        reasons.append("matched_decision_reason_terms")
        matched_terms.extend(reason_hits[:8])

    source_hits = term_hits(SOURCE_TERMS.get(source_id, set()), text, lowered)
    if source_hits:
        score += min(0.30, len(source_hits) * 0.10)
        reasons.append("matched_source_profile_terms")
        matched_terms.extend(source_hits[:8])

    score += source_specific_score(source_id, record, text, lowered, reasons, matched_terms)

    if collector_class == "vertical":
        score = max(score, 0.95)
        reasons.append("vertical_investment_source")

    confidence = min(1.0, round(score, 3))
    return {
        "is_investment_evidence": collector_class == "vertical" or confidence >= 0.30,
        "confidence": confidence,
        "threshold": 0.30,
        "reasons": stable_unique(reasons),
        "matched_terms": stable_unique(matched_terms)[:20],
        "matched_symbols": code_matches[:20],
        "classifier": "investor-source-keyword-v1",
    }


def should_keep_event(source_id: str, classification: Dict[str, Any], *, min_score: float, include_non_matches: bool) -> bool:
    profile = get_profile(source_id)
    if profile.get("collector_class") == "vertical":
        return True
    if include_non_matches:
        return True
    return bool(classification.get("is_investment_evidence")) and float(classification.get("confidence") or 0) >= min_score


def searchable_text(record: Dict[str, Any]) -> str:
    parts: List[str] = []
    collect_strings(record, parts)
    return "\n".join(part for part in parts if part)[:20000]


def collect_strings(value: Any, parts: List[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        parts.append(value)
        return
    if isinstance(value, (int, float, bool)):
        parts.append(str(value))
        return
    if isinstance(value, Path):
        parts.append(str(value))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"password", "token", "cookie", "authorization", "session", "secret"}:
                continue
            parts.append(str(key))
            collect_strings(item, parts)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value[:80] if isinstance(value, list) else list(value)[:80]:
            collect_strings(item, parts)


def term_hits(terms: Iterable[str], text: str, lowered: str) -> List[str]:
    hits = []
    for term in sorted(terms):
        probe = term.lower()
        if ascii_term_match(probe, lowered) if term.isascii() else (term in text):
            hits.append(term)
    return hits


def ascii_term_match(term: str, lowered: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return re.search(pattern, lowered) is not None


def source_specific_score(
    source_id: str,
    record: Dict[str, Any],
    text: str,
    lowered: str,
    reasons: List[str],
    matched_terms: List[str],
) -> float:
    score = 0.0
    if source_id == "email-research":
        sender_subject = " ".join(str(record.get(key) or "") for key in ("from", "sender", "subject", "title", "发件人", "主题"))
        hits = term_hits(BROKER_OR_RESEARCH_SENDERS, sender_subject, sender_subject.lower())
        if hits:
            score += 0.35
            reasons.append("matched_broker_or_research_sender_subject")
            matched_terms.extend(hits[:8])
        if any(str(record.get(key) or "") for key in ("attachment", "attachments", "附件")):
            score += 0.10
            reasons.append("has_research_attachment_ref")

    if source_id in {"research-documents", "investment-notes", "wechat-article-favorites"}:
        path_title = " ".join(str(record.get(key) or "") for key in ("path", "title", "name", "file_name", "标题", "名称"))
        hits = term_hits(RESEARCH_FILE_HINTS, path_title, path_title.lower())
        if hits:
            score += 0.30
            reasons.append("matched_research_file_or_title")
            matched_terms.extend(hits[:8])

    if source_id == "task-calendar-investor":
        if any(token in text for token in ("提醒", "日程", "待办", "deadline", "due", "复盘")):
            score += 0.12
            reasons.append("matched_task_or_calendar_context")

    if source_id == "wechat-investment-dialogue":
        if any(token in text for token in ("我买", "我卖", "准备买", "准备卖", "能不能买", "要不要卖")):
            score += 0.25
            reasons.append("matched_owner_decision_phrase")

    return score


def stable_unique(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
