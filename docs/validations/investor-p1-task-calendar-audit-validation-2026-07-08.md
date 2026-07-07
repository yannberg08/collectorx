# P1 Task Calendar Audit Validation - 2026-07-08

This validation records the audit/time-surface pass for `ticktick_events.py`
and `calendar-collector`. No OAuth token, app secret, cookie, private account
payload, or live account export is committed.

## Scope

- Collectors: `ticktick-cli` `0.1.8` event import path and
  `calendar-collector` `0.1.2`
- FinClaw target: generic task/calendar Lake input for the
  `task-calendar-investor` lens.
- Supported authorized inputs:
  - TickTick/Dida JSON, JSONL, NDJSON, and ZIP task exports
  - ICS, JSON, JSONL, NDJSON, CSV, TSV, and ZIP calendar exports
- Explicit non-goal: generic tasks/calendars do not directly write investor
  Wiki evidence or claim that a task/calendar item is investment-related.

## Changes Validated

- TickTick/Dida events now include:
  - content length
  - completion status
  - overdue status
  - recurrence
  - reminders
  - ZIP `source_archive` and `archive_member` references
- Calendar events now include:
  - description length and `has_description`
  - meeting URL / attendees / recurrence / reminders coverage
  - ZIP `source_archive` and `archive_member` references
- Task manifest now includes:
  - `field_coverage`
  - `time_status_summary`
  - `source_audit`
  - generic-collector `evidence_policy`
- Calendar manifest now includes:
  - `field_coverage`
  - `time_surface_summary`
  - `source_audit`
  - generic-collector `evidence_policy`
- ZIP import skips unsafe POSIX traversal, backslash traversal, absolute paths,
  and Windows drive-letter archive members.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_events.py
.venv/bin/python skills/calendar-collector/tests/test_calendar_collector.py
```

Covered fixtures:

- TickTick-style JSON task with due time, start time, priority, recurrence,
  reminder, tag, and credential-like raw key sanitization.
- Dida ZIP task package with completed task and unsafe ZIP members.
- ICS event with meeting URL, attendee, recurrence, reminder, and description.
- Mixed Google/Outlook JSON/CSV calendar exports.
- All expected P1 calendar platforms and ZIP member provenance.

The test commands passed in this validation pass.

## Current Gate

- `ticktick_events.py`: `baseline+audit`
- `calendar-collector`: `baseline+audit`
- `task-calendar-investor` lens: still required for investor Wiki
  classification
- Real TickTick OAuth validation: still required
- Real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent calendar validation:
  still required
- Recurring-task/timezone backtest on real data: still required
- False-positive review against real mixed personal tasks/calendars: still
  required
