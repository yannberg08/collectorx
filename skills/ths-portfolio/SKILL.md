---
name: ths-portfolio
description: 采集同花顺交易记录、估算持仓与个人化投资元数据。当用户说"同花顺记录"、"交易记录"、"交割单"、"持仓画像"、"自选股"、"投资者画像"时使用此skill。
version: 0.5.0
---

# 同花顺投资数据采集工具

## 功能

- 解析同花顺导出的CSV交割单
- 解析同花顺 Mac 本机保存的 XcsLscj 历史成交文件
- 提取交易记录（买入/卖出/成交金额等）
- 从历史成交保守估算当前持仓候选
- 读取已登录、已打开的同花顺 Mac 交易界面真实账户快照：总资产、总市值、总盈亏、当日盈亏、资金余额、可取金额、可用金额、真实持仓、当日委托、当日成交、资金明细
- 读取同花顺本机个人化元数据：自选股分组、策略标签、资讯阅读标记、短线工具配置、组件/页面布局
- 支持多种CSV格式
- 输出标准化JSON和 CollectorX Event JSONL
- 明确区分“券商确认快照”和“历史成交推导”
- 为 FinClaw investor-portrait / investor Wiki 提供可蒸馏事件

## 使用方法

```bash
# 解析交割单CSV
python <SKILL_DIR>/scripts/ths_query.py --file ~/Downloads/交割单.csv

# 导出为JSON
python <SKILL_DIR>/scripts/ths_query.py --file ~/Downloads/交割单.csv --export ~/Desktop/portfolio.json

# 导出为 CollectorX Event JSONL,用于 lake / distill / wiki 闭环
python <SKILL_DIR>/scripts/ths_query.py --file ~/Downloads/交割单.csv --event-export ~/Desktop/ths-events.jsonl

# 解析同花顺 Mac 本机历史成交文件
python <SKILL_DIR>/scripts/ths_query.py --local-xcs-file ~/Library/Containers/cn.com.10jqka.macstockPro/Data/Documents/XcsFold/XcsLscjDataFile_xxx_xxx --export ~/Desktop/ths-trades.json

# 自动扫描同花顺 Mac 容器,输出交易事件 + 估算持仓事件 + 缺口状态事件
python <SKILL_DIR>/scripts/ths_query.py --local-scan --event-export ~/Desktop/ths-events.jsonl --holdings-export ~/Desktop/ths-estimated-holdings.json --include-holding-events --gap-event

# 导出同花顺个人化元数据,用于投资者画像蒸馏
python <SKILL_DIR>/scripts/ths_query.py --metadata-export ~/Desktop/ths-metadata.json

# 一次性输出交易、估算持仓、采集缺口与个人化元数据事件
python <SKILL_DIR>/scripts/ths_query.py --local-scan --metadata-export ~/Desktop/ths-metadata.json --event-export ~/Desktop/ths-events.jsonl --include-holding-events --include-metadata-events --gap-event

# 从已打开的同花顺交易界面读取真实账户快照
python <SKILL_DIR>/scripts/ths_query.py --gui-snapshot-export ~/Desktop/ths-gui-snapshot.json --gui-screenshot-dir ~/Desktop/ths-gui-screens

# 输出真实账户快照事件：资金、真实持仓、委托、成交、资金明细
python <SKILL_DIR>/scripts/ths_query.py --gui-snapshot-export ~/Desktop/ths-gui-snapshot.json --event-export ~/Desktop/ths-events.jsonl --include-gui-events --gui-screenshot-dir ~/Desktop/ths-gui-screens

# Windows代码层模拟：指定一个模拟根目录,验证扫描/解析/事件输出链路
python <SKILL_DIR>/scripts/ths_query.py --platform windows --container-root <SIM_ROOT> --local-scan --probe-export ~/Desktop/ths-probe.json --event-export ~/Desktop/ths-events.jsonl --include-holding-events --gap-event

# 输出完整采集包：lake/events、manifest、投资 Wiki 证据包、摘要
python <SKILL_DIR>/scripts/ths_query.py --local-scan --output ~/Desktop/ths-portfolio-collect

# 输出完整采集包并同步到 SoulMirror lake；最终 Wiki 仍由 investor-portrait app 组织
python <SKILL_DIR>/scripts/ths_query.py --local-scan --output ~/Desktop/ths-portfolio-collect --sync-soulmirror

# 若同花顺交易页已登录并打开,可一起采集当前资产/持仓/委托/成交快照
python <SKILL_DIR>/scripts/ths_query.py --local-scan --include-gui-events --gui-screenshot-dir ~/Desktop/ths-gui-screens --output ~/Desktop/ths-portfolio-collect --sync-soulmirror

# 查看统计
python <SKILL_DIR>/scripts/ths_query.py --file ~/Downloads/交割单.csv --stats
```

