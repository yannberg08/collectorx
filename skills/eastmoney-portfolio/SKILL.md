---
name: eastmoney-portfolio
description: 采集东方财富用户投资行为数据，支持东方财富 Mac 本机自选/近期查看/交易接口状态/研究工作流证据采集，并支持自动打开东方财富交易页，只读采集资产、持仓、成交、委托、资金流水等投资分身需要的强交易元数据；手动交易明细文件仅作为兼容兜底。适用于 FinClaw 投资分身、用户数据采集、东方财富记录、交易记录、持仓/资产边界、投资决策链路复盘等场景。
---

# 东方财富投资行为采集工具

## 采集原则

采集的是投资分身需要理解的“决策链路证据”，不是泛泛的身份资料。

必须把四类信息分开：

- 强交易事实：交易页自动只读采集到的资产、持仓、成交、委托/撤单、资金流水表；交易接口日志中明确返回的持仓/资产状态；兼容兜底的交割单或明细文件。
- 中证据：东方财富本地自选组、近期查看、股票笔记、自选同步状态。
- 弱证据：交易页标的上下文、画线、面板、登录状态等工作流线索。
- 缺口事件：交易账户锁定、交易窗口不存在、表格不可复制、本地日志没有落地金额或逐笔明细。

不得输出登录凭据、会话凭据、签名、设备指纹、原始通信负载、浏览器存储体。路径、账户名、客户号等标识必须脱敏或哈希。

## 投资分身数据边界

投资分身需要的是能重建个人投资画像的数据，而不是“接口成功/失败”这样的空壳状态。

应采集：

- 账户与资产状态：证券账户是否已解锁、总资产、总市值、可用资金、可取资金、资金余额、冻结资金、持仓盈亏、当日参考盈亏、货币单位。
- 当前持仓：证券代码、名称、市场、持仓数量、可用数量、冻结数量、成本价、最新价、市值、盈亏、盈亏比、币种。
- 交易流水：成交日期/时间、证券代码、名称、买卖方向、成交价格、数量、金额、手续费、印花税、过户费、成交号哈希、委托号哈希。
- 委托与撤单：委托日期/时间、方向、委托价、委托数量、成交数量、撤单数量、委托状态、委托号哈希。
- 资金流水：发生日期/时间、业务类型、发生金额、资金余额、摘要。
- 研究与偏好：自选分组、近期查看、股票笔记、画线、看盘面板、交易页标的上下文。
- 采集缺口：账户锁定、窗口缺失、表格复制失败、接口只返回状态不返回明细。

不采集：

- 交易密码、登录密码、验证码、Cookie、Token、Session、签名、设备指纹、原始网络包、HTTP/浏览器存储。
- 会改变账户状态的动作：下单、撤单、转账、修改设置、解锁输入。
- 原始账号、客户号、股东号、委托号、成交号；这些字段只输出脱敏值或哈希。

## Soulmirror Wiki 元数据格式

主交付物是 `lake/eastmoney-investor-v2/events.jsonl`，每一行必须是 `collectorx.event.v1`：

- `kind` 使用 CollectorX/Soulmirror 标准枚举：`watchlist`、`trade`、`holding`、`note`、`profile`、`other` 等。
- 东方财富细分事件名保存在 `data.source_kind`，例如 `broker_trade_ui_status`、`broker_position_status`、`broker_trade_execution`。
- `wiki_targets` 使用 Soulmirror/THS 对齐的点分路由，不使用旧的 `vertical/investor/...` 路径。
- 所有个人标识、账号、委托号、成交号只输出脱敏值或哈希。

直接生成的 Markdown Wiki 只是便于检查的 deterministic organize 结果。主路径仍是：

```text
collector skill
  -> collectorx.event.v1 JSONL
  -> lake
  -> distill app
  -> wiki/external/investor/
```

本技能同时输出：

```text
wiki/external/investor/   # Soulmirror 原生投资分身路径
wiki/vertical/investor/   # CollectorX 旧版兼容路径
```

Markdown 文件必须带 frontmatter：

```yaml
---
maturity: hint|basic|solid|mature
source: eastmoney-investor-v2
collector: eastmoney-investor-v2
evidence_level: medium|strong_status_only|gap_boundary
wiki_targets:
  - investor.record_review.decision_log
---
```

