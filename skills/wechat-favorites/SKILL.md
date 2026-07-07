---
name: wechat-favorites
description: 微信收藏与公众号文章通用采集器。采集用户授权导出的收藏、保存、阅读、转发文章指针和本地保存的公众号文章文件，支持文件/目录/ZIP，输出 CollectorX 事件和动作覆盖 manifest；不抓公众号公共文章库，不读取凭据。
version: 0.1.1
---

# WeChat Favorites Collector

用于 FinClaw/CollectorX 的通用个人通道采集。

## 采集边界

采集：

- 用户自己的微信收藏、保存、阅读、转发记录。
- 公众号文章标题、作者/公众号名、URL、收藏时间、标签、备注、正文预览。
- 本地保存的 HTML/Markdown/TXT 公众号文章文件。
- 授权导出的 JSON/JSONL/CSV/TSV 收藏清单。
- 授权 ZIP 导出包；只读取支持的文件，跳过危险路径成员。
- `manifest.action_coverage`：记录收藏、阅读、转发、保存文件四类动作的观察和缺失。

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
