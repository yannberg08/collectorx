---
name: social-activity
description: 微博、B站、小红书等社交平台用户活动通用采集器。采集用户授权的关注、点赞、收藏、观看历史、评论和分享等个人活动，支持授权 ZIP 包，输出 CollectorX 事件、弱证据策略、平台/动作/字段覆盖、影响源可用面、来源审计和内容策略 manifest；不抓平台全站内容，不判断投资含义。
---

# Social Activity Collector

## 采集边界

采集：

- 用户自己的关注、点赞、收藏、观看历史、评论、分享动作。
- 创作者/账号名、创作者 ID/主页、标题、URL、域名、标签、话题、平台、动作时间、评论预览。
- 观看/点赞/评论/转发/收藏/粉丝等互动计数。
- 用户授权导出的 JSON/JSONL、CSV/TSV、Excel、HTML、Markdown、TXT、ZIP 活动记录。
- 事件明确标记为 `weak_influence_signal`，需要交易、笔记、研报、会议等更强证据交叉验证。
- `manifest.platform_coverage`、`manifest.action_coverage`、`manifest.weak_signal_field_coverage` 和 `manifest.weak_evidence_policy`。
- `manifest.influence_surface_summary`：记录创作者、主页、URL、标签、话题、证券代码、互动计数、评论/内容预览和 section 可用面。
- `manifest.source_audit`：记录请求输入、缺失输入、逐文件解析结果、扩展名覆盖、跳过原因、ZIP 成员数量、ZIP 成员跳过原因、section/sheet 来源，并声明未采集危险路径成员。
- `manifest.content_policy`：声明不抓平台全站、不抓完整创作者主页、默认不写全文，只保留预览。

不采集：

- 平台全站内容。
- 他人完整主页。
- 无关娱乐活动直接进入投资 Wiki。
- 社交影响源直接形成投资结论。
- cookie、token、账号密码、会话凭据。

## CLI

```bash
python3 skills/social-activity/scripts/social_activity.py collect \
  --input /path/to/authorized/social-activity-export-or-zip \
  --out-dir /path/to/out
```

输出：

- `lake/social-activity/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

`manifest.source_audit` 可用于 FinClaw 判断用户授权输入是否完整、哪些文件或
ZIP 成员未进入数据湖，以及 `--limit` 是否造成截断。

通用社交活动不会直接写入投资 Wiki。投资影响源筛选由
`social-investment-influence` lens 完成。即使经过 lens 筛选，也只能作为弱影响源证据，
不能单独成为投资分身的结论或建议依据。
