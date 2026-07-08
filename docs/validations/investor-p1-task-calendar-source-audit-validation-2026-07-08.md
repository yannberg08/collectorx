# P1 Task Calendar Source Audit Validation - 2026-07-08

This validation records the source-audit hardening pass for P1 task and
calendar collectors. No TickTick OAuth token, calendar account credential,
cookie, app secret, private account export, or live calendar account data is
committed.

## Scope

- Collectors:
  - `ticktick-cli` event import `0.1.9`
  - `calendar-collector` `0.2.0`
- FinClaw target: generic task/calendar Lake input for
  `task-calendar-investor`.
- Supported authorized inputs:
  - TickTick/Dida JSON, JSONL, NDJSON, ZIP
  - Calendar ICS, JSON, JSONL, NDJSON, CSV, TSV, ZIP
- Explicit non-goal: generic task/calendar collectors do not directly write
  investor Wiki evidence or claim that a record is investment-related.

## Changes Validated

- `manifest.source_audit` now reports package-level input completeness:
  - `input_count`
  - `resolved_input_file_count`
  - `extension_counts`
  - `parsed_record_count`
  - `emitted_event_count`
  - `path_results`
- `manifest.source_audit` now reports ZIP member completeness:
  - `archive_member_count`
  - `archive_member_extension_counts`
  - `skipped_archive_member_count`
  - `skipped_archive_member_extension_counts`
  - `skipped_archive_member_reason_counts`
- Package summaries now surface skipped archive member count.
- Unsafe ZIP members are skipped and counted instead of silently disappearing:
  POSIX traversal, backslash traversal, and Windows drive-letter archive members
  are covered by fixture tests.
- The generic/lens boundary remains explicit: these collectors create Lake
  events and manifest audit metadata; investor Wiki evidence is still produced
  by `task-calendar-investor`.

## Fixture Proof

Validated by:

```bash
.venv/bin/python -m py_compile skills/calendar-collector/scripts/calendar_collector/parser.py skills/calendar-collector/scripts/calendar_query.py skills/calendar-collector/tests/test_calendar_collector.py skills/ticktick-cli/scripts/ticktick_events.py skills/ticktick-cli/scripts/test_ticktick_events.py
.venv/bin/python skills/calendar-collector/tests/test_calendar_collector.py
.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_events.py
```

Covered fixtures:

- ICS calendar event with meeting URL, attendee, recurrence, reminder, and
  source audit counts.
- Calendar directory containing Apple, Google, Outlook, Feishu, DingTalk,
  WeCom, and Tencent Meeting calendar fixture exports.
- Calendar ZIP package with one safe ICS member and three unsafe traversal /
  Windows drive members.
- TickTick JSON task with project, status, due/start time, recurrence,
  reminders, tags, and credential filtering.
- Dida ZIP task export with one safe JSON member and three unsafe traversal /
  Windows drive members.
- Gap-event behavior when no authorized input is provided.

## Current Gate

- `ticktick`: `baseline+audit`
- `calendar`: `baseline+audit`
- `task-calendar-investor` lens: still required for investor Wiki
  classification
- Real TickTick OAuth/API validation: still required
- Real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting calendar
  validation: still required
- Recurring task/calendar timezone backtest: still required
- False-positive review against mixed personal/work calendar data: still
  required
