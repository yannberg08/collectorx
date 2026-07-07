# FinClaw 投资分身采集器矩阵

投资分身需要四类证据：强交易事实、原因/信息、约束/资产边界、复盘/执行。不同通道只采自己应该采的内容。分类规则见 `docs/collector-taxonomy.md`。

## 分类

| 类型 | 说明 | 例子 |
| --- | --- | --- |
| `generic` | 通用个人通道，先采原始证据，不预设投资含义 | 微信、邮箱、笔记、文件、日历、任务、会议、社交活动 |
| `vertical` | 金融/投资原生通道，直接采投资业务事实或投资活动 | 东方财富、同花顺、雪球、富途、基金理财、财经资讯、专业终端 |
| `lens` | 投资分身适配层，从 generic lake 筛选和路由投资证据 | 微信投资讨论、邮件研报、投资笔记、投研会议纪要 |

## P0 核心闭环

| Collector | Skill | 目标 |
| --- | --- | --- |
| `eastmoney-portfolio` | `eastmoney-portfolio` | vertical：东方财富资产、持仓、成交、委托、资金流水 |
| `ths-portfolio` | `ths-portfolio` | vertical：同花顺交易、持仓、自选和工作流证据 |
| `wechat` | `wechat-export` | generic：微信聊天原始通道 |
| `wechat-investment-dialogue` | `investor-source-collectors` | lens：微信投资讨论、理由、咨询对象、情绪 |
| `filesystem`/`notes` | daemon/`notes-collector` | generic：本地文件和笔记原始通道 |
| `research-documents` | `investor-source-collectors` | lens：研报、财报、公告批注、估值表 |
| `xueqiu-investor-activity` | `xueqiu-watchlist` -> dedicated skill | vertical：雪球自选、关注、发帖、评论、收藏、组合 |
| `china-wealth-assets` | dedicated skill | vertical：支付宝、天天基金、蛋卷、且慢、银行理财 |
| `email` | `email-collector` | generic：邮箱原始通道 |
| `email-research` | `investor-source-collectors` | lens：邮件研报、券商晨会、调研邀请 |

## P1

| Collector | Skill | 目标 |
| --- | --- | --- |
| `meeting-artifacts` | `meeting-artifacts` | generic：飞书、钉钉、腾讯会议纪要/逐字稿/字幕原始通道 |
| `meeting-minutes` | `investor-source-collectors` | lens：路演、调研、投委会纪要 |
| `notes` | `notes-collector` | generic：Obsidian、Notion、有道云、印象笔记 |
| `investment-notes` | `investor-source-collectors` | lens：投资笔记、规则库、复盘 |
| `ticktick`/`calendar` | `ticktick-cli`/placeholder | generic：任务和日历原始通道 |
| `task-calendar-investor` | `investor-source-collectors` | lens：交易计划、复盘提醒、研究任务 |
| `wechat-favorites` | `wechat-favorites` | generic：微信收藏/公众号文章动作 |
| `wechat-article-favorites` | `investor-source-collectors` | lens：投资公众号阅读、收藏、转发 |
| `financial-news-usage` | `financial-news-usage` | vertical：财联社、华尔街见闻、格隆汇等用户阅读/收藏/订阅痕迹 |

## P2

| Collector | Skill | 目标 |
| --- | --- | --- |
| `hk-us-brokerage` | `hk-us-brokerage` | vertical：富途、老虎、盈透等港美股交易与持仓 |
| `pro-terminal-usage` | dedicated skill | vertical：Wind、Choice、同花顺 iFinD 等专业终端使用痕迹 |
| `social-activity` | generic placeholder | generic：微博、B站、小红书用户活动 |
| `social-investment-influence` | `investor-source-collectors` | lens：投资内容影响源、创作者、收藏/点赞/观看 |

## Wiki 路由

所有采集器都必须先输出 `collectorx.event.v1`，再输出或汇总为 `finclaw.investor_wiki_evidence.v1`。最终 Wiki 不由采集器直接写入，而由 SoulMirror/FinClaw 的 investor-portrait app 统一蒸馏。

覆盖目标是 `external.investor / 7 dimensions / 20 subdimensions`：

- 投资哲学与信念：市场观、风险观、价值偏好
- 能力圈定义：行业能力圈、分析能力、信息处理与学习风格
- 投资风格与策略：风格画像、买入决策框架、卖出决策框架
- 行为特征与偏差画像：认知偏差档案、情绪模式、决策与适应风格
- 决策记录与复盘系统：决策日志、复盘记录、投资规则库
- 组合与执行：组合管理偏好、执行纪律、时间偏好
- 信息网络与人脉：信息源、咨询对象
