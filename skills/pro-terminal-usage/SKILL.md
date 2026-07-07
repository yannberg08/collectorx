---
name: pro-terminal-usage
description: 专业金融终端使用痕迹采集器。采集用户授权的 Wind、Choice、同花顺 iFinD、Bloomberg 等终端工作台、自选、搜索、下载、模型模板、因子关注等个人工作流元数据，输出 CollectorX 事件和 FinClaw 投资分身证据包；不复制厂商数据库内容，不采凭据。
---

# Professional Terminal Usage Collector

## 采集边界

采集：

- 用户自己的工作区、看板、页面布局、常用入口。
- 自选列表、关注行业、关注因子、关注证券代码。
- 搜索记录、下载动作、模型模板、估值模型入口。
- 用户导出的本地配置、日志、快捷方式、HTML/CSV/JSON 工作流记录。

不采集：

- Wind/Choice/iFinD/Bloomberg 的公共行情、研报、公告、数据库全文。
- 违反许可的批量数据镜像。
- cookie、token、密码、授权头。
- 下单/撤单行为。

## CLI

```bash
python3 skills/pro-terminal-usage/scripts/pro_terminal_usage.py collect \
  --input /path/to/authorized/terminal-workflow-export \
  --out-dir /path/to/out
```

输出：

- `lake/pro-terminal-usage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

该采集器记录用户“怎么研究、关注什么、常用什么工具”，不是公共金融数据采集器。
