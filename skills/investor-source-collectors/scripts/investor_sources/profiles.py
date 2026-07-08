"""Source profiles and investor Wiki routing for non-broker evidence."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


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


SOURCE_PROFILES: Dict[str, Dict[str, Any]] = {
    "wechat-investment-dialogue": {
        "display_name": "微信投资讨论",
        "priority": "P0",
        "default_kind": "message",
        "evidence_level": "strong_reason",
        "accepted_inputs": ["wechat export", "json", "jsonl", "csv", "txt", "html"],
        "authorization": "User-authorized local WeChat evidence only.",
        "contains": ["personal_message", "contact", "trade"],
        "wiki_targets": [
            "investor.record_review.decision_log",
            "investor.network_collaboration.discussions",
            "investor.behavior.emotion_pattern",
            "investor.decision_framework.buy_framework",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-buy-framework",
            "inv-sell-framework",
            "inv-cognitive-bias",
            "inv-emotion-pattern",
            "inv-decision-adaptation-style",
            "inv-decision-log",
            "inv-consultation-network",
        ],
        "source_policy": {
            "supports_allow_chat": True,
            "supports_deny_chat": True,
            "supports_allow_sender": True,
            "supports_deny_sender": True,
            "policy_does_not_assert_investment_relevance": True,
        },
    },
    "research-documents": {
        "display_name": "本地投研文档",
        "priority": "P0",
        "default_kind": "file",
        "evidence_level": "strong_reason",
        "accepted_inputs": ["folder", "pdf", "md", "txt", "html", "csv", "xlsx", "xls", "docx", "pptx"],
        "authorization": "User-selected local files and folders only.",
        "contains": ["work_confidential", "portfolio"],
        "wiki_targets": [
            "investor.capability_circle.analysis_ability",
            "investor.research_consumption.workflow",
            "investor.record_review.review_record",
            "investor.decision_framework.strategy_rules",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-value-preference",
            "inv-industry-circle",
            "inv-analysis-ability",
            "inv-information-learning-style",
            "inv-buy-framework",
            "inv-sell-framework",
            "inv-review-record",
            "inv-rules-library",
            "inv-information-source",
        ],
        "document_scope_policy": {
            "supports_allow_extension": True,
            "supports_deny_extension": True,
            "supports_allow_path": True,
            "supports_deny_path": True,
            "supports_allow_file_name": True,
            "supports_deny_file_name": True,
            "supports_allow_parser": True,
            "supports_deny_parser": True,
            "supports_allow_research_surface": True,
            "supports_deny_research_surface": True,
            "supports_allow_keyword": True,
            "supports_deny_keyword": True,
            "policy_does_not_assert_investment_relevance": True,
        },
    },
    "xueqiu-investor-activity": {
        "display_name": "雪球投资活动",
        "priority": "P0",
        "default_kind": "watchlist",
        "evidence_level": "medium_attention",
        "accepted_inputs": ["authorized account export", "json", "jsonl", "csv", "html"],
        "authorization": "User-owned Snowball activity only; do not crawl public timelines as personal evidence.",
        "contains": ["portfolio", "personal_message", "contact"],
        "wiki_targets": [
            "investor.opportunity_watchlist.watchlist",
            "investor.capability_circle.attention_universe",
            "investor.information_sources.news_consumption",
            "investor.network_collaboration.discussions",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-value-preference",
            "inv-industry-circle",
            "inv-information-learning-style",
            "inv-style-profile",
            "inv-information-source",
            "inv-consultation-network",
        ],
    },
    "china-wealth-assets": {
        "display_name": "中国基金理财资产",
        "priority": "P0",
        "default_kind": "holding",
        "evidence_level": "strong_portfolio",
        "accepted_inputs": ["Alipay", "Tiantian Fund", "Danjuan", "Qieman", "bank export", "csv", "json"],
        "authorization": "User-authorized account screen/export; never collect payment credentials.",
        "contains": ["money", "portfolio", "trade"],
        "wiki_targets": [
            "external.capital.assets",
            "investor.risk_portfolio.current_assets",
            "investor.risk_portfolio.portfolio_constraints",
            "investor.portfolio.time_preference",
        ],
        "subdimensions": [
            "inv-risk-view",
            "inv-style-profile",
            "inv-portfolio-preference",
            "inv-execution-discipline",
            "inv-time-preference",
        ],
    },
    "email-research": {
        "display_name": "邮件研报与调研",
        "priority": "P0",
        "default_kind": "email",
        "evidence_level": "medium_reason",
        "accepted_inputs": ["email collector events", "eml", "json", "jsonl", "csv"],
        "authorization": "User-authorized mailbox or exported mail files.",
        "contains": ["personal_message", "contact", "work_confidential"],
        "wiki_targets": [
            "investor.information_sources.news_consumption",
            "investor.research_consumption.workflow",
            "investor.network_collaboration.discussions",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-information-learning-style",
            "inv-analysis-ability",
            "inv-information-source",
            "inv-consultation-network",
        ],
        "email_research_scope_policy": {
            "supports_allow_sender": True,
            "supports_deny_sender": True,
            "supports_allow_sender_domain": True,
            "supports_deny_sender_domain": True,
            "supports_allow_folder": True,
            "supports_deny_folder": True,
            "supports_allow_mailbox": True,
            "supports_deny_mailbox": True,
            "supports_allow_subject": True,
            "supports_deny_subject": True,
            "supports_allow_attachment": True,
            "supports_deny_attachment": True,
            "supports_allow_email_surface": True,
            "supports_deny_email_surface": True,
            "supports_allow_keyword": True,
            "supports_deny_keyword": True,
            "policy_does_not_assert_investment_relevance": True,
        },
    },
    "meeting-minutes": {
        "display_name": "投研会议纪要",
        "priority": "P1",
        "default_kind": "note",
        "evidence_level": "strong_reason",
        "accepted_inputs": ["Feishu", "DingTalk", "Tencent Meeting", "minutes", "md", "txt", "json"],
        "authorization": "User-owned or user-attended meeting minutes only.",
        "contains": ["personal_message", "contact", "work_confidential"],
        "wiki_targets": [
            "investor.network_collaboration.discussions",
            "investor.research_consumption.workflow",
            "investor.record_review.decision_log",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-analysis-ability",
            "inv-information-learning-style",
            "inv-buy-framework",
            "inv-sell-framework",
            "inv-review-record",
            "inv-information-source",
            "inv-consultation-network",
        ],
    },
    "investment-notes": {
        "display_name": "投资笔记",
        "priority": "P1",
        "default_kind": "note",
        "evidence_level": "strong_reason",
        "accepted_inputs": ["Obsidian", "Notion", "Youdao", "Evernote", "md", "txt", "json"],
        "authorization": "User-selected local vault/export or authorized note API.",
        "contains": ["work_confidential", "portfolio"],
        "wiki_targets": [
            "investor.decision_framework.strategy_rules",
            "investor.record_review.review_record",
            "investor.capability_circle.analysis_ability",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-risk-view",
            "inv-value-preference",
            "inv-analysis-ability",
            "inv-information-learning-style",
            "inv-buy-framework",
            "inv-sell-framework",
            "inv-emotion-pattern",
            "inv-review-record",
            "inv-rules-library",
        ],
    },
    "task-calendar-investor": {
        "display_name": "投资任务与日历",
        "priority": "P1",
        "default_kind": "task",
        "evidence_level": "medium_process",
        "accepted_inputs": ["TickTick", "calendar", "ics", "json", "csv"],
        "authorization": "User-authorized calendar/task export or API.",
        "contains": ["work_confidential"],
        "wiki_targets": [
            "investor.record_review.review_record",
            "investor.execution.orders",
            "investor.decision_framework.monitoring_rules",
        ],
        "subdimensions": [
            "inv-decision-adaptation-style",
            "inv-review-record",
            "inv-rules-library",
            "inv-execution-discipline",
            "inv-time-preference",
        ],
    },
    "wechat-article-favorites": {
        "display_name": "公众号与微信收藏",
        "priority": "P1",
        "default_kind": "file",
        "evidence_level": "medium_attention",
        "accepted_inputs": ["WeChat favorites", "article html", "json", "csv", "txt"],
        "authorization": "User-owned read/favorite/share evidence only.",
        "contains": ["personal_message"],
        "wiki_targets": [
            "investor.information_sources.news_consumption",
            "investor.capability_circle.attention_universe",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-value-preference",
            "inv-industry-circle",
            "inv-information-learning-style",
            "inv-information-source",
        ],
    },
    "financial-news-usage": {
        "display_name": "财经资讯使用痕迹",
        "priority": "P1",
        "default_kind": "other",
        "evidence_level": "medium_attention",
        "accepted_inputs": ["CLS", "WallstreetCN", "Gelonghui", "read history", "json", "csv"],
        "authorization": "User's own read/save/subscribe history only.",
        "contains": ["none"],
        "wiki_targets": [
            "investor.information_sources.news_consumption",
            "investor.research_consumption.workflow",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-information-learning-style",
            "inv-information-source",
        ],
    },
    "hk-us-brokerage": {
        "display_name": "港美股券商",
        "priority": "P2",
        "default_kind": "holding",
        "evidence_level": "strong_portfolio",
        "accepted_inputs": ["Futu", "Tiger", "IBKR", "csv", "json"],
        "authorization": "User-authorized account export/screen; never collect login credentials.",
        "contains": ["money", "portfolio", "trade"],
        "wiki_targets": [
            "external.capital.assets",
            "investor.risk_portfolio.current_positions",
            "investor.record_review.decision_log",
            "investor.execution.orders",
        ],
        "subdimensions": [
            "inv-risk-view",
            "inv-style-profile",
            "inv-decision-log",
            "inv-portfolio-preference",
            "inv-execution-discipline",
            "inv-time-preference",
        ],
    },
    "pro-terminal-usage": {
        "display_name": "专业终端使用痕迹",
        "priority": "P2",
        "default_kind": "other",
        "evidence_level": "medium_process",
        "accepted_inputs": ["Wind", "Choice", "iFinD", "Bloomberg", "watchlist", "workspace", "json", "csv"],
        "authorization": "User-licensed terminal usage evidence only; respect vendor terms.",
        "contains": ["work_confidential", "portfolio"],
        "wiki_targets": [
            "investor.research_consumption.workflow",
            "investor.capability_circle.factor_attention",
            "investor.information_sources.news_consumption",
        ],
        "subdimensions": [
            "inv-industry-circle",
            "inv-analysis-ability",
            "inv-information-learning-style",
            "inv-rules-library",
            "inv-information-source",
        ],
    },
    "social-investment-influence": {
        "display_name": "社交投资影响源",
        "priority": "P2",
        "default_kind": "other",
        "evidence_level": "weak_attention",
        "accepted_inputs": ["Weibo", "Bilibili", "Xiaohongshu", "favorites", "likes", "watch history", "json", "csv"],
        "authorization": "User-owned likes/favorites/watch history only; do not scrape public content as personal data.",
        "contains": ["personal_message", "contact"],
        "wiki_targets": [
            "investor.information_sources.news_consumption",
            "investor.network_collaboration.discussions",
        ],
        "subdimensions": [
            "inv-market-view",
            "inv-information-learning-style",
            "inv-emotion-pattern",
            "inv-information-source",
            "inv-consultation-network",
        ],
    },
}

SOURCE_CLASSIFICATION: Dict[str, Dict[str, Any]] = {
    "wechat-investment-dialogue": {
        "collector_class": "lens",
        "upstream_collectors": ["wechat"],
        "channel": "微信聊天记录",
        "collects": ["投资讨论", "买卖前后理由", "咨询对象", "情绪和偏差线索"],
        "does_not_collect": ["全量社交画像", "资产余额", "交易密码", "非投资私聊"],
        "collection_method": "从微信通用 collector 的 lake 中按投资实体、交易词、时间线和人工白名单筛选。",
    },
    "research-documents": {
        "collector_class": "lens",
        "upstream_collectors": ["filesystem", "notes"],
        "channel": "本地文件/笔记文件夹",
        "collects": ["研报", "财报", "公告批注", "估值表", "截图", "研究结论"],
        "does_not_collect": ["整个硬盘", "无关私人文件", "公共研报库爬取"],
        "collection_method": "读取用户指定目录或已入湖文件，只索引投资相关文件元数据、摘要和 raw_ref。",
    },
    "xueqiu-investor-activity": {
        "collector_class": "vertical",
        "upstream_collectors": [],
        "channel": "雪球",
        "collects": ["自选", "关注用户/组合/话题", "个人发帖", "评论", "收藏", "用户自己的组合调仓"],
        "does_not_collect": ["全站舆情", "他人完整时间线", "券商成交明细"],
        "collection_method": "用户登录/授权后读取个人活动页、导出文件或本地缓存，输出 watchlist/note/message/holding 事件。",
    },
    "china-wealth-assets": {
        "collector_class": "vertical",
        "upstream_collectors": [],
        "channel": "支付宝/天天基金/蛋卷/且慢/银行理财",
        "collects": ["基金持仓", "理财持仓", "成本", "收益", "交易/申赎记录", "资产快照"],
        "does_not_collect": ["支付密码", "银行卡密码", "消费流水", "非投资支付行为"],
        "collection_method": "用户授权的只读界面、导出文件或官方账单入口；凭证永不入事件。",
    },
    "email-research": {
        "collector_class": "lens",
        "upstream_collectors": ["email"],
        "channel": "邮箱",
        "collects": ["券商晨会", "研报邮件", "调研邀请", "上市公司/项目往来"],
        "does_not_collect": ["全量私人邮件正文进投资 Wiki", "邮箱密码", "非投资订阅"],
        "collection_method": "从 email collector lake 中按发件人、主题、附件、关键词和白名单筛选。",
    },
    "meeting-minutes": {
        "collector_class": "lens",
        "upstream_collectors": ["meeting-artifacts", "feishu", "dingtalk", "wecom"],
        "channel": "飞书/钉钉/腾讯会议/会议纪要文件",
        "collects": ["路演纪要", "调研纪要", "投委会记录", "会议决策点", "参会对象"],
        "does_not_collect": ["所有会议", "无关组织通讯", "未授权录音"],
        "collection_method": "读取用户可访问的会议纪要或导出文件，按证券/行业/研究关键词筛选。",
    },
    "investment-notes": {
        "collector_class": "lens",
        "upstream_collectors": ["notes"],
        "channel": "Obsidian/Notion/有道云/印象笔记",
        "collects": ["投资笔记", "复盘", "规则库", "交易 checklist", "估值假设"],
        "does_not_collect": ["所有生活笔记", "账号 token", "无关知识库"],
        "collection_method": "读取授权笔记库或导出，用目录、标签、证券实体和关键词筛选投资内容。",
    },
    "task-calendar-investor": {
        "collector_class": "lens",
        "upstream_collectors": ["ticktick", "calendar"],
        "channel": "日历/滴答清单/任务系统",
        "collects": ["研究任务", "交易计划", "复盘提醒", "财报日程", "调研安排"],
        "does_not_collect": ["全部生活日程", "私人提醒正文直接进 Wiki"],
        "collection_method": "从任务/日历 lake 中按标签、项目、证券实体、时间窗口筛选。",
    },
    "wechat-article-favorites": {
        "collector_class": "lens",
        "upstream_collectors": ["wechat-favorites"],
        "channel": "公众号/微信收藏",
        "collects": ["投资文章收藏", "阅读痕迹", "转发给自己的材料", "文章 raw_ref"],
        "does_not_collect": ["公众号全量文章库", "非投资收藏", "他人阅读记录"],
        "collection_method": "读取用户微信收藏/导出/保存的文章记录，只保留用户动作和文章指针。",
    },
    "financial-news-usage": {
        "collector_class": "vertical",
        "upstream_collectors": [],
        "channel": "财联社/华尔街见闻/格隆汇等财经资讯 App",
        "collects": ["用户阅读历史", "收藏", "订阅栏目", "自选提醒", "搜索记录"],
        "does_not_collect": ["公共新闻全文库", "平台全站数据", "非用户动作"],
        "collection_method": "读取用户授权账号导出、浏览器保存记录或本地 App 可读缓存。",
    },
    "hk-us-brokerage": {
        "collector_class": "vertical",
        "upstream_collectors": [],
        "channel": "富途/老虎/盈透等港美股券商",
        "collects": ["资产", "持仓", "成交", "委托", "资金流水", "分红", "换汇"],
        "does_not_collect": ["登录密码", "交易密码", "下单/撤单操作", "社交讨论"],
        "collection_method": "用户授权的只读界面、导出文件或官方报表；按券商逐个真实验证。",
    },
    "pro-terminal-usage": {
        "collector_class": "vertical",
        "upstream_collectors": [],
        "channel": "Wind/Choice/iFinD/Bloomberg 等专业终端",
        "collects": ["工作区", "自选", "搜索", "下载", "模型模板", "行业/因子关注"],
        "does_not_collect": ["厂商数据库内容复制", "违反许可的行情/研报转存", "账号凭证"],
        "collection_method": "只采用户工作流和配置痕迹，尊重终端许可边界。",
    },
    "social-investment-influence": {
        "collector_class": "lens",
        "upstream_collectors": ["social-activity"],
        "channel": "微博/B站/小红书",
        "collects": ["投资内容收藏/点赞/观看", "关注的投资创作者", "评论表达", "影响源", "社交影响边界证明"],
        "does_not_collect": ["平台全站内容", "无关娱乐消费", "他人完整主页"],
        "collection_method": "从社交 activity lake 中按投资实体、财经标签、创作者白名单筛选。",
    },
}


def all_profiles() -> List[Dict[str, Any]]:
    return [{"id": source_id, **_with_classification(source_id, profile)} for source_id, profile in sorted(SOURCE_PROFILES.items())]


def get_profile(source_id: str) -> Dict[str, Any]:
    try:
        return _with_classification(source_id, SOURCE_PROFILES[source_id])
    except KeyError as exc:
        known = ", ".join(sorted(SOURCE_PROFILES))
        raise ValueError(f"Unknown source profile '{source_id}'. Known profiles: {known}") from exc


def subdimension_profile_ids(subdimension_id: str) -> List[str]:
    return [
        source_id
        for source_id, profile in sorted(SOURCE_PROFILES.items())
        if subdimension_id in profile.get("subdimensions", [])
    ]


def profile_ids_by_priority(priority: str) -> List[str]:
    return [
        source_id
        for source_id, profile in sorted(SOURCE_PROFILES.items())
        if profile.get("priority") == priority
    ]


def assert_profiles_cover_dimensions() -> None:
    covered = {sub for profile in SOURCE_PROFILES.values() for sub in profile.get("subdimensions", [])}
    missing = [
        child_id
        for dimension in INVESTOR_DIMENSIONS
        for child_id, _name in dimension["children"]
        if child_id not in covered
    ]
    if missing:
        raise AssertionError(f"Investor source profiles do not cover subdimensions: {missing}")


def profile_count_by_priority(profiles: Iterable[Dict[str, Any]] | None = None) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for profile in profiles or SOURCE_PROFILES.values():
        priority = str(profile.get("priority") or "unknown")
        counts[priority] = counts.get(priority, 0) + 1
    return dict(sorted(counts.items()))


def _with_classification(source_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    return {**profile, **SOURCE_CLASSIFICATION.get(source_id, {})}
