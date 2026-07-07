---
name: notes-collector
description: 采集笔记应用数据。当用户说"导出笔记"、"采集笔记"、"笔记备份"时使用此skill。
version: 0.1.0
---

# 笔记采集器

支持多种笔记应用的数据采集：
- Notion（通过API）
- Obsidian（本地文件）
- 有道云笔记（通过API）
- 印象笔记（通过API）

## 快速开始

```bash
# 采集Notion笔记
python <SKILL_DIR>/scripts/notes_api.py notion --token <token> --export ~/Desktop/notion.json

# 采集Obsidian笔记
python <SKILL_DIR>/scripts/notes_api.py obsidian --vault ~/Documents/MyVault --export ~/Desktop/obsidian.json

# 采集有道云笔记
python <SKILL_DIR>/scripts/notes_api.py youdao --token <token> --export ~/Desktop/youdao.json
```

## 支持的笔记应用

| 应用 | 认证方式 | 数据格式 |
|------|----------|----------|
| Notion | API Token | JSON |
| Obsidian | 本地文件 | Markdown |
| 有道云笔记 | OAuth | JSON |
| 印象笔记 | OAuth | ENEX |

## 参数说明

| 参数 | 说明 |
|------|------|
| `--token` | API访问令牌 |
| `--vault` | Obsidian vault目录 |
| `--export` | 导出文件路径 |
| `--format` | 输出格式（json/markdown） |
| `--limit` | 限制笔记数量 |

## 数据流向Wiki

笔记数据可流向以下Wiki维度：
- **内在/知识体系/笔记**：个人笔记
- **内在/知识体系/学习记录**：学习笔记
- **外在/履历/项目文档**：项目笔记

### 支持的应用
- **知识管理**：整理个人知识
- **学习追踪**：追踪学习进度
- **项目文档**：管理项目笔记
