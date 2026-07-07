---
name: china-wealth-assets
description: 中国基金理财资产垂直采集器。采集用户授权的支付宝基金、天天基金、蛋卷、且慢、银行理财等非股票账户资产、基金持仓、理财持仓、申购赎回、收益、成本和资产快照，输出 CollectorX holding/trade/other 事件和投资分身证据包。用于补齐投资分身的全资产边界；不采支付密码、银行卡密码、消费流水或非投资支付行为。
---

# 中国基金理财资产采集器

本技能补齐券商账户之外的投资资产：基金、理财、组合、现金管理和申赎记录。

## 采什么

- 资产快照：平台、账户、总资产、币种、更新时间。
- 基金/理财持仓：产品代码、名称、份额、净值、市值、成本、收益。
- 交易记录：申购、赎回、定投、转换、分红。

## 不采什么

- 不采支付密码、银行卡密码、登录凭证。
- 不采消费流水。
- 不下单、不赎回、不转账。
- 不把非投资支付行为放入投资分身。

## 使用

```bash
python <SKILL_DIR>/scripts/china_wealth.py collect \
  --input ~/Downloads/fund-export.csv \
  --out-dir ~/Desktop/china-wealth-collect \
  --sync-soulmirror
```

支持 CSV/TSV/JSON/JSONL/Excel/HTML/TXT/Markdown。解析器会归一化支付宝、
天天基金、蛋卷、且慢和银行理财的常见字段，保留资产、持仓、申赎、分红、
成本、收益等数字字段，并剔除 cookie、token、password 等凭据类字段。
没有授权输入时，只输出缺口事件。

## 完整性口径

本技能解析到基金/理财记录后，manifest 会标记为 `partial_authorized_input`。
这代表“采到了用户授权输入里的资产证据”，不代表已经覆盖用户全部支付宝、天天基金、蛋卷、且慢、银行理财和现金管理账户。

只有未来逐个平台完成只读真机/真实账号验证，并能证明账户覆盖范围时，FinClaw 才能把它当作完整资产边界。
