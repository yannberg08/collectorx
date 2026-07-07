---
name: notes-collector
description: 采集笔记应用数据。当用户说"导出笔记"、"采集笔记"、"笔记备份"时使用此skill。
version: 0.2.0
---

# 笔记采集器

支持多种笔记应用的数据采集：
- Notion（通过API）
- Obsidian（本地文件）
- 有道云笔记（授权导出导入）
- 印象笔记 / Evernote（ENEX 授权导入）

## 快速开始

```bash
# 采集Notion笔记
python <SKILL_DIR>/scripts/notes_api.py notion --token <token> --export ~/Desktop/notion.json

# 采集Obsidian笔记
python <SKILL_DIR>/scripts/notes_api.py obsidian --vault ~/Documents/MyVault --export ~/Desktop/obsidian.json

# 推荐给 CollectorX/FinClaw：同时输出标准事件包
python <SKILL_DIR>/scripts/notes_api.py obsidian \
  --vault ~/Documents/MyVault \
  --export ~/Desktop/obsidian.json \
  --out-dir ~/Desktop/notes-collect

# 导入有道云/印象笔记/Markdown/HTML/JSON 授权导出
python <SKILL_DIR>/scripts/notes_api.py import \
  --input ~/Downloads/notes-export \
  --source-app auto \
  --export ~/Desktop/notes.json \
  --out-dir ~/Desktop/notes-collect
```

## 支持的笔记应用

| 应用 | 认证方式 | 数据格式 |
|------|----------|----------|
| Notion | API Token | JSON |
| Obsidian | 本地文件 | Markdown |
| 有道云笔记 | 授权导出 | JSON/HTML/TXT |
| 印象笔记 / Evernote | 授权导出 | ENEX |

## 参数说明

| 参数 | 说明 |
|------|------|
| `--token` | API访问令牌 |
| `--vault` | Obsidian vault目录 |
| `--input` | 授权导出文件或目录 |
| `--source-app` | 导出来源，支持 `auto/notion/obsidian/youdao/evernote/markdown/notes-export` |
| `--export` | 导出文件路径 |
| `--format` | 输出格式（json/markdown） |
| `--limit` | 限制笔记数量 |
| `--event-export` | 导出 `collectorx.event.v1` JSONL |
| `--out-dir` | 导出完整采集包：`lake/notes/events.jsonl`、`manifest.json`、`SUMMARY.md` |
| `--include-content` | 在事件中包含完整正文；默认只写正文预览 |

## CollectorX 事件边界

`notes-collector` 是 generic collector：它采集用户授权笔记事实，不直接判断哪些是投资笔记，也不直接写投资 Wiki。

默认事件只包含 `content_preview`，不包含完整正文；如用户明确授权，可加 `--include-content`。投资分身应把 `lake/notes/events.jsonl` 交给 `investment-notes` lens，由 lens 负责筛选复盘、规则库、估值假设和交易 checklist。

## 数据流向Wiki

笔记数据可流向以下Wiki维度：
- **内在/知识体系/笔记**：个人笔记
- **内在/知识体系/学习记录**：学习笔记
- **外在/履历/项目文档**：项目笔记

### 支持的应用
- **知识管理**：整理个人知识
- **学习追踪**：追踪学习进度
- **项目文档**：管理项目笔记
