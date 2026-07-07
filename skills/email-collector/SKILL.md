---
name: email-collector
description: 采集邮箱邮件。当用户说"查邮件"、"导出邮件"、"采集邮件"、"邮件备份"时使用此skill。
version: 0.1.0
---

# 邮箱采集器

支持IMAP协议的邮箱采集，包括Gmail、Outlook、QQ邮箱、163邮箱等。

## 快速开始

```bash
# 注册邮箱账户
python <SKILL_DIR>/scripts/email_api.py register --host imap.gmail.com --email user@gmail.com

# 授权（生成应用专用密码）
python <SKILL_DIR>/scripts/email_api.py authorize

# 采集邮件
python <SKILL_DIR>/scripts/email_api.py collect --days 30 --format json
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
| `--password` | 密码或应用专用密码 |
| `--days` | 采集最近N天的邮件 |
| `--folder` | 邮箱文件夹（INBOX/Sent/Drafts） |
| `--format` | 输出格式（json/txt） |
| `--limit` | 限制邮件数量 |

## 安全说明

- 密码存储在 `~/.collectorx/email.json`（chmod 600）
- 建议使用应用专用密码（Gmail/Outlook需要）
- 不会修改或删除邮件，只读取

## 数据流向Wiki

邮件数据可流向以下Wiki维度：
- **外在/关系/联系人**：邮件往来对象
- **外在/履历/项目往来**：项目相关邮件
- **内在/知识体系/信息源**：订阅的邮件列表

### 支持的应用
- **关系管理**：追踪邮件往来关系
- **项目跟踪**：追踪项目邮件
- **信息聚合**：聚合订阅信息
