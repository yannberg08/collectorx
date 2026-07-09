---
name: email-collector
description: 采集邮箱邮件并输出CollectorX邮件事件。当用户说"查邮件"、"导出邮件"、"采集邮件"、"邮件备份"、"邮件投资讨论"时使用此skill。
---

# 邮箱采集器

支持IMAP协议的邮箱采集，包括Gmail、Outlook、QQ邮箱、163邮箱等。

邮箱采集器采集的是用户授权的邮件往来证据，用于关系、项目、信息源和投资协作画像。它不采集公共行情、公告、研报库这类外部市场数据。

邮箱采集必须先做“接入清单”前置工作：一个用户可能有 Gmail、Outlook、QQ 邮箱、163、企业邮箱等多个账户；每个账户的 IMAP host、授权方式、采集文件夹和默认时间窗口都可能不同。

## 快速开始

```bash
# 前置识别：判断邮箱服务商、IMAP host 和授权提示
python <SKILL_DIR>/scripts/email_api.py preflight --email user@gmail.com --email user@qq.com

# FinClaw 推荐：授权前诊断 IMAP/本机邮箱目录是否已具备真实采集条件
python <SKILL_DIR>/scripts/email_api.py preflight \
  --diagnose \
  --email user@gmail.com \
  --platform mac \
  --local-root ~/Library/Mail \
  --diagnose-out ~/Desktop/email-preflight.json

# 推荐：把一个邮箱加入采集清单，密码放在环境变量里，不写入状态文件
python <SKILL_DIR>/scripts/email_api.py register \
  --email user@gmail.com \
  --password-env COLLECTORX_GMAIL_PASSWORD \
  --folders INBOX,Sent \
  --days 30

# 如果只是先列入待接入清单，还没有授权码
python <SKILL_DIR>/scripts/email_api.py register \
  --email user@company.com \
  --provider custom \
  --host imap.company.com \
  --disabled

# 授权说明：Gmail/Outlook/QQ邮箱/163 等应用专用密码需要先在对应邮箱后台生成

# 查看当前接入清单
python <SKILL_DIR>/scripts/email_api.py status

# 采集全部已启用邮箱
python <SKILL_DIR>/scripts/email_api.py collect --account all --format json

# 采集并导出标准 CollectorX 包，推荐给 FinClaw 调用
python <SKILL_DIR>/scripts/email_api.py collect --account all \
  --out-dir ~/Desktop/email-package

# 可选：按用户授权范围收窄邮箱结果
python <SKILL_DIR>/scripts/email_api.py collect --account all \
  --out-dir ~/Desktop/email-package \
  --allow-folder INBOX \
  --allow-sender-domain broker.example \
  --allow-keyword 半导体

# 仅采集并导出 CollectorX Event JSONL
python <SKILL_DIR>/scripts/email_api.py collect --account all --format json \
  --event-export ~/Desktop/email-events.jsonl

# 不接 IMAP 时，也可以扫描用户授权的本机邮箱目录
python <SKILL_DIR>/scripts/email_api.py import \
  --local-scan \
  --container-root ~/Library/Mail \
  --out-dir ~/Desktop/email-package

# 或导入用户授权的本地邮件导出
python <SKILL_DIR>/scripts/email_api.py import \
  --input ~/Downloads/mail-export \
  --out-dir ~/Desktop/email-package
```

## 支持的邮箱

| 邮箱 | IMAP服务器 | 端口 |
|------|-----------|------|
| Gmail | imap.gmail.com | 993 |
| Outlook | outlook.office365.com | 993 |
| QQ邮箱 | imap.qq.com | 993 |
| 163邮箱 | imap.163.com | 993 |
| 126邮箱 | imap.126.com | 993 |

## 参数说明