## CSV格式支持

### 格式1：标准同花顺格式
```
成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税,过户费
2024-01-15 09:30:00,600519,贵州茅台,买入,1800.00,100,180000.00,54.00,0.00,1.80
```

### 格式2：简化格式
```
日期,代码,名称,方向,价格,数量,金额
2024-01-15,600519,贵州茅台,买入,1800.00,100,180000.00
```

## 输出格式

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

- CSV模式需要用户从同花顺APP手动导出CSV
- 本机模式只读取用户本机同花顺容器中的历史成交落地文件
- Mac 本机 XcsLscj 路径已在当前机器跑通
- Windows 本机路径目前只有代码层候选规则和模拟夹具,需要真实 Windows 同花顺安装后验证
- 当前持仓、资金余额、可用资金、当日委托、撤单等只有来自已登录交易界面的 Accessibility 确认快照时才标记为 confirmed
- 如果本机没有确认快照,本工具只输出 `estimated_from_historical_trades` 估算持仓,不填实时市值和浮动盈亏
- 自选股和本机配置是个人化证据；策略标签、短线工具、组件布局可能混有同花顺产品默认值,进入 Wiki 时应先按 weak/medium evidence 蒸馏
- 不读取、不导出 Cookie、密码、token 等凭证
- 不自动荐股、不自动下单、不绕过用户确认闸
- GUI 模式只按 `持仓`、`委托`、`成交`、`资金明细` 四个只读页签；不按 `确定买入`、`确定卖出`、`撤单`、`银证转账`、`退出` 等动作按钮

## 平台适配状态

| 平台 | 状态 | 说明 |
| --- | --- | --- |
| CSV导入 | 可跨平台 | 只依赖用户导出的交割单文件 |
| macOS | 已在当前机器跑通 | 支持 `~/Library/Containers/cn.com.10jqka.macstockPro/Data/Documents/XcsFold/XcsLscjDataFile_*` |
| macOS GUI确认快照 | 已在当前机器跑通 | 需要用户已登录同花顺并打开交易界面,通过 Accessibility 只读读取 |
| Windows | 代码层模拟 | 支持 `--platform windows --container-root <SIM_ROOT>` 验证扫描骨架,真实路径未验证 |
| generic | 兜底扫描 | 用于研究未知系统的数据结构,不作产品承诺 |

`--probe-export` 会输出平台探测报告,只包含平台、扫描根目录标签、找到的 Xcs 文件数量和能力状态。账号号段会脱敏,委托号/成交号只在解析后进入哈希字段。

## 个人化元数据

`--metadata-export` 会输出 `ths.personal_metadata.v1` JSON,当前包括：

- `watchlist_items/watchlist_groups`: 自选股与分组,可支撑关注行业、能力圈、机会池
- `strategy_rules/strategy_topics/strategy_label_summary`: 同花顺 KYC/策略标签,可作为决策框架和主题偏好的弱证据
- `news_read_markers`: 资讯阅读标记,可作为信息源和研究消费线索
- `short_term_rules`: 短线精灵/监控配置,可作为交易纪律和监控偏好的弱证据
- `widget_layouts/custom_pages`: 页面和组件布局,可作为研究工作流偏好线索

加上 `--include-metadata-events` 后,这些元数据会进入 CollectorX 事件流：

- `watchlist` 事件流向 `investor.opportunity_watchlist.watchlist` 与 `investor.capability_circle.attention_universe`
- `profile` 事件流向 `investor.decision_framework.*`、`investor.research_consumption.workflow`、`investor.capability_circle.*`
- `other` 资讯阅读事件流向 `investor.information_sources.news_consumption`

## GUI确认快照

`--gui-snapshot-export` 会读取已打开的同花顺交易窗口,输出 `ths.gui_snapshot.v1` JSON。当前支持：

- `asset_snapshot`: 总资产、总市值、总盈亏、当日盈亏、资金余额、可取金额、可用金额、风险测评状态
- `tabs.holding`: 真实持仓表,包括证券代码、证券名称、市价、盈亏、当日盈亏、浮动盈亏比、实际数量、股票余额、可用余额、冻结数量、成本价、市值、仓位占比、交易市场、股东账户
- `tabs.orders`: 当日委托表,包括委托日期、委托时间、证券代码、证券名称、操作、备注、委托数量、撤销数量、委托价格、成交价格、合同编号、申报编号、委托属性
- `tabs.deals`: 当日成交表,包括成交日期、成交时间、证券代码、证券名称、操作、成交数量、成交均价、成交金额、合同编号、成交编号
- `tabs.funds_detail`: 资金明细表,包括成交日期、证券代码、证券名称、操作、成交数量、成交均价、发生金额、本次金额、交易市场、股东账户、摘要、货币单位、成交时间

