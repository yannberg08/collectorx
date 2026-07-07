# P1 Task Calendar Validation - 2026-07-08

This validation records the first productization pass for task/calendar evidence.

## TickTick Generic Collector

Collector path:

- Generic source: `ticktick` via `skills/ticktick-cli`
- Event converter: `skills/ticktick-cli/scripts/ticktick_events.py`

Result:

- Added a CollectorX event converter for user-authorized TickTick task JSON.
- Output package:
  - `lake/ticktick/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Generic task events route to `internal.productivity.tasks`.
- Manifest sets `can_claim_investment_tasks: false`.

Validation:

- Fixture task JSON converts to `collectorx.event.v1` task events.
- `task-calendar-investor` lens keeps investment research tasks and filters
  unrelated personal tasks.

Real API status:

- Local TickTick token file was not present.
- No live TickTick API data was read.

Current gate:

- Offline authorized export conversion: G1/G2 baseline.
- Lens filter: G1 baseline.
- Real account validation: blocked before G3 by missing TickTick OAuth token.

Remaining before production:

- Complete TickTick OAuth registration/authorization for a real account.
- Run bounded task/project export from the API.
- Validate recurring tasks, checklist items, completed tasks, reminders,
  project names, tags, and timezone handling.
- Build or port a generic calendar collector for non-TickTick calendars.
