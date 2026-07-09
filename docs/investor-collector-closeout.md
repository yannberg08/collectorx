# FinClaw 投资分身采集器收口验收表

日期：2026-07-09

这份文档用于把 CollectorX 的 P0/P1/P2 长任务从“继续扩张”切换到“可交付收口”。
它不是新的功能规划，也不是施工记录，而是给 FinClaw 产品、调度、测试和人工验收看的
最终口径。

## 当前结论

当前仓库已经形成 30 个 FinClaw catalog 条目：

| 等级 | 数量 | 条目 |
| --- | ---: | --- |
| `production-candidate` | 1 | `eastmoney-portfolio` |
| `deep-beta` | 2 | `ths-portfolio`, `qq` |
| `baseline+audit` | 27 | 其余 P0/P1/P2 与 supporting 条目 |

按优先级看：

| 优先级 | 数量 | 当前交付口径 |
| --- | ---: | --- |
| P0 | 12 | 东方财富可做受控生产候选；同花顺交易为深度 beta；其他 P0 是可运行的授权导入、本地扫描或 lens beta |
| P1 | 13 | 可做授权导入、文件/ZIP/历史副本 beta，不宣称真实账号全自动完成 |
| P2 | 4 | 可做专业用户 beta，不宣称完整券商边界、完整终端工作流或投资结论 |
| supporting | 1 | `qq` 作为 supporting communication deep-beta，不进入 P0/P1/P2 扩张范围 |

工程资产完成度约为 70%-75%。可投产完成度约为 45%-50%。差距主要来自真实账号、
真实设备、真实导出样本和 Wiki 回测，而不是目录缺失。

## 范围冻结

收口阶段遵守这些规则：

1. 不新增采集器。
2. 不重写已经迁移且完整的采集器，例如 `wechat-export`。
3. 不把 `baseline+audit` 改写成 `production-candidate`，除非有真实账号或真实设备验证记录。
4. 不用一个通道采所有数据。每个采集器只采自己负责的证据面。
5. 不把 gap、preflight、空包、filtered-all 结果喂给 Investor Wiki 当个人事实。
6. 不为了“看起来完整”复制公共市场新闻、公共研报库或平台全站内容。

允许做的收口工作只有三类：

1. 修复会导致现有采集器无法运行、无法验证、无法被 FinClaw 调用的问题。
2. 补齐调用文档、验收分级、真实验证缺口和风险边界。
3. 基于已有 fixture、真实授权样本或真实设备运行结果更新证据。

## 可对外测试分级

| 产品层级 | 可展示对象 | FinClaw 展示方式 | 必须提示 |
| --- | --- | --- | --- |
| Guarded production candidate | `eastmoney-portfolio` | 受控一键采集，用户登录并解锁交易页后只读采集 | 当前已在 macOS 路径验证，仍需 Windows/Linux 和更多账户样本 |
| Deep beta | `ths-portfolio`, `qq` | 邀请制 beta，适合真实设备继续补样本 | 不宣称覆盖所有系统、所有账户状态 |
| Import/local beta | 大多数 `baseline+audit` generic/vertical | 用户选择授权文件、目录、ZIP、浏览器历史副本或本地导出 | 这是 beta 导入，不是完整账号托管 |
| Lens beta | `wechat-investment-dialogue`, `research-documents`, `email-research`, `meeting-minutes`, `investment-notes`, `task-calendar-investor`, `wechat-article-favorites`, `social-investment-influence` | 只在上游 Lake 已存在后运行 | lens 不能自己采原始账号数据 |

## P0 收口状态

| Collector | 状态 | 能给投资分身的元数据 | 收口前不能宣称 |
| --- | --- | --- | --- |
| `eastmoney-portfolio` | `production-candidate` | 资产、持仓、成交、委托、资金流水、本地投资行为、授权范围审计、强交易边界 | 全平台完成、全账户状态完成 |
| `ths-portfolio` | `deep-beta` | 同花顺成交、持仓估算、元数据、只读 GUI 快照、授权范围审计 | 生产可用、所有系统/账户完成 |
| `ths-watchlist` | `baseline+audit` | 自选、关注池、分组、标签、备注、关注时间、注意力边界 | 持仓、成交、资金流水 |
| `wechat` | `baseline+audit` | 微信正文、联系人/群、发送者、时间线、个人沟通证据、gap 与 source audit | 直接产出投资结论 |
| `wechat-investment-dialogue` | `baseline+audit` | 投资理由、咨询对象、情绪、偏差、决策上下文、聊天/发送者范围审计 | 自己访问微信数据库 |
| `filesystem` | `baseline+audit` | 授权文件元数据、路径风格、扩展名、修改时间、来源审计 | 默认读取所有文件正文 |
| `research-documents` | `baseline+audit` | 研报、财报、公告、估值表、复盘文档、显式授权内容抽取 | 公共研报库爬虫 |
| `email` | `baseline+audit` | 邮箱元数据、正文策略、附件引用、本机邮箱/IMAP/导出包审计 | 未授权登录或默认全文进入 Wiki |
| `email-research` | `baseline+audit` | 券商晨会、研报、IR、路演调研邀请、公告提醒、附件引用面谱 | 邮箱本身的原始采集 |
| `xueqiu-watchlist` | `baseline+audit` | 雪球自选、关注池、关注边界、attention universe | 券商交易事实 |
| `xueqiu-investor-activity` | `baseline+audit` | 关注、发帖、评论、收藏、保存页、组合活动、雪球浏览痕迹 | 自动真实账号全量适配 |
| `china-wealth-assets` | `baseline+audit` | 基金、理财、现金管理、资产快照、持仓、流水、字段契约 | 完整资产边界已验证 |

