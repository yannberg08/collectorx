---
name: pro-terminal-usage
description: 专业金融终端使用痕迹采集器。采集用户授权的 Wind、Choice、同花顺 iFinD、Bloomberg 等终端工作台、自选、搜索、下载、模型模板、因子关注等个人工作流元数据，支持授权 ZIP 包和终端/活动/工作区/项目/数据集/字段/关键词授权范围过滤，输出 CollectorX 事件、validator-safe filtered-all/no-input data-quality gap package、可用/工作流/gap 计数、业务湖/数据质量湖/Wiki readiness gates、终端/活动/字段覆盖、工作流主题面谱、工作流可用面、工作流强度与血缘摘要、统一工作流边界证明、来源审计、许可边界 manifest 和 FinClaw 投资分身证据包；不复制厂商数据库内容，不采凭据。
---

# Professional Terminal Usage Collector

## 采集边界

采集：

- 用户自己的工作区、看板、页面布局、常用入口。
- 自选列表、关注行业、关注因子、关注证券代码。
- 搜索记录、下载动作、模型模板、估值模型入口。
- 用户导出的本地配置、日志、快捷方式、HTML/CSV/JSON/Excel 工作流记录。
- 工作流元数据：函数/命令、菜单路径、项目/策略、数据集、字段、频率、日期区间、下载格式、文件名。
- 工作流强度和血缘：查询词、筛选参数、导出路径、导出行数、工作区 ID、模板 ID、证券/字段/数据集/因子数量、自选数量和 lineage ref。
- 授权 ZIP 包；保留 `archive.zip::member` 证据路径。
- `manifest.terminal_coverage`、`manifest.activity_coverage`、`manifest.workflow_field_coverage`：记录 Wind/Choice/iFinD/Bloomberg、六类活动和推荐工作流字段覆盖。
- `workflow_topics`、`primary_workflow_topic`、`workflow_topic_terms`：给每条工作流事件标记宏观、策略、行业、基本面、估值、信用固收、因子量化、组合监控、数据导出、港美股等研究主题。
- `manifest.workflow_surface_summary`：记录工作区、项目、模块、函数、菜单、搜索、证券、行业、地区、因子、数据集、字段、模板、下载格式、内容预览和研究主题可用面。
- `manifest.workflow_intensity_summary`：汇总查询词、参数键、导出路径、导出行数、工作区/模板 ID、函数代码、数据集、字段、因子、模板、工作区、下载格式和按活动聚合的数量强度。
- `manifest.workflow_boundary_proof`：把授权输入、终端覆盖、活动覆盖、字段覆盖、主题覆盖、工作流可用面、来源审计、许可边界、Wiki 流向和未完成声明合成一个 FinClaw 可判定的边界证明。
- `manifest.source_audit.pro_terminal_scope_policy`：记录终端、活动、工作区、项目、数据集、字段和关键词授权范围；若候选记录全部被策略排除，readiness 为 `scope_policy_filtered_all`，写入 1 条 profile gap 事件，不写入假工作流事件。
- `manifest.usable_event_count`、`manifest.workflow_event_count` 与 `manifest.gap_event_count`：区分真实专业终端工作流证据和采集缺口。
- `manifest.collection_readiness.can_enter_pro_terminal_usage_lake`、`can_enter_data_quality_lake` 与 `can_feed_investor_wiki_evidence`：让 FinClaw 明确判断业务湖、数据质量湖和 Wiki 证据是否可用；filtered-all/no-input data-quality gap package 的业务湖和 Wiki gate 为 false，数据质量湖 gate 为 true。
- `manifest.source_audit`：记录授权输入、缺失输入、逐文件解析结果、扩展名覆盖、跳过文件原因、ZIP 成员数量、跳过 ZIP 成员原因、文件/ZIP 成员来源、section/sheet 来源，并声明未采集危险路径成员。
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
  --out-dir /path/to/out \
  --allow-terminal wind \
  --allow-activity download \
  --allow-dataset FA \
  --allow-field Revenue
```

可选授权范围参数：

- `--allow-terminal` / `--deny-terminal`
- `--allow-activity` / `--deny-activity`
- `--allow-workspace` / `--deny-workspace`
- `--allow-project` / `--deny-project`
- `--allow-dataset` / `--deny-dataset`
- `--allow-field` / `--deny-field`
- `--allow-keyword` / `--deny-keyword`

输出：

- `lake/pro-terminal-usage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

当前支持 JSON/JSONL/NDJSON、CSV/TSV、XLSX/XLSM、HTML、Markdown/TXT、INI/CONF/LOG、ZIP。
JSON/ZIP 包会展开 workspaces、watchlists、searches、downloads、templates、models、
factors 等 section。manifest 会记录逐输入来源审计、跳过原因、ZIP 成员审计和路径安全
边界、统一工作流边界证明，并把用户工作流归类到研究主题面谱。采集器记录用户“怎么研究、关注什么、常用什么工具”，
不是公共金融数据采集器。
`workflow_intensity_summary` 用于让投资分身识别用户研究流程的“频度、深度、对象数量和导出规模”，但仍不代表完整终端历史或厂商数据库复制。
授权范围策略用于把用户明确授权外的工作流记录排除在 Lake 之前；filtered-all/no-input 包只记录 collection gap，路由到 `collectorx.data_quality.collection_gaps`，不会成为投资分身 Wiki 的工作流事实。它不会证明终端历史完整，也不会替代真实 Wind/Choice/iFinD/Bloomberg 导出验证或许可安全评审。
