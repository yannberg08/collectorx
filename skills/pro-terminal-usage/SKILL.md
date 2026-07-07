---
name: pro-terminal-usage
description: 专业金融终端使用痕迹采集器。采集用户授权的 Wind、Choice、同花顺 iFinD、Bloomberg 等终端工作台、自选、搜索、下载、模型模板、因子关注等个人工作流元数据，支持授权 ZIP 包，输出 CollectorX 事件、终端/活动/字段覆盖、工作流可用面、来源审计、许可边界 manifest 和 FinClaw 投资分身证据包；不复制厂商数据库内容，不采凭据。
---

# Professional Terminal Usage Collector

## 采集边界

采集：

- 用户自己的工作区、看板、页面布局、常用入口。
- 自选列表、关注行业、关注因子、关注证券代码。
- 搜索记录、下载动作、模型模板、估值模型入口。
- 用户导出的本地配置、日志、快捷方式、HTML/CSV/JSON/Excel 工作流记录。
- 工作流元数据：函数/命令、菜单路径、项目/策略、数据集、字段、频率、日期区间、下载格式、文件名。
- 授权 ZIP 包；保留 `archive.zip::member` 证据路径。
- `manifest.terminal_coverage`、`manifest.activity_coverage`、`manifest.workflow_field_coverage`：记录 Wind/Choice/iFinD/Bloomberg、六类活动和推荐工作流字段覆盖。
- `manifest.workflow_surface_summary`：记录工作区、项目、模块、函数、菜单、搜索、证券、行业、地区、因子、数据集、字段、模板、下载格式和内容预览可用面。
- `manifest.source_audit`：记录文件/ZIP 成员来源、section/sheet 来源，并声明未采集危险路径成员。
- `manifest.license_policy` 与 `manifest.evidence_policy`：声明只采工作流元数据，不镜像厂商数据库，不镜像授权内容全文。

不采集：

- Wind/Choice/iFinD/Bloomberg 的公共行情、研报、公告、数据库全文。
- 违反许可的批量数据镜像。
- cookie、token、密码、授权头。
- 下单/撤单行为。

## CLI

```bash
python3 skills/pro-terminal-usage/scripts/pro_terminal_usage.py collect \
  --input /path/to/authorized/terminal-workflow-export-or-zip \
  --out-dir /path/to/out
```

输出：

- `lake/pro-terminal-usage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

当前支持 JSON/JSONL/NDJSON、CSV/TSV、XLSX/XLSM、HTML、Markdown/TXT、INI/CONF/LOG、ZIP。
JSON/ZIP 包会展开 workspaces、watchlists、searches、downloads、templates、models、
factors 等 section。采集器记录用户“怎么研究、关注什么、常用什么工具”，不是公共金融
数据采集器。
