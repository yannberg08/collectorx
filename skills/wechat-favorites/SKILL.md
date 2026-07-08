---
name: wechat-favorites
description: 微信收藏与公众号文章通用采集器。采集用户授权导出的收藏、保存、阅读、转发文章指针和本地保存的公众号文章文件，支持文件/目录/ZIP，输出 CollectorX 事件、字段覆盖、行为强度、标的线索、来源审计、内容策略和动作覆盖 manifest；不抓公众号公共文章库，不读取凭据。
---

# WeChat Favorites Collector

用于 FinClaw/CollectorX 的通用个人通道采集。

## 采集边界

采集：

- 用户自己的微信收藏、保存、阅读、转发记录。
- 公众号文章标题、作者/公众号名、URL、收藏时间、标签、备注、正文预览。
- 公众号来源类型、文章 ID、收藏理由、分享对象、阅读时长、阅读进度、关联证券/基金代码和阅读/点赞/收藏/转发/评论计数。
- 本地保存的 HTML/Markdown/TXT 公众号文章文件。
- 授权导出的 JSON/JSONL/CSV/TSV 收藏清单。
- 授权 ZIP 导出包；只读取支持的文件，跳过危险路径成员。
- `manifest.action_coverage`：记录收藏、阅读、转发、保存文件四类动作的观察和缺失。
- `manifest.field_coverage`：记录标题、来源账号、URL、动作时间、标签、正文预览等字段覆盖。
- `manifest.article_surface_summary`：记录 URL、来源账号、来源账号类型、文章 ID、标签、正文、标的代码、公号文章等可用面。
- `manifest.article_behavior_summary`：记录收藏理由、分享对象、阅读时长、阅读进度、互动计数和标的线索覆盖。
- `manifest.source_audit`：记录授权输入、逐文件解析结果、扩展名覆盖、跳过文件原因、ZIP 成员数量、跳过 ZIP 成员原因、文件/ZIP 成员来源、归档包数量，并声明未采集路径穿越成员。
- `manifest.content_policy` 与 `manifest.evidence_policy`：声明通用采集器不直接写投资 Wiki，需交给 `wechat-article-favorites` lens。

不采集：

- 公众号全量历史文章库。
- 他人的阅读记录。
- 登录密码、cookie、token、数据库密钥。
- 非用户授权目录。

## CLI

```bash
python3 skills/wechat-favorites/scripts/wechat_favorites.py collect \
  --input /path/to/authorized/wechat-favorites-export \
  --out-dir /path/to/out
```

输出：

- `lake/wechat-favorites/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

通用收藏事件不会直接写入投资 Wiki。投资相关筛选由
`wechat-article-favorites` lens 完成。
