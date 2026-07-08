---
name: hk-us-brokerage
description: 港美股券商强交易采集器。采集用户授权的富途、老虎、盈透等券商只读导出/ZIP 包中的资产、持仓、成交、委托、资金流水、分红、换汇，输出 CollectorX 事件、券商/交易表/字段覆盖、账户边界、币种市场、费用税费保证金、强交易可用面、资产数值汇总、来源审计 manifest 和 FinClaw 投资分身证据包；不读取密码，不下单，不撤单。
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
- 授权 ZIP 包：支持券商 statement/export 打包文件，保留包内成员路径。
- `manifest.broker_coverage`、`manifest.trade_surface_coverage`、`manifest.field_coverage`：记录富途/老虎/盈透、七类强交易表和关键金额字段覆盖。
- `manifest.strong_trade_surface_summary`：记录资产、持仓、成交、委托、资金流水、分红、换汇以及账户、币种、金额、费用、税、保证金、盈亏可用面。
- `manifest.account_boundary_summary`：按券商和账户汇总已观察账户、账户内强交易表、缺失表面和全表面账户候选；仍明确不声明完整账户边界。
- `manifest.currency_market_summary` 与 `manifest.fee_tax_margin_summary`：汇总币种、市场、换汇对、费用、税费、保证金和维持保证金。
- `manifest.asset_value_summary`：按币种汇总导出包中报告的总资产、现金和购买力，并标记是否观察到多币种。
- `manifest.brokerage_boundary_proof`：把授权输入、券商覆盖、交易表覆盖、账户边界、资产数值、多币种、税费保证金、来源审计、Wiki 流向和未完成声明合成一个 FinClaw 可判定的边界证明。
- `manifest.source_audit`：记录授权输入、缺失输入、逐文件解析结果、扩展名覆盖、跳过文件原因、ZIP 成员数量、跳过 ZIP 成员原因、文件/ZIP 成员来源、section/sheet 来源，并声明未采集危险路径成员。
- `manifest.evidence_policy`：声明只读采集、强交易源、不直接写 Wiki、不允许下单/撤单副作用、不声称完整交易边界。

不采集：

- 登录密码、交易密码、cookie、token。
- 下单、撤单、修改委托等交易动作。
- 富途/老虎社区讨论内容。

## CLI

```bash
python3 skills/hk-us-brokerage/scripts/hk_us_brokerage.py collect \
  --input /path/to/authorized/broker-export-or-zip \
  --out-dir /path/to/out
```

输出：

- `lake/hk-us-brokerage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

当前支持 CSV/TSV/JSON/JSONL/NDJSON/XLSX/XLSM/ZIP 本地授权导出；JSON/ZIP 包会展开
assets、positions、executions、orders、cashflows、dividends、fx 等 section。manifest 会
记录逐输入来源审计、跳过原因、ZIP 成员审计、账户/币种/市场摘要、统一券商边界证明和路径安全边界。真实富途、老虎、盈透只读
适配器需要按平台逐个验证。