加上 `--include-gui-events` 后,会追加：

- `asset_snapshot` 事件：确认资产/现金快照
- `holding` 事件：确认当前持仓,`snapshot_type=broker_gui_current_snapshot`,`is_confirmed=true`
- `order` 事件：当日委托/撤单/废单等委托行,如果表为空则输出确认空表 profile 事件
- `execution` 事件：当日成交行
- `cashflow` 事件：资金明细行,如果表为空则输出确认空表 profile 事件

## CollectorX事件输出

`--event-export` 会输出 `collectorx.event.v1` JSONL。默认每一行是一条 `trade` 事件，包含：

- `id`: 稳定事件ID
- `collector`: `ths-portfolio`
- `owner_scope`: `personal`
- `kind`: `trade`
- `data.symbol/name/side/price/quantity/amount/fee/tax`
- `raw_ref.file/row`
- `privacy.local_only: true`

加上 `--include-holding-events` 后,会追加 `holding` 事件：

- `data.snapshot_type`: `estimated_from_historical_trades`
- `data.evidence_level`: `estimated`
- `data.is_confirmed`: `false`
- `data.quantity/cost/avg_cost`: 由历史成交滚动估算
- `data.market_value/unrealized_pnl`: 本机无确认快照时保持 `null`

加上 `--gap-event` 后,会追加一条 `profile` 事件,记录本轮本机采集未发现的关键硬证据：

- 当前持仓确认快照
- 总资产/可用资金/现金余额快照
- 当日委托/撤单快照

这些事件进入 lake 后,由 `investor-portrait` 这类应用负责组织到投资分身 Wiki。

## SoulMirror lake 同步

`--output` 会创建完整采集包：

```text
ths-portfolio-collect/
├── manifest.json
├── investor_wiki_evidence.v1.json
├── SUMMARY.md
├── trades.normalized.json
├── estimated_holdings.json
├── metadata.json
├── gui_snapshot.json              # 仅在采集 GUI 时存在
├── probe.json
└── lake/ths-portfolio/events.jsonl
```

`--sync-soulmirror` 会把以下文件同步到：

```text
~/.soulmirror/lake/ths-portfolio/<run-id>/
~/.soulmirror/lake/ths-portfolio/latest/
```

同步文件包括：

- `events.jsonl`
- `investor_wiki_evidence.v1.json`
- `manifest.json`
- `SUMMARY.md`
- `soulmirror_sync.json`

同步只写 lake，不直接写最终 Wiki。SoulMirror 的 `investor-portrait` app 负责把证据蒸馏并组织到 `wiki/external/investor/`。

## 投资 Wiki 证据包

`investor_wiki_evidence.v1.json` 按当前 SoulMirror 投资分身 schema 输出：

- 7 大维度
- 20 个产品子维度
- 每个子维度包含：`support_level`、`suggested_maturity`、`evidence_count`、`evidence_kinds`、`signals`、`gaps`

这份证据包是 Wiki 组织输入，不是最终 Wiki 页面。原始交易金额、账户、合同号、成交号、截图和完整流水仍留在本地证据包，不应直接暴露到 Wiki 正文。

## 数据流向Wiki

交割单数据可流向以下Wiki维度：

- **投资/决策记录与复盘系统/决策日志**：买入卖出动作证据
- **投资/风险偏好与组合约束/组合约束**：交易金额和集中度线索
- **投资/决策框架/仓位决策**：单笔交易规模线索
- **外在/资源/资产**：仅作为资产线索,不能替代完整持仓
- **投资/能力圈与关注行业/关注池**：自选股和分组线索
- **投资/信息源与研究网络/资讯消费**：资讯阅读标记、同花顺页面配置线索
- **投资/决策框架/策略规则**：策略标签、短线工具配置线索
- **投资/交易纪律/监控规则**：短线工具和组件布局线索

注意：交割单只能证明用户做了什么,不能证明为什么做。买卖理由、风险偏好和能力圈需要结合投研笔记、聊天讨论、持仓快照和复盘记录继续蒸馏。

## 证据边界

FinClaw 的投资分身需要“决策操作系统”,不是简单复制交易流水。本技能采用三层证据：

1. **强事实**：历史成交记录,证明发生过的交易动作。
2. **保守推导**：由历史成交估算的剩余持仓,只能作为当前组合候选。
3. **显式缺口**：未采到的真实持仓/资金/委托快照,单独进入数据质量维度。

下游蒸馏时,估算持仓可以用于识别能力圈、仓位偏好和交易节奏,但不能作为真实资产证明。
