---
name: xueqiu-watchlist
description: 雪球关注/自选列表垂直采集器。采集用户授权导出的雪球关注池，输出 watchlist 事件；关注池不能单独证明持仓、交易或完整投资意图。
---

# Xueqiu Watchlist Collector

## 采集边界

采集：

- 雪球关注/自选列表中的股票代码、名称、市场、分组、行业、标签、备注、关注时间。
- CSV/TSV、JSON/JSONL/NDJSON、XLSX/XLSM、HTML、Markdown、TXT、ZIP 中的授权关注列表。
- 简单文本中的 A 股、港股雪球代码。

不采集：

- 登录密码、cookie、token、session。
- 发帖、评论、收藏、组合调仓等更宽的雪球活动；这些由 `xueqiu-investor-activity` 采集。
- 真实持仓、成交、委托、资金流水；这些必须来自券商或交易接口。
- 把关注列表直接当成持仓或交易建议。

## CLI

标准 CollectorX 事件包：

```bash
python3 skills/xueqiu-watchlist/scripts/xueqiu_query.py collect \
  --input /path/to/authorized/xueqiu-watchlist-export \
  --out-dir /path/to/out

# 可选：按用户授权范围收窄关注池
python3 skills/xueqiu-watchlist/scripts/xueqiu_query.py collect \
  --input /path/to/authorized/xueqiu-watchlist-export \
  --out-dir /path/to/out \
  --allow-market SH \
  --allow-group 核心观察 \
  --deny-keyword 私人
```

输出：

- `lake/xueqiu-watchlist/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

保留旧入口：

```bash
python3 skills/xueqiu-watchlist/scripts/xueqiu_query.py \
  --file /path/to/authorized/xueqiu-watchlist.csv \
  --export /path/to/watchlist.json \
  --list
```

## Wiki 边界

关注列表是 attention-universe 证据，流向 `investor.opportunity_watchlist.watchlist`
和 `investor.capability_circle.attention_universe`。FinClaw 应与雪球活动、
券商交易、笔记、研报和复盘交叉验证。

ZIP 包会保留 `archive.zip::member` 来源并跳过路径穿越成员。manifest 会明确
标注 `xueqiu_watchlist_is_strong_trade_source: false`，并记录输入文件数、
扩展名覆盖、ZIP 成员/跳过成员、解析记录数、过滤记录数和字段覆盖。
`collect` 支持 symbol、market、group、industry、tag、keyword 的 allow/deny
授权范围过滤。`manifest.collection_audit.xueqiu_watchlist_scope_policy` 会记录配置、
候选事件数、保留数、过滤数、原因计数和 filtered-all 状态；
`manifest.xueqiu_watchlist_boundary_proof.authorization_scope_boundary` 给 FinClaw
检查本轮关注池授权边界。该策略只限定用户授权范围，不判断投资相关性。
