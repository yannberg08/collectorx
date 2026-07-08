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
- 资产边界证明：按平台和账户判断是否有账户引用、资产快照、持仓、交易和金额字段。

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

python <SKILL_DIR>/scripts/china_wealth.py collect \
  --input ~/Downloads/china-wealth-network.har \
  --out-dir ~/Desktop/china-wealth-collect

python <SKILL_DIR>/scripts/china_wealth.py collect \
  --input ~/Downloads/bank-wealth-statement.pdf \
  --out-dir ~/Desktop/china-wealth-collect

# 可选：按用户授权范围收窄资产记录
python <SKILL_DIR>/scripts/china_wealth.py collect \
  --input ~/Downloads/china-wealth-export.zip \
  --out-dir ~/Desktop/china-wealth-collect \
  --allow-platform alipay \
  --allow-account ali-main \
  --allow-product-code 000001 \
  --deny-keyword 私人
```

支持 CSV/TSV/JSON/JSONL/Excel/旧式 `.xls`/HTML 表格/PDF 官方账单/TXT/Markdown/HAR/ZIP。
解析器会归一化支付宝、天天基金、蛋卷、且慢和银行理财的常见字段，保留资产、持仓、申赎、分红、
成本、收益等数字字段，并剔除 cookie、token、password 等凭据类字段。
PDF 账单通过本地 `pdfplumber` 读取文本和表格，不做远程 OCR；能提取表格时会保留页码、表格号、
行号和 PDF parser 审计，无法结构化时只作为授权账单快照，不伪造资产数字。
HAR 是用户已登录对应平台后、明确授权选择的浏览器网络导出文件。采集器只读取
支付宝/天天基金/蛋卷/且慢/银行理财域名白名单内的响应体，按域名推断平台，
并记录接口路径、状态、平台覆盖和跳过原因；请求头、Cookie、Authorization 和
URL 查询串不会写入事件、manifest 或 Wiki evidence。

ZIP 包会保留 `archive.zip::member` 来源并跳过路径穿越成员，ZIP 内也可包含 PDF 官方账单。
manifest 会记录
输入文件数、扩展名覆盖、HAR 网络包覆盖、ZIP 成员/跳过成员、解析记录数、
PDF 文件数、页数、表格数、PDF 表格记录数、发出事件数和路径级结果。
没有授权输入时，只输出缺口事件。

可用 platform、account、subtype、product-code、product-name、currency、side、
keyword 的 allow/deny 授权范围过滤。`manifest.collection_audit.china_wealth_scope_policy`
会记录配置、候选记录数、保留数、过滤数和过滤原因；如果全部候选记录都被授权范围排除，
`manifest.collection_readiness.status` 会变为 `scope_policy_filtered_all`，不会伪造空成功。
`manifest.asset_boundary_proof.authorization_scope_boundary` 会给 FinClaw 检查资产授权边界。

## 完整性口径

本技能解析到基金/理财记录后，manifest 会标记为 `partial_authorized_input`。
这代表“采到了用户授权输入里的资产证据”，不代表已经覆盖用户全部支付宝、天天基金、蛋卷、且慢、银行理财和现金管理账户。

`manifest.platform_coverage` 会列出 P0 预期平台：

- `alipay`
- `tiantian-fund`
- `danjuan`
- `qieman`
- `bank-wealth`

并记录本次输入中已观察到的平台、缺失平台、unknown 事件数，以及
`real_account_validation: false`。即使五类平台都在授权文件里出现，也只能说明
“输入覆盖”，不能说明已经完成真实账号边界证明。

只有未来逐个平台完成只读真机/真实账号验证，并能证明账户覆盖范围时，FinClaw 才能把它当作完整资产边界。

`manifest.field_coverage` 会列出平台、产品代码、产品名称、份额、净值、市值、
总资产、现金、成本、收益、申赎金额等推荐字段覆盖情况；`asset_value_summary`
会按平台汇总本次授权输入里的市值、总资产和交易金额。

`manifest.account_boundary_summary` 会按平台和账户引用汇总本次输入覆盖的账户组、
资产面、产品数、币种和值字段；`asset_surface_summary` 会说明是否看到了资产快照、
基金持仓、理财持仓、现金管理和申赎/分红交易；`currency_summary` 会按币种和
平台-币种汇总金额字段。这些摘要可进入 FinClaw/SoulMirror 的投资分身 Wiki，
但仍只代表用户授权输入内的证据。

`manifest.asset_boundary_proof` 会进一步给出本次授权输入的资产边界证明强度：

- `strong_partial_asset_boundary`：至少有命名账户、金额字段，并同时看到资产快照和持仓面。
- `medium_partial_asset_boundary`：有命名账户和金额字段，但只覆盖快照/持仓/交易中的一部分。
- `weak_partial_asset_boundary`：只有部分金额或资产面，缺账户名、平台或关键面谱。

这些强度仍然都是 `partial`。没有真实账号/只读界面逐平台验证前，不会声明完整资产边界。
