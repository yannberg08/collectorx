---
name: investor-source-collectors
description: 投资分身采集器分类、路由和证据包工具。用于区分 CollectorX 通用采集器、投资垂直采集器和 investor lens/适配层，并把微信投资讨论、投研文档、雪球活动、基金/理财资产、邮件研报、会议纪要、投资笔记、任务日历、公众号收藏、财经资讯使用痕迹、港美股券商、Wind/Choice/iFinD 专业终端使用痕迹、微博/B站/小红书等用户授权证据标准化为 FinClaw/SoulMirror 的 investor_wiki_evidence.v1，同时保留各 lens 边界证明。
---

# 投资分身采集器分类与路由

## Overview

本技能不是一个“大杂烩采集器”。它是投资分身的分类、路由和证据包工具：帮助 Codex 判断每个通道属于通用采集器、投资垂直采集器，还是基于通用通道的 investor lens。

输出必须先进入 `collectorx.event.v1` lake，再形成 `finclaw.investor_wiki_evidence.v1` 证据包；最终 Wiki 仍由 SoulMirror/FinClaw 的 investor-portrait app 蒸馏组织。

## 分类原则

- `generic`：通用个人数据通道，先忠实采原始证据，不预设它一定是投资数据。例：微信、QQ、邮箱、笔记、文件、日历、任务、飞书、钉钉。
- `vertical`：金融/投资原生通道，源头本身就是账户、投资社区、基金理财、券商、专业终端或财经资讯使用痕迹。例：东方财富、同花顺、雪球、富途、老虎、天天基金、Wind。
- `lens`：投资分身适配层，不重复挖原始数据，只从通用 collector 的 lake 中筛选、标注和路由投资相关证据。例：微信投资讨论、邮件研报、投资笔记、会议纪要。
- `external_research_tool`：公共行情、公告、财报、新闻、研报库、宏观数据。它们服务 FinClaw 研究能力，但不作为用户个人 Wiki 的原始证据采集器。

## 快速开始

```bash
# 查看全部投资分身数据源分类
python <SKILL_DIR>/scripts/investor_sources.py list-sources

# 从用户授权的本地投研文件夹生成 lens 事件、manifest 和证据包
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source research-documents \
  --input ~/Documents/research \
  --out-dir ~/Desktop/research-investor-collect

# 显式授权读取研报/财报/估值表内容；默认不读取二进制文档正文
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source research-documents \
  --input ~/Documents/research \
  --include-content \
  --out-dir ~/Desktop/research-content-investor-collect

# 投研文档产品化入口：先按用户授权的格式、路径、文件名、解析器、主题和关键词收窄，再做投资证据筛选
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source research-documents \
  --input ~/Documents/research \
  --allow-extension "pdf,xlsx,md" \
  --allow-path "投资研究" \
  --allow-research-surface "valuation_model,financial_statement,research_report" \
  --deny-keyword "私人" \
  --out-dir ~/Desktop/research-scoped-investor-collect

# 从 filesystem 的授权元数据 Lake 中筛选投研文件；不读取文件正文
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source research-documents \
  --input ~/Desktop/filesystem-package/lake/filesystem/events.jsonl \
  --out-dir ~/Desktop/research-from-filesystem-events

# 从微信通用 collector 的授权导出里筛选投资讨论
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source wechat-investment-dialogue \
  --input ~/Desktop/wechat-collect.json \
  --out-dir ~/Desktop/wechat-investor-dialogue

# 微信投资讨论产品化入口：先用联系人/群/发送者范围策略收窄，再做投资证据筛选
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source wechat-investment-dialogue \
  --input ~/Desktop/wechat-package/lake/wechat/events.jsonl \
  --allow-chat "投资讨论群,投研朋友" \
  --deny-sender "营销号" \
  --out-dir ~/Desktop/wechat-investor-dialogue

# 审计模式：同时输出未命中的记录，便于回测阈值和白名单
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source email-research \
  --input ~/Desktop/email-events.jsonl \
  --out-dir ~/Desktop/email-research-audit \
  --include-non-matches

# 邮件研报产品化入口：先按用户授权的发件域/文件夹/邮件面谱收窄，再做研报 lens
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source email-research \
  --input ~/Desktop/email-package/lake/email/events.jsonl \
  --allow-email-sender-domain "broker.example,company.example" \
  --allow-email-surface "broker_research_report,roadshow_invite,company_ir_thread" \
  --deny-email-keyword "private" \
  --out-dir ~/Desktop/email-research-audit

# 采集雪球个人活动导出或浏览器保存的 JSON/CSV/文本
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source xueqiu-investor-activity \
  --input ~/Downloads/xueqiu \
  --out-dir ~/Desktop/xueqiu-investor-collect

# 从会议/协作 Lake 中筛选投研会议，并输出会议面谱摘要
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source meeting-minutes \
  --input ~/Desktop/meeting-artifacts/lake/meeting-artifacts/events.jsonl \
  --out-dir ~/Desktop/meeting-minutes-investor-collect

# 只做授权/输入缺口登记，不伪造业务数据
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source china-wealth-assets \
  --out-dir ~/Desktop/china-wealth-preflight
```

