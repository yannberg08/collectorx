---
name: email-collector
description: 采集邮箱邮件并输出CollectorX邮件事件。当用户说"查邮件"、"导出邮件"、"采集邮件"、"邮件备份"、"邮件投资讨论"时使用此skill。
version: 0.4.1
---

# 邮箱采集器

支持IMAP协议的邮箱采集，包括Gmail、Outlook、QQ邮箱、163邮箱等。

邮箱采集器采集的是用户授权的邮件往来证据，用于关系、项目、信息源和投资协作画像。它不采集公共行情、公告、研报库这类外部市场数据。

邮箱采集必须先做“接入清单”前置工作：一个用户可能有 Gmail、Outlook、QQ 邮箱、163、企业邮箱等多个账户；每个账户的 IMAP host、授权方式、采集文件夹和默认时间窗口都可能不同。

## 快速开始

```bash
# 前置识别：判断邮箱服务商、IMAP host 和授权提示
python <SKILL_DIR>/scripts/email_api.py preflight --email user@gmail.com --email user@qq.com

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

# 采集并导出 CollectorX Event JSONL
python <SKILL_DIR>/scripts/email_api.py collect --account all --format json \
  --event-export ~/Desktop/email-events.jsonl

# 不接 IMAP 时，也可以导入用户授权的本地邮件导出
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
| `--folders` | 默认采集文件夹，逗号分隔 |
| `--days` | 采集最近N天的邮件 |
| `--account` | 采集哪个账户，默认 `all` |
| `--folder` | 覆盖采集文件夹 |
| `--format` | 输出格式（json/txt） |
| `--limit` | 限制邮件数量 |

## 本地导入

`import` 命令支持 EML、MBOX、JSON/JSONL/NDJSON、CSV/TSV、ZIP 邮件包。它输出标准采集包：

- `lake/email/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

默认只写入 `body_preview` 和 `attachment_refs`，附件只记录文件名、类型和大小，
不写入附件正文。ZIP 包会保留 `archive.zip::member` 来源并跳过路径穿越成员。
只有显式使用 `--event-include-body` 时才会把完整正文写入事件。

## 安全说明

- 推荐使用 `--password-env` 从环境变量读取密码，避免把应用专用密码写入本地状态文件
- 新注册不会把密码或应用专用密码写入 `~/.collectorx/email.json`
- 旧版状态文件如曾包含密码，可继续兼容读取；建议迁移到 `password_env`
- 建议使用应用专用密码（Gmail/Outlook需要）
- 不会修改或删除邮件，只读取
- `--event-export` 默认只把正文预览写入事件，不把完整正文塞进事件；如确实需要可显式使用 `--event-include-body`
- `import` 默认只记录附件引用，不写入附件正文
- 附件引用和 `raw_ref` 会过滤 token、cookie、password、secret 等敏感键
- 支持多邮箱接入清单，状态文件结构为 `accounts[]`；旧版单邮箱 `account` 状态会被兼容读取

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
