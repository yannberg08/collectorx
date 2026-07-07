---
name: financial-news-usage
description: 财经资讯使用痕迹垂直采集器。采集用户授权的财联社、华尔街见闻、格隆汇等财经 App/网页的阅读、收藏、订阅、搜索、自选提醒等个人动作，支持文件/目录/ZIP/浏览器历史副本，输出 CollectorX 事件、平台/动作覆盖 manifest 和 FinClaw 投资分身证据包；不采公共新闻全文库。
version: 0.2.1
---

# Financial News Usage Collector

## 采集边界

采集：

- 用户自己的阅读历史、收藏、订阅栏目、搜索记录、自选提醒。
- 财联社、华尔街见闻、格隆汇等财经资讯 App/网页的本地授权导出。
- 浏览器保存页面或本地归档中的用户动作指针。
- 授权 ZIP 导出包；只读取支持的导出文件，跳过危险路径成员。
- 用户授权提供的 Chrome、Edge、Brave 等 Chromium `History` 数据库副本，以及 Safari `History.db`。
- 结构化字段：动作类型、平台、域名、来源应用、URL、文章标题、访问时间、访问次数、标签、证券代码、自选提醒。
- `manifest.platform_coverage` 与 `manifest.action_coverage`：记录三大财经资讯平台和 read/favorite/search/subscribe/alert 动作覆盖。

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

浏览器历史库建议先由用户复制到授权目录，再作为 `--input` 提供；采集器只读打开，不修改原库。

输出：

- `lake/financial-news-usage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

该采集器是投资垂直通道，但仍只表达用户的信息消费/关注事实，不能替代行情、
公告、研报和新闻研究工具。

## 当前投产边界

- 已验证：JSON/CSV/HTML/Markdown/TXT/ZIP 授权导出、Chromium 浏览器历史库、平台/动作归一、覆盖 manifest、递归敏感字段过滤。
- 待验证：真实财联社/华尔街见闻/格隆汇 App 本地缓存、账号 API、跨浏览器历史导出工具、订阅/提醒的真实字段差异。
