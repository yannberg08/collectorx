---
name: financial-news-usage
description: 财经资讯使用痕迹垂直采集器。采集用户授权的财联社、华尔街见闻、格隆汇等财经 App/网页的阅读、收藏、订阅、搜索、自选提醒等个人动作，输出 CollectorX 事件和 FinClaw 投资分身证据包；不采公共新闻全文库。
---

# Financial News Usage Collector

## 采集边界

采集：

- 用户自己的阅读历史、收藏、订阅栏目、搜索记录、自选提醒。
- 财联社、华尔街见闻、格隆汇等财经资讯 App/网页的本地授权导出。
- 浏览器保存页面或本地归档中的用户动作指针。

不采集：

- 公共新闻全文库。
- 平台全站数据。
- 非用户动作。
- cookie、token、账号密码。

## CLI

```bash
python3 skills/financial-news-usage/scripts/financial_news_usage.py collect \
  --input /path/to/authorized/export-or-folder \
  --out-dir /path/to/out
```

输出：

- `lake/financial-news-usage/events.jsonl`
- `manifest.json`
- `investor_wiki_evidence.v1.json`
- `SUMMARY.md`

该采集器是投资垂直通道，但仍只表达用户的信息消费/关注事实，不能替代行情、
公告、研报和新闻研究工具。
