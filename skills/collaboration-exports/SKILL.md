---
name: collaboration-exports
description: 钉钉/企业微信通用协作导出采集器。采集用户授权的本地导出中的消息、会话、联系人、文件指针、会议指针，输出 dingtalk 或 wecom 的 CollectorX 事件和 filtered-all/no-input gap package；不直接判断投资含义。
---

# Collaboration Exports Collector

## 采集边界

采集：

- 钉钉、企业微信用户授权导出的消息、会话、联系人、文件指针、会议/纪要指针。
- 发送人、会话、时间、正文预览、文件名、会议链接、参与人、标签等协作元数据。
- JSON/JSONL/NDJSON、CSV/TSV、HTML、Markdown、TXT、ZIP 本地授权导出。
- `manifest.field_coverage`、`collaboration_surface_summary`、`source_audit`
  和 `evidence_policy`，用于判断消息/会议/文件/联系人覆盖、每个输入文件的
  解析结果、ZIP 成员总数、跳过成员数量/原因、ZIP 来源和 generic/lens 边界。
- 可选授权范围过滤：来源平台、记录类型、群聊/会话、发送人/接收人、参会人和关键词。
  过滤发生在事件写入 Lake 前，`manifest.source_audit.collaboration_scope_policy`
  记录候选记录数、过滤数量、原因计数和 `policy_does_not_assert_investment_relevance=true`。
- 授权输入缺失、可读记录为空或授权范围过滤为空时，输出 `profile` gap 事件，
  并在 manifest 中区分 `collaboration_event_count` 和 `gap_event_count`；
  gap 只进入 `collectorx.data_quality.collection_gaps`。

不采集：

- 登录密码、cookie、token、session、企业应用 secret。
- 未授权企业空间数据。
- 文件正文批量镜像。
- 投资含义判断。

## CLI

```bash
python3 skills/collaboration-exports/scripts/collaboration_exports.py collect \
  --platform dingtalk \
  --input /path/to/authorized/dingtalk-export \
  --allow-chat 投研讨论群 \
  --allow-sender 研究员A \
  --deny-keyword 买菜 \
  --out-dir /path/to/out
```

```bash
python3 skills/collaboration-exports/scripts/collaboration_exports.py collect \
  --platform wecom \
  --input /path/to/authorized/wecom-export \
  --out-dir /path/to/out
```

输出：

- `lake/dingtalk/events.jsonl` 或 `lake/wecom/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

这些事件只进入通用协作 lake。投资讨论、调研协作、会议纪要应由
`wechat-investment-dialogue`、`meeting-minutes`、`research-documents` 等 lens
或后续协作 lens 进行投资筛选。
