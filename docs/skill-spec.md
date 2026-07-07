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
| feishu | 5+ | 迁移 skill，需确认上游许可与真实环境 |
| ticktick-cli | 12+ | 滴答清单 API 工具 + CollectorX 任务事件转换 baseline；支持授权 JSON/ZIP、平台覆盖 manifest 和凭证字段过滤，仍需真实 OAuth 账号验证 |
| calendar-collector | 5+ | 通用日历采集器 baseline；支持授权 ICS/JSON/CSV/TSV/ZIP、平台覆盖 manifest，仍需真实 Apple/Google/Outlook/飞书/钉钉/企业微信日历验证 |
| meeting-artifacts | 7+ | 通用会议产物采集器 baseline；支持授权本地文件/平台导出/ZIP、平台覆盖 manifest 和凭证字段过滤，仍需真实飞书/钉钉/企业微信/腾讯会议账号验证 |
| wechat-favorites | 7+ | 微信收藏/公众号文章动作通用采集器 baseline；支持授权文件/目录/ZIP、动作覆盖 manifest 和凭证字段过滤，仍需真实微信收藏/公众号阅读库验证 |
| doubao-chat-export | 19+ | 迁移 skill，需确认上游许可与真实环境 |
| filesystem-collector | 7+ | 本地文件元数据开源实现，对齐 SoulMirror driver=filesystem 边界 |
| ths-portfolio | 9 | 草稿实现，CSV parser 已有基础测试 |
| eastmoney-portfolio | 9+ | macOS 本机与授权完整交易事实本地 Lake Beta，强交易表需账户解锁真机验证 |
| xueqiu-watchlist | 9 | 草稿实现，CSV parser 已有基础测试 |
| xueqiu-investor-activity | 7+ | 雪球个人活动垂直采集器，本地授权导出 baseline 已测试 |
| china-wealth-assets | 7+ | 中国基金理财资产垂直采集器，本地授权导出 baseline 已测试 |
| financial-news-usage | 7+ | 财经资讯使用痕迹垂直采集器 baseline；支持授权文件/目录/ZIP/浏览器历史副本、平台/动作覆盖 manifest 和凭证字段过滤，仍需真实财联社/华尔街见闻/格隆汇账号验证 |
| email-collector | 8+ | 已有多邮箱前置识别与邮件事件输出基线，需真实邮箱验证与安全评审 |
| qq-export | 9+ | 已发现真实 macOS QQ NT 联系人/群/消息库；支持 key 诊断、clean库准备、解密后联系人/群/消息读取；当前机器受 LLDB 权限限制 |
| notes-collector | 6+ | 笔记通用采集器 baseline；支持 Obsidian/Notion、有道/印象/Markdown/HTML/JSON/ENEX/ZIP 授权导入和平台覆盖 manifest，仍需真实 Notion/有道/印象账号验证 |
| investor-source-collectors | 7+ | 投资分身分类、路由和 lens 证据包工具，不替代通用/垂直源采集器 |

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