| 参数 | 说明 |
|------|------|
| `--host` | IMAP服务器地址 |
| `--email` | 邮箱地址 |
| `--provider` | 邮箱服务商（gmail/outlook/qq/163/126/icloud/custom） |
| `--account-id` | 账户ID，默认由邮箱地址生成 |
| `--password` | 已禁用写入；保留参数只为提示迁移 |
| `--password-env` | 从环境变量读取密码 |
| `preflight --diagnose` | 输出 `collectorx.email_preflight.v1` 授权前诊断，不登录 IMAP、不读邮件 |
| `preflight --diagnose-out` | 保存同一份诊断 JSON，供 FinClaw 接入页或运行手册使用 |
| `preflight --platform` | 诊断本机邮箱目录的平台适配器：auto/mac/windows/linux/generic |
| `preflight --local-root` | 用户授权的本机邮箱根目录，可重复；诊断只统计候选文件，不读取内容 |
| `--folders` | 默认采集文件夹，逗号分隔 |
| `--days` | 采集最近N天的邮件 |
| `--account` | 采集哪个账户，默认 `all` |
| `--folder` | 覆盖采集文件夹 |
| `--format` | 输出格式（json/txt） |
| `--limit` | 限制邮件数量 |
| `--out-dir` | IMAP 或本地导入的标准采集包输出目录 |
| `--allow-mailbox/--deny-mailbox` | 邮箱账号授权范围过滤 |
| `--allow-folder/--deny-folder` | 邮箱文件夹授权范围过滤 |
| `--allow-sender/--deny-sender` | 发件人/发件地址授权范围过滤 |
| `--allow-sender-domain/--deny-sender-domain` | 发件域名授权范围过滤 |
| `--allow-recipient/--deny-recipient` | 收件人/抄送人授权范围过滤 |
| `--allow-subject/--deny-subject` | 主题授权范围过滤 |
| `--allow-attachment/--deny-attachment` | 附件名授权范围过滤 |
| `--allow-keyword/--deny-keyword` | 主题、正文预览、联系人、附件名关键词授权范围过滤 |

## 本地导入

`collect --out-dir` 和 `import --out-dir` 都输出标准采集包：

