# P1 Calendar Validation - 2026-07-08

This validation records the first productization pass for the generic calendar
collector.

## Calendar Generic Collector

Collector path:

- Generic source: `calendar`
- Skill: `skills/calendar-collector`

Result:

- Added a runnable generic collector for user-authorized calendar exports.
- Supported inputs:
  - ICS
  - JSON/JSONL/NDJSON
  - CSV/TSV
- Captured event metadata:
  - title
  - start/end time
  - all-day status
  - location
  - meeting URL
  - organizer
  - attendees
  - recurrence
  - reminders
- Output package:
  - `lake/calendar/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Generic calendar events route to `internal.calendar.events`.
- Manifest sets `can_claim_investment_calendar: false`.

Fixture validation:

- ICS event with attendee, recurrence, reminder, meeting URL, and timezone is
  converted into `collectorx.event.v1`.
- JSON and CSV calendar exports are parsed into generic calendar events.
- Credential-like raw fields are removed from retained metadata.
- Missing input emits a gap event.

Current gate:

- Offline authorized export conversion: G1/G2 baseline.
- Lens filter: existing G1 baseline via `task-calendar-investor`.
- Real account validation: not done.

Remaining before production:

- Validate real Apple/Google/Outlook/Feishu calendar exports or account APIs.
- Validate recurring events, timezones, all-day events, reminders, cancelled
  events, and attendee normalization on real calendars.
- Backtest `task-calendar-investor` against real calendar/task histories to
  avoid treating private life calendar items as investment evidence.
