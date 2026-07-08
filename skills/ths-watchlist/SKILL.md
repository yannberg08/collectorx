---
name: ths-watchlist
description: 同花顺自选股垂直采集器。采集用户授权本机目录或授权导出的同花顺自选股列表，输出 watchlist 事件；自选只代表关注池，不能单独证明持仓或交易意图；无输入或授权范围过滤为空时输出可验证 gap package。
version: 0.1.4
---

# Tonghuashun Watchlist Collector

## 采集边界

采集：

- 用户授权本机同花顺目录中可识别的自选股文件。
- 同花顺自选股导出中的证券代码、证券名称、市场、分组、行业、标签、备注、添加时间。
- CSV/TSV、JSON/JSONL/NDJSON、XLSX/XLSM、HTML、Markdown、TXT、ZIP 中的授权自选列表。
- manifest 中的本机扫描审计、逐输入审计、ZIP 成员 provenance、字段覆盖、ths_watchlist_boundary_proof。
- symbol、market、group、industry、tag、keyword、source、source_platform 的 allow/deny 授权范围过滤。
- 无授权输入、无可用记录、或 filtered-all 场景下的 profile gap 事件，带非空时间、候选/过滤计数和交易事实边界。
- 简单文本中的 A 股代码列表。

不采集：

- 登录密码、交易密码、cookie、token、session。
- 真实持仓、成交、委托、资金流水；这些由 `ths-portfolio` 采集。
- 把自选股直接当成持仓或交易建议。

## CLI

```bash
python3 skills/ths-watchlist/scripts/ths_watchlist.py collect \
  --local-scan \
  --container-root /path/to/authorized/tonghuashun-root \
  --out-dir /path/to/out
```

也可以导入用户已经导出的自选文件：

```bash
python3 skills/ths-watchlist/scripts/ths_watchlist.py collect \
  --input /path/to/authorized/ths-watchlist-export \
  --out-dir /path/to/out
```

输出：

- `lake/ths-watchlist/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

自选股是 attention-universe 证据，应与交易、持仓、笔记、研报和复盘交叉验证。
`ths_watchlist_boundary_proof` 会明确它不是强交易、持仓、委托或资金流水来源。
`manifest.collection_audit.ths_watchlist_scope_policy` 会记录授权范围配置、
候选事件数、保留数、过滤数、原因计数和 filtered-all 状态；
`manifest.ths_watchlist_boundary_proof.authorization_scope_boundary` 给 FinClaw
检查本次同花顺自选股采集是否只保留了用户授权范围内的关注池证据。
如果没有授权输入，或用户授权范围过滤后没有保留任何记录，采集器会输出
validator-safe profile gap event，并设置 `manifest.gap_event_count=1`、
`manifest.watchlist_event_count=0` 和 `collection_readiness.can_enter_finclaw=false`。