### 七大维度路由

按本地 Soulmirror 投资分身文档，投资分身是 `external.investor` 子维度。东方财富事件当前可路由到：

- 投资哲学与信念：当前缺少直接证据，只能通过后续投研笔记/复盘补齐。
- 能力圈定义：`investor.capability_circle.attention_universe`，来自自选股、近期查看、标的上下文。
- 投资风格与策略：`investor.decision_framework.*`，来自交易页标的上下文、面板、画线、委托/成交规模。
- 行为特征与偏差画像：当前缺少直接情绪/偏差证据，需要交易前后聊天、笔记、复盘。
- 决策记录与复盘系统：`investor.record_review.decision_log`，来自成交、委托、交易接口状态。
- 组合与执行：`investor.risk_portfolio.*`、`investor.execution.orders`、`external.capital.*`，来自资产、持仓、委托、成交、资金流水。
- 信息网络与人脉：`investor.information_sources.news_consumption`、`investor.research_consumption.workflow`，来自近期查看、股票笔记、画线和看盘面板。

数据质量统一进入 `investor.data_quality.collection_gaps`，包括账户锁定、交易窗口缺失、表格不可复制、接口只返回状态不返回明细。

## 功能

- 采集东方财富经典版 Mac 本机数据。
- 支持 `--platform auto|mac|windows|generic` 与 `--probe-export` 进行平台探测。
- 支持 Windows 目录规则的代码层模拟；真实 Windows 安装路径仍需真机验证。
- 支持 `--auto-trade-ui` 自动打开东方财富交易页，识别账户锁定状态，并只读采集资产/持仓/成交/委托/资金表。
- 解析自选股、分组、近期查看。
- 读取股票笔记、画线、看盘面板结构；没有数据时输出缺口事件。
- 解析交易接口日志中的持仓/资产查询状态，只记录可证明的状态，不虚构金额。
- 从交易页可访问文本中直接识别总资产、总市值、可用资金、可取资金、资金余额、冻结资金、盈亏和币种，形成资产快照强证据。
- 解析东方财富交易页复制出的资产、持仓、成交、委托、资金流水明细表。
- 保留交易明细文件和 CSV 交割单解析，作为兼容兜底，不是 FinClaw 一键采集主流程。
- 输出 `manifest.json`、`events.jsonl`、`structured_profile.json`、`investor_wiki_evidence.v1.json` 和投资 wiki 文档。

## 使用方法

```bash
# 一键深采东方财富 Mac 本机投资行为证据
python <SKILL_DIR>/scripts/eastmoney_query.py \
  --collect-local \
  --auto-trade-ui \
  --sync-soulmirror \
  --output ~/Desktop/eastmoney-investor-v2-collect

# 导出安全探测报告，不采集正文数据
python <SKILL_DIR>/scripts/eastmoney_query.py \
  --platform mac \
  --probe-export ~/Desktop/eastmoney-probe.json

# Windows 代码层模拟：指定一个模拟根目录，验证扫描/采集/缺口输出链路
python <SKILL_DIR>/scripts/eastmoney_query.py \
  --collect-local \
  --platform windows \
  --container-root <SIM_ROOT> \
  --probe-export ~/Desktop/eastmoney-probe.windows.json \
  --output ~/Desktop/eastmoney-windows-sim-collect

# 兼容兜底：读取已有交易明细文件，不作为一键采集主流程
python <SKILL_DIR>/scripts/eastmoney_query.py \
  --collect-local \
  --trade-export-dir ~/Downloads/eastmoney-trade-exports \
  --output ~/Desktop/eastmoney-investor-v2-collect

# 解析交割单CSV
python <SKILL_DIR>/scripts/eastmoney_query.py --file ~/Downloads/交割单.csv

# 导出为JSON
python <SKILL_DIR>/scripts/eastmoney_query.py --file ~/Downloads/交割单.csv --export ~/Desktop/portfolio.json

# 查看统计
python <SKILL_DIR>/scripts/eastmoney_query.py --file ~/Downloads/交割单.csv --stats
```

## 默认本机数据源