## 数据源全集

P0 必做：

- `wechat-investment-dialogue`：lens，读取 `wechat` lake，只筛投资讨论、交易理由、咨询对象。
- `research-documents`：lens，读取 `filesystem`/`notes` lake，只筛研报、财报、公告批注、估值表；若上游 `filesystem` 事件来自 Windows/Linux/macOS 路径，manifest/evidence 会记录路径风格和来源平台边界，但不声明真实跨系统设备验证已经完成。
- `xueqiu-investor-activity`：vertical，采雪球个人自选、关注、发帖、评论、收藏、组合活动。
- `china-wealth-assets`：vertical，采支付宝、天天基金、蛋卷、且慢、银行理财等非股票账户资产。
- `email-research`：lens，读取 `email` lake，只筛邮件研报、券商晨会、调研邀请；支持 sender、sender-domain、folder、mailbox、subject、attachment、email-surface、keyword 授权范围过滤，并输出晨会/研报/路演/IR/公告提醒/附件引用面谱、`email_research_scope_policy` 与 `email_research_boundary_proof.authorization_scope_boundary`。

P1 必做：

- `meeting-minutes`：lens，读取会议/文档/协作通道，只筛路演、调研、投委会、专家会、业绩会、风险讨论和后续行动。
- `investment-notes`：lens，读取 `notes` lake，只筛投资笔记、规则库、复盘。
- `task-calendar-investor`：lens，读取 `ticktick`/日历 lake，只筛交易计划、复盘提醒、研究任务。
- `wechat-article-favorites`：lens，读取微信收藏/公众号通道，只筛用户收藏、阅读、转发的投资文章，并标注券商研究、基本面、策略、行业、估值、组合、风险和宏观政策面谱。
- `financial-news-usage`：vertical，采财联社、华尔街见闻、格隆汇等财经 App 的用户阅读/收藏/订阅/搜索/提醒痕迹，并报告平台/动作覆盖。

P2 必做：

- `hk-us-brokerage`：vertical，采富途、老虎、盈透等港美股资产、持仓、成交、委托、资金流水、分红、换汇，并报告券商/交易表/字段覆盖。
- `pro-terminal-usage`：vertical，采 Wind、Choice、同花顺 iFinD、Bloomberg 等专业终端工作台、自选、搜索、导出、模板、因子、数据集、字段和函数代码痕迹，并报告终端/活动/字段覆盖。
- `social-investment-influence`：lens，读取微博/B站/小红书通用社交 activity，只筛投资内容影响源；支持 platform、action、source-app、domain、creator、topic、keyword 授权范围过滤，并汇总平台/动作/创作者/社交影响主题、`social_influence_event_count`、`social_influence_scope_policy`、social-influence/data-quality/Wiki readiness gates 和 `social_influence_boundary_proof`；输出仍是弱证据，不能单独形成投资结论。

