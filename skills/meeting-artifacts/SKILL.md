---
name: meeting-artifacts
description: 通用会议产物采集器。采集用户授权的会议纪要、逐字稿、字幕、参会人和附件指针，输出 CollectorX note 事件；用于 feeding meeting-minutes lens，不直接判断投资含义。
version: 0.1.0
---

# 会议产物采集器

本技能是 generic collector。它只采用户授权的会议产物文件，不直接判断哪些会议是投研会议，也不直接写投资 Wiki。

## 采什么

- 会议纪要：Markdown、TXT、JSON。
- 逐字稿/字幕：VTT、SRT、JSON/JSONL。
- 参会人、会议标题、开始时间、来源平台、附件指针。

## 不采什么

- 不采未授权录音。
- 不连接会议平台账号或读取凭证。
- 不保存 cookie、token、会议密码。
- 不把所有会议直接写入投资分身。

## 使用

```bash
python <SKILL_DIR>/scripts/meeting_artifacts.py collect \
  --input ~/Documents/meetings \
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
