---
name: filesystem-collector
description: 本地文件通用采集器，复刻 SoulMirror 已验证的 filesystem driver 边界：只扫描用户授权目录中的人类文档元数据，输出路径、大小、mtime、扩展名等 CollectorX file 事件，不读取正文。用于本地文件、研报、PDF、Excel、Word、Markdown、幻灯片等文件证据进入 lake，投资分身再通过 research-documents lens 筛选投研文件。
---

# 本地文件采集器

本技能是 CollectorX 的开源本地文件采集器。行为对齐 SoulMirror `driver=filesystem`：扫描本地“有内容的人类文档”，只采元数据，不读正文。

## 采什么

- 文件路径、文件名、扩展名、大小、mtime。
- 文档类、表格类、幻灯类、笔记类文件。
- 默认目录：`~/Documents`、`~/Desktop`、`~/Downloads`，macOS 追加 iCloud Drive，Windows 追加 OneDrive。

## 不采什么

- 不读取正文。
- 不扫描全盘。
- 不进入 `node_modules`、`.git`、`build`、`dist`、缓存和虚拟环境。
- 不采超过大小上限的文件。

## 使用

```bash
python <SKILL_DIR>/scripts/filesystem_query.py collect \
  --root ~/Documents \
  --out-dir ~/Desktop/filesystem-collect

python <SKILL_DIR>/scripts/filesystem_query.py collect \
  --root ~/Documents/research \
  --event-export ~/Desktop/filesystem-events.jsonl
```

输出：

```text
<out-dir>/
├── lake/filesystem/events.jsonl
├── manifest.json
└── SUMMARY.md
```

`manifest.json` 会记录 `platform_default_root_plan`，用于说明 macOS、Windows、
Linux 默认候选根目录的代码级路径计划。无论哪个平台，默认边界仍是：
metadata-only、用户授权根目录、正文不读取。

`manifest.source_audit` 会记录授权根目录是否存在、扫描文件数、产出事件数、
跳过文件/目录数、扩展名覆盖、跳过原因、大小上限、忽略目录和逐根目录结果。
这让 FinClaw 能判断本次本地文件采集是否只是“没有文件”，还是因为目录缺失、
扩展名不支持、文件过大、隐藏文件或缓存目录被跳过。

投资分身不直接消费全量本地文件；`research-documents` lens 从 `filesystem` lake 中筛选研报、财报、公告批注、估值表等投研文件。
