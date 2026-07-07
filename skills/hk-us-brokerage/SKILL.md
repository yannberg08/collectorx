---
name: hk-us-brokerage
description: 港美股券商强交易采集器。采集用户授权的富途、老虎、盈透等券商只读导出中的资产、持仓、成交、委托、资金流水、分红、换汇，输出 CollectorX 事件和 FinClaw 投资分身证据包；不读取密码，不下单，不撤单。
version: 0.2.0
---

# HK/US Brokerage Collector

## 采集边界

采集：

- 资产快照：总资产、现金、购买力、币种。
- 持仓：证券代码、名称、市场、交易所、数量、成本、现价、市值、浮盈亏、收益率。
- 成交：买卖方向、成交数量、价格、金额、费用、订单号/成交号、交收日。
- 委托：方向、数量、价格、状态、订单类型、有效期。
- 资金流水：入金、出金、利息、费用、税费、净额。
- 分红和换汇：除息日、派息日、税前/税后金额、换出/换入币种、汇率。
- 多币种字段：本位币、现金、可用现金、已结算现金、保证金、维持保证金、净清算值。

不采集：

- 登录密码、交易密码、cookie、token。
- 下单、撤单、修改委托等交易动作。
- 富途/老虎社区讨论内容。

## CLI

```bash
python3 skills/hk-us-brokerage/scripts/hk_us_brokerage.py collect \
  --input /path/to/authorized/broker-export \
  --out-dir /path/to/out
```

输出：

- `lake/hk-us-brokerage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

当前支持 CSV/TSV/JSON/JSONL/NDJSON/XLSX/XLSM 本地授权导出；JSON 包会全量展开
assets、positions、executions、orders、cashflows、dividends、fx 等 section。真实富途、
老虎、盈透只读适配器需要按平台逐个验证。