- `lake/email/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

`preflight --diagnose` 输出授权前诊断包 `collectorx.email_preflight.v1`，用于 FinClaw
判断用户是否已经具备 IMAP 采集或本机邮箱扫描条件。诊断只读取本地状态中的账户配置、
环境变量是否存在，以及用户授权邮箱根目录里的候选文件数量/格式；它不会登录 IMAP，
不会读取邮件头、正文、附件或本地邮件文件内容，也不会输出完整邮箱地址、密码、密码环境变量名或本地路径。
诊断包只表示“能否尝试采集”，不能进入 email Lake 或 `email-research` lens。

`collect` 通过已注册的 IMAP 邮箱读取邮件，并在 manifest 中记录账户/文件夹审计：
注册账户数、选中账户数、登录/搜索/抓取状态、匹配邮件数、抓取邮件数和失败原因。
如果没有注册邮箱、授权失败或时间窗口没有邮件，也会输出 validator-safe
`kind=profile` gap 事件和明确下一步；manifest 会把 `email_event_count` 与
`gap_event_count` 分开，并用 `can_enter_email_lake`、`can_enter_data_quality_lake`
和 `can_feed_email_research_lens` 区分真实邮件事实、数据质量缺口和下游
`email-research` lens 的可运行状态，避免把采集缺口当成真实邮件事实。

`import --local-scan` 可以扫描用户授权的本机邮箱目录，如 Apple Mail、Thunderbird、
Evolution/Maildir 根目录，并在 manifest/probe 中记录平台、授权根、候选邮件文件和本机扫描边界。
`import --input` 支持 EML、Apple Mail EMLX、Maildir、MBOX、Thunderbird 无后缀
mbox、JSON/JSONL/NDJSON、CSV/TSV、ZIP 邮件包。Maildir 只识别 `cur/` 和 `new/`
下具备 RFC822 邮件头的文件；Thunderbird 只把 `Mail/`、`ImapMail/` 或带 `.msf`
索引旁路证明的无后缀 mbox 当作邮件，`.msf` 索引文件只写入跳过原因，避免把普通无扩展文件误采。
默认只写入 `body_preview` 和 `attachment_refs`，附件只记录文件名、类型和大小，
不写入附件正文。ZIP 包会保留 `archive.zip::member` 来源并跳过路径穿越成员。
`manifest.collection_audit` 会记录请求输入、本机扫描平台/根目录/候选文件、缺失输入、
逐文件解析结果、跳过文件原因、Apple Mail EMLX 文件数、Maildir 文件数、Thunderbird
mbox 文件数、Thunderbird `.msf` 索引跳过数、ZIP 成员数量、ZIP 成员跳过原因和
`--limit` 截断状态。
`collect` 和 `import` 都支持邮箱授权范围策略：mailbox、folder、sender、
sender-domain、recipient、subject、attachment 和 keyword 的 allow/deny 规则。
`manifest.collection_audit.email_scope_policy` 会记录配置、候选邮件数、保留数、
过滤数、原因计数和 `filtered_all` 状态。若授权范围把所有候选邮件排除，采集器会输出
`email_scope_policy_filtered_all` profile gap，而不是误报为没有邮箱或没有导出文件。
gap 事件路由到 `collectorx.data_quality.collection_gaps`，并显式声明不代表邮件事实、
邮件研报事实、投资结论、完整邮箱历史、正文/附件正文采集或直接写入投资 Wiki。
`manifest.mailbox_boundary_proof` 会把本轮采集边界提升为稳定接口：IMAP 路径记录
账号/文件夹/天数窗口/匹配与抓取数量；本地导入路径记录授权输入、格式覆盖、ZIP 成员、
Apple Mail/Maildir/Thunderbird 计数、跳过原因、本机扫描根目录状态、邮箱授权范围、
正文策略和附件策略。它不会声明完整邮箱历史已采集，
投资 Wiki 仍必须先经过 `email-research` lens。
只有显式使用 `--event-include-body` 时才会把完整正文写入事件。

## 安全说明

- 推荐使用 `--password-env` 从环境变量读取密码，避免把应用专用密码写入本地状态文件
- 新注册不会把密码或应用专用密码写入 `~/.collectorx/email.json`
- 旧版状态文件如曾包含密码，可继续兼容读取；建议迁移到 `password_env`
- 建议使用应用专用密码（Gmail/Outlook需要）
- 不会修改或删除邮件，只读取
- `preflight --diagnose` 不登录邮箱、不读取邮件文件内容，输出中只保留邮箱域名和候选数量
- `--event-export` 默认只把正文预览写入事件，不把完整正文塞进事件；如确实需要可显式使用 `--event-include-body`
- `import` 默认只记录附件引用，不写入附件正文
- 附件引用和 `raw_ref` 会过滤 token、cookie、password、secret 等敏感键
- `import --local-scan` 的 probe、manifest 和 raw_ref 会掩码路径中的邮箱地址和长数字账号片段
- 支持多邮箱接入清单，状态文件结构为 `accounts[]`；旧版单邮箱 `account` 状态会被兼容读取
- `manifest.evidence_policy` 明确标记邮箱是通用证据源，进入投资 Wiki 前必须经过 `email-research` lens

## CollectorX事件输出

`--event-export` 会输出 `collectorx.event.v1` JSONL。每一行是一条 `email` 事件，包含：

- `collector`: `email`
- `owner_scope`: `personal`
- `kind`: `email`
- `data.mailbox/folder/from/to/cc/subject/body_preview/has_body`
- `data.attachment_refs/has_attachments/attachment_count`（如有附件）
- `raw_ref.imap_uid/message_id/folder`
- `privacy.local_only: true`

## 数据流向Wiki

邮件数据可流向以下Wiki维度：
- **外在/关系/联系人**：邮件往来对象
- **外在/履历/项目往来**：项目相关邮件
- **内在/知识体系/信息源**：订阅的邮件列表
- **投资/关系与协作网络**：投研、调研、项目和协作邮件

### 支持的应用
- **关系管理**：追踪邮件往来关系
- **项目跟踪**：追踪项目邮件
- **信息聚合**：聚合订阅信息