P0 收口优先级：

1. 只修阻塞：东方财富、同花顺交易、微信、邮箱、雪球、基金理财的验证和调用问题。
2. 真实验证优先于功能新增：每个 P0 至少补一条真实账号、真实设备或真实导出样本记录。
3. 任何 gap-only 包只能进入 `collectorx.data_quality.collection_gaps`。

## P1 收口状态

| Collector | 状态 | 能给投资分身的元数据 | 收口前不能宣称 |
| --- | --- | --- | --- |
| `notes` | `baseline+audit` | Obsidian、Notion、有道云、印象笔记、Markdown/HTML/JSON/ENEX/ZIP、来源和标签审计 | 所有笔记平台真实账号完成 |
| `investment-notes` | `baseline+audit` | 投资笔记、规则库、复盘、估值假设、checklist | 通用笔记直接写 Wiki |
| `ticktick` | `baseline+audit` | SoulMirror 对齐的任务快照、离线导入、项目/标签/关键词审计 | 托管 OAuth 已完成 |
| `calendar` | `baseline+audit` | 日历事件、会议时间、重复、提醒、冲突和时间质量 | 所有日历账号托管完成 |
| `task-calendar-investor` | `baseline+audit` | 交易计划、复盘提醒、研究任务、财报日程、风险检查 | 自己采任务/日历账号 |
| `feishu` | `baseline+audit` | 飞书消息、文档、文件、会议、录制指针、ZIP 导入审计 | 真实飞书账号 API 全面完成 |
| `meeting-artifacts` | `baseline+audit` | 会议纪要、逐字稿、字幕、参与人、链接、平台归一化 | 自动覆盖所有会议平台 |
| `dingtalk` | `baseline+audit` | 钉钉授权导出中的消息、会话、联系人、文件和会议指针 | 钉钉云端账号全量采集 |
| `wecom` | `baseline+audit` | 企业微信授权导出中的消息、会话、联系人、文件和会议指针 | 企业微信云端账号全量采集 |
| `meeting-minutes` | `baseline+audit` | 路演、调研、投委会、专家会、业绩会、决策点、行动项、风险讨论 | 自己采会议平台账号 |
| `wechat-favorites` | `baseline+audit` | 微信收藏、公众号文章、阅读/收藏/保存/转发动作、来源账号审计 | 公众号全站抓取 |
| `wechat-article-favorites` | `baseline+audit` | 投资公众号文章面谱、收藏理由、分享对象、阅读进度、互动计数 | 直接代表研究结论 |
| `financial-news-usage` | `baseline+audit` | 财联社、华尔街见闻、格隆汇等用户阅读、收藏、订阅、搜索、提醒痕迹 | 公共新闻内容库 |

## P2 收口状态

| Collector | 状态 | 能给投资分身的元数据 | 收口前不能宣称 |
| --- | --- | --- | --- |
| `hk-us-brokerage` | `baseline+audit` | 富途、老虎、盈透资产、持仓、成交、委托、资金、分红、换汇、税费、保证金 | 完整港美股券商边界 |
| `pro-terminal-usage` | `baseline+audit` | Wind、Choice、iFinD、Bloomberg 的工作区、自选、搜索、下载、模板、因子、字段、查询强度 | 复制终端许可内容或供应商数据库 |
| `social-activity` | `baseline+audit` | 微博、B站、小红书关注、点赞、收藏、观看、评论、分享、浏览历史和弱影响源 | 投资结论或强证据 |
| `social-investment-influence` | `baseline+audit` | 投资内容影响源、创作者、主题、平台动作、corroboration candidate | 单独形成 Wiki 事实 |

## FinClaw 调用入口

产品侧不要直接读 README 表格来拼命令。标准入口是：

1. `collectors/finclaw-investor-catalog.json`
2. `collectors/finclaw-invocation-contracts.json`
3. `tools/finclaw_catalog.py doctor/runbook/batch-manifest/plan --json`
4. `tools/run_finclaw_batch.py --json`，真实执行时再加 `--execute`
5. `tools/validate_collector_package.py <out-dir> --collector <id>`
6. `tools/validate_investor_wiki_evidence.py <investor_wiki_evidence.v1.json>`

FinClaw 可以展示的用户步骤来自 invocation contract：

- authorization mode
- user step
- preflight
- failure state
- product surface
- evidence role

如果 helper 没返回可执行 `argv`，产品层不要自己拼命令。

## 最终交付清单

收口完成前只需要补齐这些证据：

1. `PYTHON=.venv/bin/python bash test_collectors.sh` 通过。
2. `.venv/bin/python tools/validate_project.py` 通过。
3. catalog、invocation contracts 和 skill metadata 的 JSON 格式通过。
4. README、productization control board、production readiness 和本收口表互相引用。
5. 对每个 `production-candidate` 和 `deep-beta` 条目有明确真实验证或剩余阻塞记录。
6. 对每个 `baseline+audit` 条目有明确“可 beta 使用方式”和“不能宣称什么”。
7. Git 工作区干净，最新 commit 已 push。

## 下一步不再扩张

收口后的下一阶段不是继续增加 P0/P1/P2 名单，而是按真实用户样本推进 G3/G4：

1. P0：东方财富跨系统、同花顺多账户、微信真实 lake、邮箱真实根目录/邮箱、雪球真实账号/历史、基金理财真实导出。
2. P1：笔记、任务日历、会议协作、微信收藏、财经资讯使用痕迹的真实账号或真实导出回测。
3. P2：港美股券商、专业终端、社交活动的真实样本、许可边界和弱证据误判回测。

在这些真实证据补齐之前，大多数采集器保持 `baseline+audit` 是正确状态。
