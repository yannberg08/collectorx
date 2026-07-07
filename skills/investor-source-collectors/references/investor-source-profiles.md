# 投资分身数据源矩阵

本技能维护投资分身的分类和路由，不替代每个通道自己的采集器。采集器只处理用户授权的个人证据，不把公共行情、新闻、公告、研报库本身当成个人 Wiki 证据。

| 优先级 | source id | 分类 | 上游/通道 | 作用 |
| --- | --- | --- | --- | --- |
| P0 | `wechat-investment-dialogue` | lens | `wechat` | 交易前后理由、咨询对象、情绪和偏差证据 |
| P0 | `research-documents` | lens | `filesystem`/`notes` | 研报、财报、公告批注、估值表和本地研究文件 |
| P0 | `xueqiu-investor-activity` | vertical | 雪球 | 自选、关注、发帖、评论、收藏、组合活动 |
| P0 | `china-wealth-assets` | vertical | 支付宝/天天基金/蛋卷/且慢/银行理财 | 资产边界 |
| P0 | `email-research` | lens | `email` | 邮件研报、券商晨会、调研邀请 |
| P1 | `meeting-minutes` | lens | 飞书/钉钉/企业微信/腾讯会议 | 路演、调研、会议纪要和投委会记录 |
| P1 | `investment-notes` | lens | `notes` | 投资笔记、规则库、复盘和交易 checklist |
| P1 | `task-calendar-investor` | lens | `ticktick`/`calendar` | 交易计划、研究任务、复盘提醒 |
| P1 | `wechat-article-favorites` | lens | `wechat-favorites` | 公众号阅读、收藏、转发、微信收藏 |
| P1 | `financial-news-usage` | vertical | 财联社/华尔街见闻/格隆汇 | 阅读/收藏/订阅痕迹 |
| P2 | `hk-us-brokerage` | vertical | 富途/老虎/盈透 | 港美股交易和持仓 |
| P2 | `pro-terminal-usage` | vertical | Wind/Choice/iFinD | 专业终端使用痕迹 |
| P2 | `social-investment-influence` | lens | `social-activity` | 微博、B站、小红书等投资内容影响源 |

每个 source profile 都会映射到投资分身七大维度、20 个子维度。证据强度分为：

- `strong_reason`：能直接解释决策理由或复盘。
- `strong_portfolio`：能直接证明资产、持仓或交易事实。
- `medium_reason`：能辅助解释研究和协作过程。
- `medium_attention`：能证明关注、阅读和机会池。
- `medium_process`：能证明工作流、任务和工具使用。
- `weak_attention`：只能作为影响源和注意力线索。

没有授权输入时，采集器只输出缺口事件，不能伪造数据。
