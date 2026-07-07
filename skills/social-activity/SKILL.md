---
name: social-activity
description: 微博、B站、小红书等社交平台用户活动通用采集器。采集用户授权的关注、点赞、收藏、观看历史、评论和分享等个人活动，输出 CollectorX 事件；不抓平台全站内容，不判断投资含义。
version: 0.2.0
---

# Social Activity Collector

## 采集边界

采集：

- 用户自己的关注、点赞、收藏、观看历史、评论、分享动作。
- 创作者/账号名、创作者 ID/主页、标题、URL、域名、标签、话题、平台、动作时间、评论预览。
- 观看/点赞/评论/转发/收藏/粉丝等互动计数。
- 用户授权导出的 JSON/JSONL、CSV/TSV、Excel、HTML、Markdown、TXT 活动记录。
- 事件明确标记为 `weak_influence_signal`，需要交易、笔记、研报、会议等更强证据交叉验证。

不采集：

- 平台全站内容。
- 他人完整主页。
- 无关娱乐活动直接进入投资 Wiki。
- 社交影响源直接形成投资结论。
- cookie、token、账号密码、会话凭据。

## CLI

```bash
python3 skills/social-activity/scripts/social_activity.py collect \
  --input /path/to/authorized/social-activity-export \
  --out-dir /path/to/out
```

输出：

- `lake/social-activity/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

通用社交活动不会直接写入投资 Wiki。投资影响源筛选由
`social-investment-influence` lens 完成。即使经过 lens 筛选，也只能作为弱影响源证据，
不能单独成为投资分身的结论或建议依据。