默认读取：

```text
~/Library/Containers/com.emmac.mac/Data/Library/Application Support/EastMoney
```

可用 `--eastmoney-home` 覆盖精确数据目录；可用 `--container-root` 指定扫描根目录。若存在多个本地用户目录，可用 `--user` 指定。

主要来源：

- `config/user/<user>/SelfStocks_v1.plist`：自选股与分组
- `config/user/<user>/recent_stock.dat`：近期查看
- `config/user/<user>/StockNote.sqlite`：股票笔记
- `config/user/<user>/LineParintv1.db`：画线/图形标注
- `config/user/<user>/EMCustomPanelDatas.sqlite`：自定义看盘面板
- `log/TradeLog.log`：交易接口状态
- `log/SyncSelfStock.log`：自选同步状态
- 东方财富交易页：通过 `--auto-trade-ui` 自动只读读取账户状态与交易表格

## 交易页自动强采集

`--auto-trade-ui` 是 FinClaw 一键采集的交易强证据主路径。

执行时采集器会：

- 激活东方财富经典版并进入交易页。
- 读取交易页可见账户状态，判断证券账户是否锁定。
- 先从交易页可访问文本提取可见资产字段；在账户未锁定时，依次尝试只读复制资产、持仓、成交、委托、资金表。
- 把复制出的表格直接解析为强交易事实事件。
- 采集完成后恢复系统剪贴板。

如果账户锁定，采集器只输出 `broker_trade_ui_status` 和 `broker_account_locked` 缺口事件，不读取或请求交易密码。账户锁定不是“让用户导出文件”，而是明确的强采集边界：交易端未解锁，所以本轮不能形成资产/成交/委托强明细。

自动识别：

- 资产快照：总资产、总市值、可用资金、可取资金、资金余额、冻结资金、持仓盈亏、当日参考盈亏、币种。
- 持仓明细：证券代码、名称、市场、持仓数量、可用数量、冻结数量、成本价、最新价、最新市值、盈亏、盈亏比、币种。
- 成交明细：成交日期/时间、代码、名称、买卖方向、成交价格、数量、金额、费用。
- 委托/撤单：委托日期/时间、代码、名称、方向、委托价、委托数量、成交数量、撤单数量、状态。
- 资金流水：发生日期/时间、业务、发生金额、资金余额、摘要。

## 兼容文件入口

`--trade-export` 可重复传入单个明细文件，`--trade-export-dir` 会递归读取目录下的 `CSV/TSV/TXT/JSON` 文件。

该入口仅用于历史兼容、测试、异常兜底。账号、股东号、委托号、成交号会脱敏或哈希；金额、数量、价格、盈亏会保留，因为它们是投资 Wiki 形成个人组合、交易节奏和风险偏好的关键事实。

## 平台适配状态

| 平台 | 状态 | 说明 |
| --- | --- | --- |
| macOS | 已在当前机器跑通 | 支持本机文件采集和 `--auto-trade-ui` 交易页只读采集 |
| Windows | 代码层模拟 | 支持 `--platform windows --container-root <SIM_ROOT>` 验证扫描骨架，真实路径未验证 |
| 兼容文件入口 | 可跨平台 | 仅作兜底，不是主采集路径 |
| generic | 兜底扫描 | 用于研究未知系统的数据结构，不作产品承诺 |

`--probe-export` 会输出平台探测报告，只包含平台、扫描根目录标签、找到的东方财富本机数据目录数量和能力状态。账户名会脱敏或哈希；不读取登录材料、签名、设备指纹或原始交易通信负载。

## CSV格式支持

### 格式1：东方财富标准格式
```
成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税,过户费
2024-01-15 09:30:00,600519,贵州茅台,买入,1800.00,100,180000.00,54.00,0.00,1.80
```

### 格式2：东方财富简化格式
```
日期,代码,名称,方向,价格,数量,金额
2024-01-15,600519,贵州茅台,买入,1800.00,100,180000.00
```

## 输出格式

### 本机采集包

```text
<output>/
├── manifest.json
├── structured_profile.json
├── investor_wiki_evidence.v1.json
├── SUMMARY.md
├── lake/eastmoney-investor-v2/events.jsonl
├── wiki/external/investor/
├── wiki/vertical/investor/
└── soulmirror_sync.json        # 仅在 --sync-soulmirror 时生成
```

