---
name: ths-watchlist
description: 同花顺自选股垂直采集器。采集用户授权本机目录或授权导出的同花顺自选股列表，输出 watchlist 事件；自选只代表关注池，不能单独证明持仓或交易意图。
version: 0.1.2
---

# Tonghuashun Watchlist Collector

## 采集边界

采集：

- 用户授权本机同花顺目录中可识别的自选股文件。
- 同花顺自选股导出中的证券代码、证券名称、市场、分组、行业、标签、备注、添加时间。
- CSV/TSV、JSON/JSONL/NDJSON、XLSX/XLSM、HTML、Markdown、TXT、ZIP 中的授权自选列表。
- manifest 中的本机扫描审计、逐输入审计、ZIP 成员 provenance、字段覆盖、ths_watchlist_boundary_proof。
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
