---
name: calendar-collector
description: 通用日历采集器。采集用户授权的 ICS、JSON、CSV、TSV、ZIP 日历导出，输出 CollectorX calendar 事件和平台覆盖 manifest。它只采日程原始证据，不判断是否投资相关；投资计划、财报提醒、复盘提醒由 task-calendar-investor lens 筛选。
---

# 通用日历采集器

本技能采集用户授权的日历事件，用于补齐时间安排、提醒、会议链接和参与人等通用证据。

## 采什么

- 日程标题、开始/结束时间、全天状态。
- 地点、会议链接、组织者、参与人。
- 重复规则、提醒时间。
- 用户授权导出中的日历/项目名称。
- 来源平台：Apple/Google/Outlook/飞书/钉钉/企业微信/腾讯会议/通用导出。

## 不采什么

- 不读取邮箱、日历账号密码、cookie、token 或会话凭据。
- 不把全部私人日历直接写进投资 Wiki。
- 不判断日程是否投资相关。

## 使用

```bash
python <SKILL_DIR>/scripts/calendar_query.py collect \
  --input ~/Downloads/calendar.ics \
  --out-dir ~/Desktop/calendar-collect
```

支持 ICS、JSON、JSONL、CSV、TSV 和 ZIP 授权导出包。没有授权输入时，只输出缺口事件。

`manifest.json` 会写入 `platform_coverage`，记录 P1 日历通道预期平台、
本次实际观察平台、缺失平台、事件数和 `real_account_validation` 状态。
它也会写入 `field_coverage`、`time_surface_summary`、`source_audit` 和
`evidence_policy`，用于判断开始/结束时间、会议链接、参与人、循环、提醒、
ZIP 来源、ZIP 跳过成员数量/原因、逐文件解析结果和 generic/lens 边界。

投资分身使用时，应把 `lake/calendar/events.jsonl` 交给
`task-calendar-investor` lens，由 lens 只筛交易计划、研究任务、财报日程和复盘提醒。
