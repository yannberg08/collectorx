# P1 Task/Calendar Gap Package Validation - 2026-07-09

This validation records the gap-package hardening pass for the P1
task/calendar planning channel.

## Scope

- TickTick/Dida skill: `ticktick-cli` `0.1.13`
- Calendar skill: `calendar-collector` `0.2.3`
- Downstream lens: `task-calendar-investor`
- FinClaw routes:
  - TickTick live path remains SoulMirror YAML + AgentRunner + daemon-owned
    `lake/ticktick/events.jsonl`.
  - TickTick offline helper writes only `exports/ticktick/events.jsonl`.
  - Calendar writes standard CollectorX packages under `lake/calendar/events.jsonl`.

## What Changed

- TickTick/Dida offline missing input now emits one `kind=profile` gap event.
- TickTick/Dida offline scope-policy filtered-all runs now emit one
  `kind=profile` gap event instead of an empty helper event file.
- Calendar missing input now emits one validator-safe `kind=profile` gap event.
- Calendar scope-policy filtered-all runs now emit one validator-safe
  `kind=profile` gap event instead of an empty `events.jsonl`.
- TickTick manifests now separate `event_count`, `task_event_count`, and
  `gap_event_count`.
- Calendar manifests now separate `event_count`, `calendar_event_count`, and
  `gap_event_count`.

## Boundary

TickTick main collection still follows the SoulMirror contract. The skill does
not write daemon-owned Lake paths during live collection. Offline helper gap
events are data-quality records for migration/import tests and must not be
treated as task facts.

Calendar gap events route to `collectorx.data_quality.collection_gaps`. They do
not claim investment-calendar facts, complete calendar coverage, service-token
collection, or direct investor Wiki writes.

## Verification

```bash
.venv/bin/python -m py_compile \
  skills/ticktick-cli/scripts/ticktick_events.py \
  skills/ticktick-cli/scripts/test_ticktick_events.py \
  skills/calendar-collector/scripts/calendar_collector/parser.py \
  skills/calendar-collector/scripts/calendar_query.py \
  skills/calendar-collector/tests/test_calendar_collector.py

.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_events.py
.venv/bin/python skills/calendar-collector/tests/test_calendar_collector.py
```

Results:

```text
ticktick event tests passed.
calendar-collector tests passed.
```

Calendar tests validate normal, missing-input, and filtered-all packages through
`tools/validate_collector_package.py --collector calendar`. TickTick tests
validate offline helper event shape and manifest counts while preserving the
SoulMirror daemon boundary.

## Remaining Work

- Deploy and validate the FinClaw-managed TickTick OAuth broker.
- Run real TickTick/Dida recurring/timezone/checklist account validation.
- Validate real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting
  calendar exports/accounts.
- Backtest `task-calendar-investor` false positives against real task/calendar
  and trade/review history.
