---
name: investor-source-collectors
description: 投资分身采集器分类、路由和证据包工具。用于区分 CollectorX 通用采集器、投资垂直采集器和 investor lens/适配层，并把微信投资讨论、投研文档、雪球活动、基金/理财资产、邮件研报、会议纪要、投资笔记、任务日历、公众号收藏、财经资讯使用痕迹、港美股券商、Wind/Choice/iFinD 专业终端使用痕迹、微博/B站/小红书等用户授权证据标准化为 FinClaw/SoulMirror 的 investor_wiki_evidence.v1。
---

# 投资分身采集器分类与路由

## Overview

本技能不是一个“大杂烩采集器”。它是投资分身的分类、路由和证据包工具：帮助 Codex 判断每个通道属于通用采集器、投资垂直采集器，还是基于通用通道的 investor lens。

输出必须先进入 `collectorx.event.v1` lake，再形成 `finclaw.investor_wiki_evidence.v1` 证据包；最终 Wiki 仍由 SoulMirror/FinClaw 的 investor-portrait app 蒸馏组织。

## 分类原则

- `generic`：通用个人数据通道，先忠实采原始证据，不预设它一定是投资数据。例：微信、QQ、邮箱、笔记、文件、日历、任务、飞书、钉钉。
- `vertical`：金融/投资原生通道，源头本身就是账户、投资社区、基金理财、券商、专业终端或财经资讯使用痕迹。例：东方财富、同花顺、雪球、富途、老虎、天天基金、Wind。
- `lens`：投资分身适配层，不重复挖原始数据，只从通用 collector 的 lake 中筛选、标注和路由投资相关证据。例：微信投资讨论、邮件研报、投资笔记、会议纪要。
- `external_research_tool`：公共行情、公告、财报、新闻、研报库、宏观数据。它们服务 FinClaw 研究能力，但不作为用户个人 Wiki 的原始证据采集器。

## 快速开始

```bash
# 查看全部投资分身数据源分类
python <SKILL_DIR>/scripts/investor_sources.py list-sources

# 从用户授权的本地投研文件夹生成 lens 事件、manifest 和证据包
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source research-documents \
  --input ~/Documents/research \
  --out-dir ~/Desktop/research-investor-collect

# 显式授权读取研报/财报/估值表内容；默认不读取二进制文档正文
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source research-documents \
  --input ~/Documents/research \
  --include-content \
  --out-dir ~/Desktop/research-content-investor-collect

# 从微信通用 collector 的授权导出里筛选投资讨论
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source wechat-investment-dialogue \
  --input ~/Desktop/wechat-collect.json \
  --out-dir ~/Desktop/wechat-investor-dialogue

# 审计模式：同时输出未命中的记录，便于回测阈值和白名单
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source email-research \
  --input ~/Desktop/email-events.jsonl \
  --out-dir ~/Desktop/email-research-audit \
  --include-non-matches

# 采集雪球个人活动导出或浏览器保存的 JSON/CSV/文本
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source xueqiu-investor-activity \
  --input ~/Downloads/xueqiu \
  --out-dir ~/Desktop/xueqiu-investor-collect

# 只做授权/输入缺口登记，不伪造业务数据
python <SKILL_DIR>/scripts/investor_sources.py collect \
  --source china-wealth-assets \
  --out-dir ~/Desktop/china-wealth-preflight
```

## 数据源全集

P0 必做：

- `wechat-investment-dialogue`：lens，读取 `wechat` lake，只筛投资讨论、交易理由、咨询对象。
- `research-documents`：lens，读取 `filesystem`/`notes` lake，只筛研报、财报、公告批注、估值表。
- `xueqiu-investor-activity`：vertical，采雪球个人自选、关注、发帖、评论、收藏、组合活动。
- `china-wealth-assets`：vertical，采支付宝、天天基金、蛋卷、且慢、银行理财等非股票账户资产。
- `email-research`：lens，读取 `email` lake，只筛邮件研报、券商晨会、调研邀请。

P1 必做：

- `meeting-minutes`：lens，读取会议/文档通道，只筛路演、调研、投委会纪要。
- `investment-notes`：lens，读取 `notes` lake，只筛投资笔记、规则库、复盘。
- `task-calendar-investor`：lens，读取 `ticktick`/日历 lake，只筛交易计划、复盘提醒、研究任务。
- `wechat-article-favorites`：lens，读取微信收藏/公众号通道，只筛用户收藏、阅读、转发的投资文章。
- `financial-news-usage`：vertical，采财联社、华尔街见闻、格隆汇等财经 App 的用户阅读/收藏/订阅/搜索/提醒痕迹，并报告平台/动作覆盖。

P2 必做：

- `hk-us-brokerage`：vertical，采富途、老虎、盈透等港美股资产、持仓、成交、委托、资金流水、分红、换汇，并报告券商/交易表/字段覆盖。
- `pro-terminal-usage`：vertical，采 Wind、Choice、同花顺 iFinD、Bloomberg 等专业终端工作台、自选、搜索、导出、模板、因子、数据集、字段和函数代码痕迹，并报告终端/活动/字段覆盖。
- `social-investment-influence`：lens，读取微博/B站/小红书通用社交 activity，只筛投资内容影响源；输出仍是弱证据，不能单独形成投资结论。

## 采集边界

- 保留用户授权的业务事实，不脱敏破坏投资分身分析。
- 不读取、不输出登录密码、支付密码、交易密码、Cookie、token、设备指纹和原始通信负载。
- 不把公共行情、新闻、公告、研报库当成用户个人证据；只能记录用户自己的阅读、收藏、批注、下载、转发和讨论。
- 没有真实授权或输入时，只输出缺口事件，不能伪造成已采到。
- 每个通道只采它该采的东西：微信不采资产，券商不采聊天，雪球不采全网舆情，笔记不采交易接口。

## 输出

`collect` 会输出：

```text
<out-dir>/
├── lake/<source>/events.jsonl
├── manifest.json
├── investor_wiki_evidence.v1.json
└── SUMMARY.md
```

事件使用 `collectorx.event.v1`，证据包使用 `finclaw.investor_wiki_evidence.v1`，并按投资分身七大维度、20 个子维度提供覆盖情况。

## Lens 分类器

`lens` 类型的数据源默认会先做投资证据筛选，再写入证据包：

- 命中证券/基金代码、交易动作、仓位、估值、研报、财报、调研、复盘等特征才会进入投资证据。
- 事件会带 `data.classification`，包含置信度、命中原因、关键词和证券代码。
- 默认阈值是 `--min-score 0.30`。
- `--include-non-matches` 只用于审计和回测，会把未命中记录也输出，但仍带分类结果。
- 如果授权输入可读但没有投资证据，输出 `no_investment_evidence_matched` 缺口事件，不会污染 Wiki 覆盖率。

`vertical` 类型的数据源是金融原生通道，默认视为投资证据，但仍会附分类元数据。后续每个 vertical collector 还必须做真实账号/平台验证。

## 参考

- 数据源矩阵：`references/investor-source-profiles.md`
- 分类原则：`../../docs/collector-taxonomy.md`
- 项目事件契约：`../../docs/event-contract.md`
- 项目总矩阵：`../../docs/investor-collector-matrix.md`
