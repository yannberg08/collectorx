# P1 Task Calendar Platform Coverage Validation - 2026-07-08

This validation records the second productization pass for the P1 task/calendar
channel.

## Scope

Collectors:

- Generic task source: `ticktick`
- Generic calendar source: `calendar`
- Lens target: `task-calendar-investor`

This pass improves upstream generic packages. It does not promote all personal
tasks or calendar events into the investor Wiki.

## Product Changes

Calendar collector:

- Added authorized ZIP import for ICS/JSON/JSONL/CSV/TSV calendar packages.
- Added `data.source_platform` and `raw_ref.source_platform`.
- Added `manifest.platform_coverage` for:
  - `apple_calendar`
  - `google_calendar`
  - `outlook_calendar`
  - `feishu_calendar`
  - `dingtalk_calendar`
  - `wecom_calendar`
  - `tencent_meeting_calendar`
- ZIP import skips absolute paths and `..` path traversal members.

TickTick/Dida task collector:

- Added authorized ZIP import for JSON/JSONL/NDJSON task packages.
- Added `data.source_app` and `raw_ref.source_app`.
- Added `manifest.platform_coverage` for `ticktick` and `dida365`.
- Event raw snapshots now remove password/cookie/token/session/secret/
  authorization/credential-like fields.
- ZIP import skips absolute paths and `..` path traversal members.

## Fixture Validation

Validated scenarios:

- Generic ICS calendar event produces `collectorx.event.v1`.
- Google-style JSON and Outlook-style CSV calendar exports produce platform
  counts.
- Fixture containing Apple, Google, Outlook, Feishu, DingTalk, WeCom, and
  Tencent Meeting calendar records reports `all_expected_platforms_observed`.
- Calendar ZIP member `../unsafe.ics` is skipped.
- TickTick JSON task export produces `collectorx.event.v1`, strips fake token
  fields, and reports partial TickTick/Dida coverage.
- Dida ZIP task export is parsed as `dida365`.
- TickTick ZIP member `../unsafe.json` is skipped.

Commands:

```bash
.venv/bin/python skills/calendar-collector/tests/test_calendar_collector.py
.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_events.py
```

Result:

- Passed.

## Current Gate

- Authorized export/ZIP import: G1/G2 baseline.
- Real TickTick OAuth account validation: not done in this pass.
- Real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting calendar
  exports/accounts: not done in this pass.
- Investment lens false-positive backtest: still needed before production.

## Remaining Before Production Candidate

- Run TickTick OAuth on a real user account and convert real `task list`/
  `project data` output.
- Validate real ICS exports from Apple, Google, Outlook, and Chinese workplace
  calendar products.
- Validate timezone, recurrence, all-day, attendee, and reminder edge cases on
  real exports.
- Backtest `task-calendar-investor` so life tasks and unrelated meetings do not
  enter investor Wiki conclusions.
