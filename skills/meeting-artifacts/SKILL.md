---
name: meeting-artifacts
description: 通用会议产物采集器。采集用户授权的会议纪要、逐字稿、字幕、参会人和附件指针，支持本地文件/ZIP/平台导出，输出 CollectorX note 事件和平台覆盖 manifest；用于 feeding meeting-minutes lens，不直接判断投资含义。
---

# 会议产物采集器

本技能是 generic collector。它只采用户授权的会议产物文件或平台导出包，不直接判断哪些会议是投研会议，也不直接写投资 Wiki。

## 采什么

- 会议纪要：Markdown、TXT、HTML、JSON、JSONL、NDJSON、CSV、TSV。
- 逐字稿/字幕：VTT、SRT、JSON/JSONL/NDJSON。
- 授权 ZIP 导出包：只读取支持的会议文件，跳过危险路径成员。
- 飞书、钉钉、企业微信、腾讯会议常见授权导出字段。
- 参会人、会议标题、开始/结束时间、组织者、会议链接、来源平台、附件指针。
- 从已授权纪要/逐字稿文本中提取行动项、决策点、风险点、参会人角色线索、证券代码线索和录制引用指针。
- 平台枚举标准化：`feishu`、`dingtalk`、`wecom`、`tencent-meeting`、`local-file`。
- `manifest.platform_coverage`：记录四个 P1 会议平台的观察、缺失、事件数和 `real_account_validation`。
- `manifest.field_coverage`、`meeting_surface_summary`、`source_audit` 和
  `evidence_policy`：记录文本、参会人、参会人角色、行动项、决策点、风险点、组织者、会议链接、附件/录制引用、时长、开始/
  结束时间、ZIP 来源、每个输入文件的解析结果、ZIP 成员总数、跳过成员数量/
  原因、缺失输入/不支持扩展名文件和 generic/lens 边界。
- 可选授权范围过滤：`--allow-source-platform` / `--deny-source-platform`、
  `--allow-participant` / `--deny-participant`、`--allow-keyword` /
  `--deny-keyword`。过滤发生在事件写入 Lake 前，`manifest.source_audit.meeting_scope_policy`
  记录候选记录数、过滤数量、原因计数和 `policy_does_not_assert_investment_relevance=true`。

## 不采什么

- 不采未授权录音。
- 不读取账号密码、cookie、token、session 或会议密码。
- 不保存 cookie、token、会议密码。
- 不把平台公共会议资料当成用户个人事实。
- 不把所有会议直接写入投资分身。

## 使用

```bash
python <SKILL_DIR>/scripts/meeting_artifacts.py collect \
  --input ~/Documents/meetings \
  --allow-source-platform feishu,dingtalk \
  --allow-keyword 投委会,调研 \
  --out-dir ~/Desktop/meeting-artifacts-collect
```

输出：

```text
<out-dir>/
├── lake/meeting-artifacts/events.jsonl
├── manifest.json
└── SUMMARY.md
```

## 数据流向

`meeting-artifacts` 事件只进入通用 lake，默认路由到 `internal.collaboration.meetings`。
投资分身应把 `lake/meeting-artifacts/events.jsonl` 交给 `meeting-minutes` lens，由 lens 筛选路演、调研、投委会、复盘会议和决策点。

## 当前投产边界

- 已验证：本地授权导出文件、ZIP 包来源、ZIP 跳过成员审计、缺失输入/不支持扩展名审计、平台导出字段归一化、参会人/参会人角色/行动项/决策点/风险点/录制引用/会议链接/正文预览解析、敏感凭证字段过滤、manifest 审计字段。
- 已验证：来源平台、参会人和关键词授权范围过滤，以及所有候选会议被过滤时的 `scope_policy_filtered_all` 状态。
- 未验证：真实飞书/钉钉/企业微信/腾讯会议账号 API 拉取、录音转写授权链路、跨企业空间权限边界。
