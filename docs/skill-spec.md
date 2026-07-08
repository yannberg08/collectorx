# CollectorX 采集器架构规范

## 标准采集器结构

每个采集器必须包含以下文件：

```
skill-name/
├── SKILL.md              # 使用文档（给Agent看）
├── VERSION               # 版本号
├── .collectorx.json      # 元数据
├── scripts/
│   ├── xxx_query.py      # 主CLI入口
│   └── xxx/              # 核心库（多模块）
│       ├── __init__.py
│       ├── parser.py     # 数据解析
│       ├── stats.py      # 统计分析
│       └── ...
├── tests/                # 测试
│   └── test_xxx.py
└── references/           # 参考文档
    └── xxx-format.md
```

## 各文件说明

### SKILL.md
- 给Agent看的使用文档
- 包含：功能说明、使用方法、参数说明、限制

### VERSION
- 版本号（如 0.1.0）

### .collectorx.json
- 元数据（slug、version、description）

### scripts/xxx_query.py
- 主CLI入口
- 参数解析
- 调用核心库

### scripts/xxx/
- 核心库模块
- parser.py：数据解析
- stats.py：统计分析
- 其他辅助模块

### tests/
- 单元测试
- 测试解析、统计等功能

### references/
- 参考文档
- CSV格式说明
- API文档等

## 对比

| 采集器 | 文件数 | 状态 |
|--------|--------|------|
| wechat-export | 15+ | 迁移 skill，需确认上游许可与真实环境 |
| feishu | 8+ | 飞书 OAuth/API 工具 + 通用采集器 baseline；支持授权 JSON/CSV/HTML/Markdown/TXT/ZIP 本地导入、字段覆盖、飞书数据面、ZIP 跳过审计、逐文件解析 manifest 和凭证字段过滤，仍需真实飞书账号/API 验证 |
| ticktick-cli | 12+ | 滴答清单 API 工具 + SoulMirror YAML/AgentRunner 主采集路径；`collect_for_soulmirror.py` 输出任务快照数组，未授权以 `ticktick_auth_required` 失败，离线 JSON/ZIP 转换 helper 保留到 `exports/ticktick/events.jsonl`，仍需托管 OAuth Broker 和真实账号验证 |
| calendar-collector | 5+ | 通用日历采集器 baseline；支持授权 ICS/JSON/CSV/TSV/ZIP、平台覆盖、ZIP 跳过审计、逐文件解析 manifest，仍需真实 Apple/Google/Outlook/飞书/钉钉/企业微信日历验证 |
| meeting-artifacts | 7+ | 通用会议产物采集器 baseline；支持授权本地文件/平台导出/ZIP、平台覆盖、ZIP 跳过审计、逐文件解析 manifest 和凭证字段过滤；`meeting-minutes` lens 已汇总路演/调研/投委会/专家会/业绩会/风险/后续行动面谱，仍需真实飞书/钉钉/企业微信/腾讯会议账号验证 |
| collaboration-exports | 7+ | 钉钉/企业微信通用协作导出采集器 baseline；支持授权 JSON/CSV/HTML/文本/ZIP、消息/联系人/文件/会议指针、ZIP 跳过审计和逐文件解析 manifest，仍需真实账号/API 验证 |
| wechat-favorites | 8+ | 微信收藏/公众号文章动作通用采集器 baseline；支持授权文件/目录/ZIP、动作覆盖、逐输入来源审计、跳过原因和凭证字段过滤；`wechat-article-favorites` lens 已汇总文章面谱、动作和来源类型，仍需真实微信收藏/公众号阅读库验证 |
| doubao-chat-export | 19+ | 迁移 skill，需确认上游许可与真实环境 |
| filesystem-collector | 8+ | 本地文件元数据开源实现，对齐 SoulMirror driver=filesystem 边界；manifest 记录授权根、扩展覆盖、跳过原因和逐根目录结果，仍保持 metadata-only |
| ths-portfolio | 9 | 草稿实现，CSV parser 已有基础测试 |
| eastmoney-portfolio | 9+ | macOS 本机与授权完整交易事实本地 Lake Beta，强交易表需账户解锁真机验证 |
| xueqiu-watchlist | 9+ | 雪球关注池垂直采集器；授权导入、ZIP、来源审计、字段覆盖和 7/20 Wiki 证据包已测试，仍需真实账号/分页验证 |
| xueqiu-investor-activity | 8+ | 雪球个人活动垂直采集器；本地授权导出、浏览器网络 HAR、保存页、分页标记审计、字段覆盖和 SoulMirror 同步已测试，仍需真实账号样本与一键 adapter |
| china-wealth-assets | 8+ | 中国基金理财资产垂直采集器；本地授权导入、浏览器网络 HAR、ZIP、来源审计、平台/字段/账户/资产面/币种覆盖和金额汇总已测试，仍需真实账号边界证明 |
| financial-news-usage | 8+ | 财经资讯使用痕迹垂直采集器 baseline；支持授权文件/目录/ZIP/浏览器历史副本、平台/动作/主题覆盖、逐输入来源审计、跳过原因和凭证字段过滤，仍需真实财联社/华尔街见闻/格隆汇账号验证 |
| hk-us-brokerage | 8+ | 港美股券商强交易垂直采集器 baseline；支持授权 CSV/JSON/Excel/ZIP、券商/交易表/字段覆盖、账户边界、币种市场、费用税费保证金、逐输入来源审计、跳过原因和凭证字段过滤，仍需真实富途/老虎/盈透账号验证 |
| pro-terminal-usage | 8+ | 专业终端使用痕迹垂直采集器 baseline；支持授权 CSV/JSON/Excel/HTML/TXT/LOG/ZIP、终端/活动/字段覆盖、工作流主题面谱、逐输入来源审计、跳过原因和凭证/许可字段过滤，仍需真实 Wind/Choice/iFinD/Bloomberg 账号验证 |
| social-activity | 8+ | 社交平台用户活动通用采集器 baseline；支持授权 JSON/CSV/Excel/HTML/TXT/ZIP、弱证据策略、平台/动作/字段覆盖、社交影响主题、逐输入来源审计、跳过原因、ZIP 成员审计和凭证字段过滤，仍需真实微博/B站/小红书账号验证 |
| email-collector | 8+ | 多邮箱前置识别、IMAP 标准包、本地邮件导入、Apple Mail EMLX、Maildir、账户/文件夹审计、逐输入导入审计、跳过文件/ZIP 成员原因和字段覆盖已补齐，仍需真实邮箱验证与安全评审 |
| qq-export | 9+ | 已发现真实 macOS QQ NT 联系人/群/消息库；支持 key 诊断、clean库准备、解密后联系人/群/消息读取；当前机器受 LLDB 权限限制 |
| notes-collector | 8+ | 笔记通用采集器 baseline；支持 Obsidian/Notion、有道/印象/Markdown/HTML/JSON/ENEX/ZIP 授权导入、平台覆盖、逐输入来源审计、跳过原因和内容策略 manifest，仍需真实 Notion/有道/印象账号验证 |
| investor-source-collectors | 8+ | 投资分身分类、路由和 lens 证据包工具；research-documents 已补逐输入审计、显式内容抽取和 `--include-image-ocr` 本地截图 OCR 审计，investment-notes 与 task-calendar-investor 已补投资面谱，不替代通用/垂直源采集器 |

