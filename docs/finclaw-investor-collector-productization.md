# FinClaw 投资采集器产品化控制板

这份文档是给 FinClaw 产品层、任务调度层和人工验收使用的总账。机器可读版本在
`collectors/finclaw-investor-catalog.json`。如果两者冲突，以 JSON 目录为调度
入口，以 `docs/production-readiness.md` 为诚实状态说明。

## 当前结论

P0/P1/P2 已经全部摆脱“只做占位”的状态。当前工程状态是：

| 层级 | 当前状态 | 可给 FinClaw 的产品动作 |
| --- | --- | --- |
| P0 | 东方财富达到当前 macOS 真实账户 `production-candidate`；同花顺为 `deep-beta`；微信、研报、邮件、雪球、基金理财进入 `baseline+audit` | 东方财富可做受控一键采集；其他 P0 先做授权导入/本地扫描/镜头 lens 的 beta 流程 |
| P1 | 笔记、任务日历、会议协作、微信收藏、财经资讯使用痕迹全部进入 `baseline+audit` | 可展示为“授权导入/选择文件/选择历史副本”的 beta 采集器，真实账号 API 逐个平台补验证 |
| P2 | 港美股券商、专业终端、社交活动全部进入 `baseline+audit` | 可做授权导入 beta，不可宣称完整资产边界、完整终端工作流或投资结论 |

不能把大多数采集器标成 `production-candidate`，原因不是代码占位，而是缺真实账号、
真实设备、真实导出文件的授权验证。这个边界必须保留，否则后续 Wiki 会把“解析器能跑”
误当成“用户数据已经完整采集”。

## FinClaw 调用规则

FinClaw 应按下面顺序调用：

1. 读取 `collectors/finclaw-investor-catalog.json`，展示采集器名称、优先级、状态、
   允许采集内容、禁止采集内容和前置条件。
   同时读取 `collectors/finclaw-invocation-contracts.json`，获得机器可读的
   授权方式、用户动作、preflight、失败状态、产品展示面和证据角色。
2. 读取 `collectors/generic/*.yaml`、`collectors/vertical/*.yaml`、
   `collectors/lenses/*.yaml`，确认 `armed`、`scope.collects` 和 `scope.excludes`。
3. 调用 `python3 tools/finclaw_catalog.py doctor/runbook/batch-manifest --json`
   生成产品侧设置页、批量顺序和可执行清单。产品执行时只运行
   `ready_steps[*].argv` 或 `plan.argv`，不要重新解析展示用 `command` 字符串。
4. 可用 `python3 tools/run_finclaw_batch.py --json` 做 dry-run 检查；只有在用户完成
   授权且 helper 返回 ready 后，才加 `--execute` 执行采集器命令。
5. 采集完成后先运行 helper 返回的 `package_validation.argv` 或
   `ready_steps[*].post_run_validation.argv`；事件包、manifest 或隐私字段未通过时，
   不能进入持久 Lake。
6. 采集结果必须先进入 `collectorx.event.v1` lake，再进入
   `finclaw.investor_wiki_evidence.v1`，最终 Wiki 由 FinClaw/SoulMirror distill 层写入。
7. 如果采集器输出 `investor_wiki_evidence.v1.json`，FinClaw 必须先运行
   `python3 tools/validate_investor_wiki_evidence.py <path>`；未通过 7 大维度/20 子维度
   合同校验的证据包不能进入投资分身 Wiki distill。
8. 如果 `manifest.json` 表示 gap、缺平台、缺字段、无真实账号验证，产品层展示为
   “未完成采集/证据不足”，不能把它当成个人事实。

## 展示闸门

| readiness | 产品展示建议 |
| --- | --- |
| `production-candidate` | 可展示一键采集，但仍要列明授权和只读边界 |
| `deep-beta` | 可展示 beta 采集，提示真实设备覆盖仍在扩大 |
| `baseline+audit` | 可展示“授权导入/选择文件/选择导出包”流程，不做完整性承诺 |
| `baseline` | 可在高级/实验入口展示，需要更强审计 manifest 后再推广 |
| `migrated-review` | 默认隐藏或只给开发者，完成来源、许可和边界复核后再进入产品 |

## P0 采集器

