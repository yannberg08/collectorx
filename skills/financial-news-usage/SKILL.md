---
name: financial-news-usage
description: 财经资讯使用痕迹垂直采集器。采集用户授权的财联社、华尔街见闻、格隆汇等财经 App/网页的阅读、收藏、订阅、搜索、自选提醒等个人动作，支持文件/目录/ZIP/直接或 ZIP 内浏览器历史副本，输出 CollectorX 事件、平台/动作/主题覆盖、字段覆盖、行为强度、来源审计、内容策略 manifest 和 FinClaw 投资分身证据包；不采公共新闻全文库。
---

# Financial News Usage Collector

## 采集边界

采集：

- 用户自己的阅读历史、收藏、订阅栏目、搜索记录、自选提醒。
- 财联社、华尔街见闻、格隆汇等财经资讯 App/网页的本地授权导出。
- 浏览器保存页面或本地归档中的用户动作指针。
- 授权 ZIP 导出包；只读取支持的导出文件和浏览器历史成员，跳过危险路径成员。
- 用户授权提供的 Chrome、Edge、Brave 等 Chromium `History` 数据库副本，以及 Safari `History.db`；支持直接文件和 ZIP 包内成员。
- 结构化字段：动作类型、平台、域名、来源应用、URL、文章标题、访问时间、访问次数、标签、证券代码、自选提醒、搜索词拆分、订阅对象、提醒条件、通知渠道、入口来源、前序页面、会话 ID、停留时长和浏览器访问方式。
- `manifest.platform_coverage` 与 `manifest.action_coverage`：记录三大财经资讯平台和 read/favorite/search/subscribe/alert 动作覆盖。
- 事件与 `manifest.usage_surface_summary` 会标注资讯使用主题：宏观政策、市场策略、行业主题、公司基本面、港美股/海外市场、风险事件、交易机会和自选提醒。
- `manifest.field_coverage`：记录标题、URL、域名、来源应用、栏目、搜索词、订阅对象、提醒条件、通知渠道、入口来源、证券代码、标签、正文预览等字段覆盖。
- `manifest.usage_surface_summary`：记录 URL、域名、来源应用、查询、标签、正文、浏览器历史、提醒、订阅和主题覆盖等可用面。
- `manifest.usage_behavior_summary`：记录搜索词拆分、订阅对象、提醒条件、通知渠道、入口来源、前序页面、会话 ID、停留时长、访问次数、输入访问次数和浏览器访问方式覆盖。
- `manifest.source_audit`：记录授权输入、缺失输入、逐文件解析结果、扩展名覆盖、跳过文件原因、ZIP 成员数量、跳过 ZIP 成员原因、文件/ZIP 成员来源、浏览器历史来源和来源应用计数、归档包数量，并声明未采集危险路径成员。
- `manifest.usage_boundary_proof`：汇总授权输入、平台/动作/主题覆盖、行为边界、浏览器历史域名过滤、ZIP 安全、内容指针和完整性声明；明确不声明完整使用历史、完整账号边界、公共新闻全文爬取、公共文章镜像或平台全站数据。
- `manifest.content_policy` 与 `manifest.evidence_policy`：声明只采用户使用痕迹，不爬公共新闻库，不把公共新闻内容当个人事实。

不采集：

- 公共新闻全文库。
- 平台全站数据。
- 非用户动作。
- cookie、token、账号密码。
- 浏览器全量历史作为投资事实；仅筛选财联社、华尔街见闻、格隆汇域名下的使用痕迹。

## CLI

```bash
python3 skills/financial-news-usage/scripts/financial_news_usage.py collect \
  --input /path/to/authorized/export-or-folder \
  --out-dir /path/to/out
```

浏览器历史库建议先由用户复制到授权目录或授权 ZIP 包，再作为 `--input` 提供；采集器只读打开，不修改原库。

输出：

- `lake/financial-news-usage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

该采集器是投资垂直通道，但仍只表达用户的信息消费/关注事实，不能替代行情、
公告、研报和新闻研究工具。

## 当前投产边界

- 已验证：JSON/CSV/HTML/Markdown/TXT/ZIP 授权导出、Chromium 浏览器历史库、Safari `History.db` 直接文件、ZIP 包内 Safari `History.db`、平台/动作/主题归一、搜索/订阅/提醒/停留/访问行为字段、字段覆盖、浏览器来源计数、逐输入来源审计、跳过原因、使用边界证明、内容/证据边界、递归敏感字段过滤。
- 待验证：真实财联社/华尔街见闻/格隆汇 App 本地缓存、账号 API、真实 Safari/macOS 历史库样本、Windows/Linux 浏览器历史真实路径、跨浏览器历史导出工具、订阅/提醒的真实字段差异。