## 采集边界

- 保留用户授权的业务事实，不脱敏破坏投资分身分析。
- 不读取、不输出登录密码、支付密码、交易密码、Cookie、token、设备指纹和原始通信负载。
- 不把公共行情、新闻、公告、研报库当成用户个人证据；只能记录用户自己的阅读、收藏、批注、下载、转发和讨论。
- 没有真实授权或输入时，只输出缺口事件，不能伪造成已采到。
- 每个通道只采它该采的东西：微信不采资产，券商不采聊天，雪球不采全网舆情，笔记不采交易接口。

## 输出

`collect` 会输出：

```text
<out-dir>/
├── lake/<source>/events.jsonl
├── manifest.json
├── investor_wiki_evidence.v1.json
└── SUMMARY.md
```

事件使用 `collectorx.event.v1`，证据包使用 `finclaw.investor_wiki_evidence.v1`，并按投资分身七大维度、20 个子维度提供覆盖情况。
当缺少授权输入、输入不可读、没有投资证据或授权范围过滤后全空时，lens 会输出
validator-safe `kind=profile` gap 事件，路由到
`collectorx.data_quality.collection_gaps`；这些 gap 会被证据包排除，不会变成投资事实。
manifest 会拆分 `event_count`、`usable_event_count` 和 `gap_event_count`；
`research-documents` 还会额外写 `research_document_event_count`，因此 FinClaw 可以区分
真实投研文档事实和采集状态证据；`email-research` 还会额外写
`email_research_event_count`，因此 FinClaw 可以区分真实邮件研报事实和采集状态证据；
`social-investment-influence` 还会额外写 `social_influence_event_count` 和
`can_enter_social_investment_influence_lake`，因此 FinClaw 可以区分真实社交弱影响源和
data-quality gap。

`manifest.json` 会带 `collection_audit`：

- 记录请求输入、缺失输入、逐文件解析结果、候选记录数、命中/过滤数量、扩展名分布、跳过原因和 limit 截断状态。
- 记录 `source_policy`：`--allow-chat`、`--deny-chat`、`--allow-sender`、`--deny-sender` 的配置和过滤数量。这个策略只收窄来源范围，不把普通聊天强行变成投资证据。
- 对 `wechat-investment-dialogue` 输出 `wechat_dialogue_boundary_proof` 与对话面谱：汇总聊天/发送者范围、来源策略、本人/他人发言、群聊/私聊、交易意图、买卖理由、仓位、风险情绪、咨询网络、研究讨论和复盘线索；不声明完整微信历史或完整上下文。
- 对 `research-documents` 明确记录 `content_extraction_policy`：通用 `filesystem` 只做元数据；DOCX/PDF/XLSX/XLSM/XLS/PPTX 正文、表格或幻灯片读取必须显式传入 `--include-content`；`.xls` 会区分 XML Spreadsheet、HTML table、delimited/plain text、renamed OOXML 和 binary BIFF，经 `parser_counts` 写入 manifest；binary BIFF 需要 `xlrd`，不可用时必须记录 `xlrd-biff` / `extract_failed`，不能伪造内容；截图/图片默认只保留元数据；若用户显式传入 `--include-image-ocr` 且本机有 tesseract，才读取图片文字；OCR 不可用时必须在 manifest/path_results 中写明降级原因。
- 对 `research-documents` 额外输出 `document_scope_policy`、`research_corpus_boundary_proof` 和 `lens_surface_summary`：汇总授权输入、格式覆盖、解析器、扩展名/路径/文件名/解析器/研究主题/关键词授权范围、全文/元数据/OCR 边界、上游 filesystem 事件的 Windows/Linux/macOS 路径风格与来源平台、研报/财报/估值表/公告/复盘/截图/表格面谱，并明确不声明完整研究语料库、全盘扫描或真实跨系统设备验证；若研究文档授权范围过滤后全空，gap 原因为 `research_documents_scope_policy_filtered_all`，readiness 为 `scope_policy_filtered_all`，只进入数据质量湖。
- 对 `investment-notes` 输出 `investment_note_boundary_proof`：汇总授权输入、来源应用、预览/全文、标签/路径/URL、候选/命中/过滤数量和投资笔记类型面谱，并明确不声明完整笔记库或完整上下文。
- 对 `task-calendar-investor` 输出 `task_calendar_boundary_proof`：汇总授权输入、上游任务/日历来源、候选/命中/过滤数量、时间/提醒/会议链接/日程质量面谱，并明确不声明完整任务清单、完整日历或完整上下文。
- 对 `meeting-minutes` 输出 `meeting_minutes_boundary_proof`：汇总授权输入、上游会议/协作来源、候选/命中/过滤数量、参会人、会议链接、附件/录制指针和时间覆盖，并明确不声明完整会议历史、完整工作区或默认采集录制正文。
- 对 `wechat-article-favorites` 输出 `wechat_article_boundary_proof`：汇总授权输入、微信收藏上游来源、候选/命中/过滤数量、收藏/阅读/分享/保存动作、公众号来源类型、URL/文章 ID/标签/文本/时间覆盖，以及收藏理由、分享对象、阅读时长/进度、互动计数和标的线索行为边界，并明确不声明完整微信收藏、完整阅读历史或公众号全文爬取。
- 不支持的研究文档扩展名会被跳过，不会因为文件名里有弱投资词就污染 Wiki 覆盖率。