| Collector | 职责 | 当前状态 | 下一步真实验证 |
| --- | --- | --- | --- |
| `eastmoney-portfolio` | 东方财富资产、持仓、成交、委托、资金流水和本地投资行为 | `production-candidate` on current macOS | Windows/Linux 真机、更多账户样本 |
| `ths-portfolio` | 同花顺交易、持仓、元数据和只读 GUI 快照 | `deep-beta` | 多账户、多系统真机验证 |
| `ths-watchlist` | 同花顺自选股、关注池和机会池 | `baseline+audit`；已进入 FinClaw investor catalog，授权导入 CSV/JSON/Excel/text 自选列表，输出标准 Lake、manifest 和 7/20 Wiki attention-universe 证据；不能替代持仓、成交、委托或资金流水 | 真实同花顺自选导出/本地库验证、Windows/macOS/Linux 路径验证、和交易/研究交叉回测 |
| `wechat` + `wechat-investment-dialogue` | 微信原始对话和投资讨论 lens | `baseline+audit`；generic wechat 输出标准包，lens 支持联系人/群/发送者来源策略、source-policy gap、微信对话边界证明和交易意图/买卖理由/仓位/风险情绪/咨询网络/研究讨论/复盘面谱 | WeChat 4.x key/平台路径、真实 lake、联系人/群/发送者 allowlist 和交易前后回测 |
| `filesystem` + `research-documents` | 文件元数据、研报/财报/估值表内容 lens | `baseline+audit`；filesystem 标准包记录授权根、扩展名覆盖、跳过原因和逐根目录结果，research-documents 负责内容授权、逐输入审计、研究语料边界证明、研报/财报/估值/公告/复盘/截图/表格面谱、截图默认 metadata-only、显式 `--include-image-ocr` 本地 tesseract 适配和 Wiki 证据路由 | Windows/Linux 真机、本地真实样本、中文截图 OCR 质量评审 |
| `email` + `email-research` | 邮箱原始通道和券商/IR/研报邮件 lens | `baseline+audit`；IMAP 和本地导入都能输出标准包，本地导入支持 EML、Apple Mail EMLX、Maildir、MBOX、JSON/CSV/TSV/ZIP；manifest 记录账户/文件夹审计、逐输入导入审计、Apple Mail/Maildir 计数、跳过文件/ZIP 成员原因、字段覆盖、正文/附件策略、邮箱边界证明和 generic-to-lens 边界 | 注册真实邮箱、附件/正文泄漏评审、真实发件人回测 |
| `xueqiu-watchlist` + `xueqiu-investor-activity` | 雪球自选、关注、发帖、评论、收藏、保存页、组合活动 | `baseline+audit`；manifest 记录来源、HAR 网络包、ZIP、字段覆盖、活动覆盖证明和分页完整性审计；活动采集器可解析用户授权的 `xueqiu.com` 浏览器响应体并剥离请求头/Cookie/Authorization/URL 查询串；自选和活动均可输出 7/20 Wiki 证据包，但不当作强交易事实 | 真实账号/HAR 样本、真实分页和频率边界 |
| `china-wealth-assets` | 支付宝、天天基金、蛋卷、且慢、银行理财资产 | `baseline+audit`；manifest 记录平台覆盖、字段覆盖、账户边界、资产边界证明强度、资产面、币种、交易方向、HAR 网络包、来源审计和资产金额汇总；可解析用户授权的基金/理财平台浏览器响应体并剥离请求头/Cookie/Authorization/URL 查询串 | 各平台真实 HAR/导出/只读屏幕、完整资产边界证明 |

## P1 采集器