`manifest.json` 和 `structured_profile.json` 中包含 `collection_readiness`：

- `ready_for_investor_avatar`：资产、持仓、成交、委托、资金流水强表均已形成事件。
- `blocked_by_account_lock`：交易页存在但证券账户锁定；采集器不会读取或请求交易密码。
- `partial_strong_trade_data`：已取得部分强交易事实，仍缺若干强表。
- `strong_trade_data_missing`：交易页已尝试但没有形成强交易明细。

`investor_wiki_evidence.v1.json` 是 FinClaw/SoulMirror 的投资分身中间证据包，按七大维度、20 个产品子维度列出证据强度、事件计数、路由建议和缺口。采集器不把这份 JSON 直接写入最终 Wiki；最终组织仍由 `investor-portrait` app 处理。

`--sync-soulmirror` 会把 `events.jsonl`、`investor_wiki_evidence.v1.json`、`manifest.json`、`structured_profile.json` 和 `SUMMARY.md` 同步到 `~/.soulmirror/lake/eastmoney-investor-v2/latest/` 以及对应时间戳目录。它只同步证据到 lake，不直接改最终 Wiki。

事件格式对齐 CollectorX：

```json
{
  "schema": "collectorx.event.v1",
  "collector": "eastmoney-investor-v2",
  "kind": "watchlist",
  "owner_scope": "personal",
  "data": {
    "source_kind": "watchlist"
  },
  "privacy": {
    "sensitive": true,
    "local_only": true,
    "contains": ["portfolio"]
  },
  "wiki_targets": ["investor.opportunity_watchlist.watchlist"]
}
```

### CSV 解析结果

```json
[
  {
    "date": "2024-01-15",
    "time": "09:30:00",
    "code": "600519",
    "name": "贵州茅台",
    "direction": "买入",
    "price": 1800.00,
    "quantity": 100,
    "amount": 180000.00,
    "fee": 54.00,
    "tax": 0.00
  }
]
```

## 限制

- 本机采集不读取原始登录材料。
- 当前 Mac 东方财富本地 `TradeLog.log` 只落出接口状态和返回记录数，没有逐笔明细字段；逐笔强证据优先来自 `--auto-trade-ui` 交易页自动只读采集。
- 如果东方财富交易页显示证券账户已锁定，采集器不会读取或请求交易密码，只输出锁定缺口。
- 如果交易页表格为空或不可复制，采集器会输出表格不可读缺口，不虚构金额或交易记录。
- 如果交易页已显示资产字段但表格不可复制，采集器仍会把可见资产字段写成 `broker_asset_snapshot`，并将表格缺口单独记录。
- Windows 适配目前只有候选目录规则和模拟夹具，需要真实 Windows 东方财富安装后验证。
- 如果本地日志只证明“持仓查询成功且记录数为 0”，只能输出状态事件，不能生成持仓明细。
- 如果资产查询没有落地金额字段，只能输出“资产查询状态”，不能生成总资产/可用资金/市值/盈亏。
- 历史成交/委托文件导入是兼容兜底，不应作为 FinClaw 一键采集的默认用户路径。
- 不同券商在东方财富内的交易日志字段可能不同，需要保守解析。

## 数据流向Wiki

数据可流向以下 Wiki 维度：

- **投资/交易历史**：交易页自动成交/委托/资金流水、兼容 CSV 历史成交、交易接口状态
- **投资/持仓变化**：交易页自动资产/持仓快照、持仓查询状态、资产查询状态、数据缺口
- **投资/机会池**：自选股、分组、近期查看
- **投资/研究动作**：股票笔记、画线、看盘面板
- **投资/决策框架**：工作流线索、缺口边界

### 支持的应用

- **投资复盘**：基于真实交易记录和研究动作分析决策。
- **持仓分析**：只在有硬证据时追踪持仓；否则输出边界。
- **机会池画像**：根据自选、近期查看、分组理解关注领域。
- **交易统计**：对 CSV 成交记录计算交易频率、买卖金额、个股统计。
