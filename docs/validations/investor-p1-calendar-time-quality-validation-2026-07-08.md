# P1 Calendar Time Quality Validation - 2026-07-08

## Scope

This validation hardens the P1 task/calendar chain for FinClaw investor-avatar
planning evidence.

Covered collectors:

- `calendar`
- `task-calendar-investor`

## What Changed

- Upgraded `calendar-collector` to `0.2.1`.
- Added event-level calendar time-quality fields:
  - `has_time_range`
  - `time_order_valid`
  - `duration_minutes`
  - `is_multi_day`
- Expanded `manifest.time_surface_summary` with:
  - missing start/end counts
  - duration coverage
  - min/max/average duration
  - invalid time ranges
  - all-day and multi-day counts
  - missing meeting-link and reminder counts
  - same-calendar conflict summary
- Conflict samples use event ids only, not event titles, so the manifest can
  show quality issues without adding extra private text.
- Added lens-level propagation in `task-calendar-investor`:
  - `events_with_duration_minutes`
  - `multi_day_event_count`
  - `invalid_time_range_count`

## Validation Commands

```bash
.venv/bin/python skills/calendar-collector/tests/test_calendar_collector.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile \
  skills/calendar-collector/scripts/calendar_collector/parser.py \
  skills/calendar-collector/scripts/calendar_query.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py
git diff --check
```

## Fixture Coverage

- ICS event with start/end time and one-hour duration.
- CSV investment calendar package with overlapping events in the same calendar.
- Invalid event where end time is earlier than start time.
- Cross-night event that is marked as multi-day.
- `task-calendar-investor` lens propagation into manifest and
  `investor_wiki_evidence.v1.json`.

## Result

All validation commands passed.

The collector remains `baseline+audit`.

FinClaw can now inspect whether planning and review evidence has usable timing
before writing to the investor Wiki. This does not claim real Apple Calendar,
Google Calendar, Outlook, Feishu, DingTalk, WeCom, Tencent Meeting, TickTick, or
Dida365 account validation.