| Collector | 职责 | 当前状态 | 下一步真实验证 |
| --- | --- | --- | --- |
| `notes` + `investment-notes` | Obsidian、Notion、有道云、印象笔记和投资笔记 lens | `baseline+audit`；generic notes manifest 记录平台覆盖、字段覆盖、CSV/TSV 表格导入审计、逐输入解析结果、跳过文件/ZIP 成员原因、内容策略和 generic-to-lens 边界；investment-notes lens 记录复盘/规则库/checklist/估值假设/研究记录子类型面谱、来源应用、预览/全文边界和投资笔记边界证明 | Notion/有道/印象真实账号、Windows/Linux vault、真实笔记语料误判回测 |
| `ticktick` + `calendar` + `task-calendar-investor` | 任务、日历、交易计划、复盘提醒；TickTick 主路径对齐 SoulMirror YAML + AgentRunner + skill，输出任务快照数组并由 daemon 写 `lake/ticktick/events.jsonl`；离线导出 helper 只写 `exports/ticktick/events.jsonl`；calendar 记录时长、跨天、异常时间段和同日历冲突；lens 汇总研究任务、交易计划、复盘提醒、财报日程、调研会议、风险检查、时间质量面谱和任务日历边界证明 | `baseline+audit` | 部署托管 TickTick OAuth Broker、真实账号 recurring/timezone 回测、Apple/Google/Outlook/飞书等真实日历 |
| `feishu` + `meeting-artifacts` + `dingtalk` + `wecom` + `meeting-minutes` | 飞书/会议纪要、协作导出、投研会议 lens，含 ZIP 跳过成员审计、逐文件解析结果、路演/调研/投委会/专家会/业绩会/风险/后续行动面谱和会议边界证明 | `baseline+audit` | 飞书/钉钉/企业微信/腾讯会议真实账号 API 和导出、参会人归一化、附件/录制指针验证 |
| `wechat-favorites` + `wechat-article-favorites` | 微信收藏、公众号文章动作和投资文章 lens | `baseline+audit`；generic manifest 记录动作覆盖、字段覆盖、逐输入解析结果、跳过文件/ZIP 成员原因、内容策略和 generic-to-lens 边界；lens 记录收藏/阅读/保存/转发动作、公众号来源类型、券商研究/基本面/策略/行业/估值/组合/风险/宏观文章面谱和文章边界证明 | 真实微信收藏库、公众号阅读动作、标签 allowlist、误判回测 |
| `financial-news-usage` | 华尔街见闻、财联社、格隆汇阅读/收藏/订阅/搜索/提醒 | `baseline+audit`；manifest 记录平台/动作/主题覆盖、字段覆盖、逐输入解析结果、跳过文件/ZIP 成员原因、浏览器历史来源、个人使用痕迹边界和使用边界证明；主题面谱覆盖宏观、策略、行业、基本面、港美股、风险、机会和自选提醒 | App 缓存、账号 API、订阅提醒、多浏览器历史和主题误判回测 |

## P2 采集器

| Collector | 职责 | 当前状态 | 下一步真实验证 |
| --- | --- | --- | --- |
| `hk-us-brokerage` | 富途、老虎、盈透资产、持仓、成交、委托、资金、分红、换汇 | `baseline+audit`；manifest 记录券商/交易表/字段覆盖、账户边界、币种市场、费用税费保证金、资产金额汇总、统一券商边界证明、逐输入解析结果、跳过文件/ZIP 成员原因和只读强交易边界 | 真实券商导出/只读屏幕、多币种、税费、保证金、完整账户边界证明 |
| `pro-terminal-usage` | Wind、Choice、iFinD、Bloomberg 工作流使用痕迹 | `baseline+audit`；manifest 记录终端/活动/字段覆盖、工作流主题面谱、工作流可用面、统一工作流边界证明、逐输入解析结果、跳过文件/ZIP 成员原因和许可边界 | 真实授权终端导出、许可安全评审、主题误判回测 |
| `social-activity` + `social-investment-influence` | 微博、B站、小红书影响源和弱证据 lens | `baseline+audit`；manifest 记录平台/动作/弱证据字段覆盖、社交影响主题、影响源可用面、社交活动边界证明、逐输入解析结果、跳过文件/ZIP 成员原因和 preview-only 边界；lens 汇总平台/动作/创作者/主题和社交影响边界证明但仍为弱证据 | 真实平台导出、创作者 allowlist、主题误判和弱证据回测 |

## 验收标准

每一波产品化必须留下：

1. 可运行 CLI。
2. 无私人数据的 fixture 测试。
3. `collectorx.event.v1` 输出。
4. `manifest.json` 中的覆盖率、来源审计、证据边界。
5. 采集包通过 `tools/validate_collector_package.py`。
6. 必要时输出 `finclaw.investor_wiki_evidence.v1.json`。
7. `docs/validations/*.md` 验证记录。
8. 绿色的 `PYTHON=.venv/bin/python bash test_collectors.sh`。
9. Git commit 和 push。

## 下一阶段

下一阶段不是再堆新采集器，而是按真实账号做 G3/G4：

- P0 先做微信、邮件、雪球、基金理财真实授权验证。
- P1 先做笔记、任务日历、会议协作的真实账号和多系统验证。
- P2 先找真实券商/专业终端/社交平台导出样本，验证字段覆盖和证据边界。

只有通过真实账号或真实设备验证，并且 Wiki 回测不过度推断，才能把对应采集器升为
`production-candidate`。
