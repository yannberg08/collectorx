---
name: calendar-collector
description: 通用日历采集器。采集用户授权的 ICS、JSON、CSV、TSV 日历导出，输出 CollectorX calendar 事件。它只采日程原始证据，不判断是否投资相关；投资计划、财报提醒、复盘提醒由 task-calendar-investor lens 筛选。
---

# 通用日历采集器

本技能采集用户授权的日历事件，用于补齐时间安排、提醒、会议链接和参与人等通用证据。

## 采什么

- 日程标题、开始/结束时间、全天状态。
- 地点、会议链接、组织者、参与人。
- 重复规则、提醒时间。
- 用户授权导出中的日历/项目名称。

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

支持 ICS、JSON、JSONL、CSV、TSV。没有授权输入时，只输出缺口事件。

投资分身使用时，应把 `lake/calendar/events.jsonl` 交给
`task-calendar-investor` lens，由 lens 只筛交易计划、研究任务、财报日程和复盘提醒。