## 输出契约

采集器不直接写 Wiki。所有采集器必须先输出 `collectorx.event.v1`，再由 lake 和 distill app 处理。

必读文件：

- `docs/event-contract.md`
- `schemas/collectorx-event.schema.json`
- `examples/events/*.json`

最小规则：

1. `id` 必须稳定，不能每次采集随机生成。
2. `owner_scope` 默认是 `personal`，公共市场数据不要混入用户个人证据。
3. `privacy.local_only` 默认是 `true`。
4. `raw_ref` 保存原始证据指针，避免下游 prompt 无限制暴露原文。
5. `wiki_targets` 只是路由建议，不能替代 distill app 的判断。

## 验收标准

一个采集器达到可进入 FinClaw/SoulMirror 闭环前，至少要通过：

1. CLI `--help` 可执行。
2. Python 语法编译通过。
3. 有不会泄露隐私的 fixture。
4. 能输出 `collectorx.event.v1`。
5. 文档说明授权方式、平台状态、限制和错误降级。
6. 明确映射到通用 Wiki 或垂直 Wiki 的哪些维度。
7. 标准输出目录必须通过
   `python3 tools/validate_collector_package.py <out-dir> --collector <collector-id>`。
8. 若输出 `investor_wiki_evidence.v1.json`，必须通过
   `python3 tools/validate_investor_wiki_evidence.py <path>`；严格模式要求
   `external.investor / 7 dimensions / 20 subdimensions`、证据强度、缺口和
   “采集器不直接写 Wiki”的策略元数据齐全。
