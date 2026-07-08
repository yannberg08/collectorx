---
name: notes-collector
description: 采集笔记应用数据。当用户说"导出笔记"、"采集笔记"、"笔记备份"时使用此skill。
---

# 笔记采集器

支持多种笔记应用的数据采集：
- Notion（通过API）
- Obsidian（本地 Markdown / Canvas 文件）
- 有道云笔记（授权导出导入）
- 印象笔记 / Evernote（ENEX 授权导入）
- Notion/有道/印象等 ZIP 授权导出包

## 快速开始

```bash
# 采集Notion笔记。推荐把 token 放在环境变量里，不写进命令历史。
python <SKILL_DIR>/scripts/notes_api.py notion --token-env NOTION_TOKEN --export ~/Desktop/notion.json

# 采集Obsidian笔记
python <SKILL_DIR>/scripts/notes_api.py obsidian --vault ~/Documents/MyVault --export ~/Desktop/obsidian.json

# 推荐给 CollectorX/FinClaw：同时输出标准事件包
python <SKILL_DIR>/scripts/notes_api.py obsidian \
  --vault ~/Documents/MyVault \
  --export ~/Desktop/obsidian.json \
  --out-dir ~/Desktop/notes-collect

# 导入有道云/印象笔记/Notion/Markdown/HTML/JSON/CSV/TSV/ZIP 授权导出
python <SKILL_DIR>/scripts/notes_api.py import \
  --input ~/Downloads/notes-export \
  --source-app auto \
  --export ~/Desktop/notes.json \
  --out-dir ~/Desktop/notes-collect
```

## 支持的笔记应用

| 应用 | 认证方式 | 数据格式 |
|------|----------|----------|
| Notion | API Token / 授权导出 | JSON/Markdown/CSV/TSV |
| Obsidian | 本地文件 | Markdown / Canvas |
| 有道云笔记 | 授权导出 | JSON/HTML/TXT |
| 印象笔记 / Evernote | 授权导出 | ENEX |
| ZIP 授权导出包 | 本地文件 | Notion/有道/印象/Markdown/CSV/TSV 等导出包 |

## 参数说明

| 参数 | 说明 |
|------|------|
| `--token-env` | 保存 Notion API Token 的环境变量名，推荐 |
| `--token` | API访问令牌；兼容保留，不推荐写进命令历史 |
| `--vault` | Obsidian vault目录 |
| `--input` | 授权导出文件、目录或 ZIP |
| `--source-app` | 导出来源，支持 `auto/notion/obsidian/youdao/evernote/markdown/notes-export` |
| `--export` | 导出文件路径 |
| `--limit` | 限制笔记数量 |
| `--event-export` | 导出 `collectorx.event.v1` JSONL |
| `--out-dir` | 导出完整采集包：`lake/notes/events.jsonl`、`manifest.json`、`SUMMARY.md` |
| `--include-content` | 在事件中包含完整正文；默认只写正文预览 |

## CollectorX 事件边界

`notes-collector` 是 generic collector：它采集用户授权笔记事实，不直接判断哪些是投资笔记，也不直接写投资 Wiki。

默认事件只包含 `content_preview`、`content_length` 和 `content_digest`，不包含完整正文；如用户明确授权，可加 `--include-content`。投资分身应把 `lake/notes/events.jsonl` 交给 `investment-notes` lens，由 lens 负责筛选复盘、规则库、估值假设和交易 checklist。

CSV/TSV 表格会按行转成 note，适配 Notion database、规则库、复盘表和研究清单导出；
标题列优先识别 `title/name/标题/名称`，正文列优先识别 `content/text/正文/内容/备注/notes`，
其他非元数据列会拼入正文预览，避免表格字段丢失。

Obsidian `.canvas` 会按画布转成一条 generic note，保留文字节点、链接文件、
URL、节点数和边数。Canvas 仍然只是笔记事实，不直接声明投资结论。

ZIP 导入会保留 `source_archive` 和 `archive_member`，并跳过绝对路径、`..`
路径穿越和 Windows 盘符路径成员。采集器只记录用户授权导出内的来源引用，不采
Notion token、服务端 cookie 或账号密码。

`manifest.json` 会写入 `platform_coverage`，列出 P1 笔记通道预期平台
`obsidian/notion/youdao/evernote`、本次实际观察到的平台、缺失平台、各
平台事件数，以及 `real_account_validation` 状态。FinClaw 应用它判断这次
采集是否只是局部导入，还是已经覆盖用户授权的主要笔记平台。

`manifest.field_coverage` 会报告标题、路径/URL、正文预览、正文长度、标签、
更新时间等推荐字段覆盖情况；`source_audit` 报告授权输入、逐文件解析结果、
扩展名覆盖、CSV/TSV 表格文件数、表格行数、Canvas 文件数、Canvas note 数、跳过文件原因、ZIP 成员数量、跳过 ZIP 成员原因、来源引用和路径
安全边界；`content_policy` 明确本次是预览模式还是全文授权模式。`evidence_policy`
固定声明：generic notes 不能直接写投资 Wiki，也不能直接声称“投资笔记已识别”。

## 数据流向Wiki

笔记数据可流向以下Wiki维度：
- **内在/知识体系/笔记**：个人笔记
- **内在/知识体系/学习记录**：学习笔记
- **外在/履历/项目文档**：项目笔记

### 支持的应用
- **知识管理**：整理个人知识
- **学习追踪**：追踪学习进度
- **项目文档**：管理项目笔记