## Lens 分类器

`lens` 类型的数据源默认会先做投资证据筛选，再写入证据包：

- 命中证券/基金代码、交易动作、仓位、估值、研报、财报、调研、复盘等特征才会进入投资证据。
- 事件会带 `data.classification`，包含置信度、命中原因、关键词和证券代码。
- `wechat-investment-dialogue` 会额外标注微信投资对话面谱：交易意图、买卖理由、仓位、风险情绪、咨询网络、研究讨论和复盘线索。
- `investment-notes` 会额外标注投资笔记子类型：复盘、规则库、交易 checklist、估值假设和研究记录；manifest/evidence 会汇总这些面谱。
- `task-calendar-investor` 会额外标注任务/日历面谱：研究任务、交易计划、复盘提醒、财报日程、调研会议和风险检查。
- `meeting-minutes` 会额外标注投研会议面谱：路演、调研、投委会、专家会、业绩会、决策点、风险讨论和后续行动，并汇总上游平台、参会人、附件/录制指针和时间覆盖。
- `wechat-article-favorites` 会额外标注文章信息源面谱：券商研究、公司基本面、市场策略、行业主题、估值方法、组合案例、风险预警和宏观政策，并汇总收藏/阅读/保存/转发动作、公众号来源类型、收藏理由、分享对象、阅读时长/进度、互动计数和标的线索。
- 默认阈值是 `--min-score 0.30`。
- `--include-non-matches` 只用于审计和回测，会把未命中记录也输出，但仍带分类结果。
- 如果授权输入可读但没有投资证据，输出 `no_investment_evidence_matched` profile 缺口事件，不会污染 Wiki 覆盖率。
- 如果所有候选都被来源范围策略、邮件研报授权范围策略、社交影响授权范围策略或投研文档授权范围策略排除，输出对应 profile 缺口事件，提示检查本次白名单和黑名单。

`vertical` 类型的数据源是金融原生通道，默认视为投资证据，但仍会附分类元数据。后续每个 vertical collector 还必须做真实账号/平台验证。

## 参考

- 数据源矩阵：`references/investor-source-profiles.md`
- 分类原则：`../../docs/collector-taxonomy.md`
- 项目事件契约：`../../docs/event-contract.md`
- 项目总矩阵：`../../docs/investor-collector-matrix.md`
