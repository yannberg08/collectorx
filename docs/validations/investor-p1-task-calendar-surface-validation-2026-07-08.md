# P1 Task Calendar Surface Validation - 2026-07-08

This validation records the `task-calendar-investor` lens surface pass. No real
OAuth tokens, calendar credentials, task-account credentials, or private task
exports are committed.

## Scope

- Skill: `investor-source-collectors` `0.1.6`
- Generic upstreams: `ticktick` and `calendar`
- Lens target: `task-calendar-investor`
- FinClaw target: research tasks, trade plans, review reminders, earnings
  calendar items, research meetings, and risk checks.

## Lens Additions

`data.classification` for `task-calendar-investor` events now includes:

- `task_calendar_surfaces`
- `primary_task_calendar_surface`
- `task_calendar_surface_terms`

Supported surfaces:

- `research_task`
- `trade_plan`
- `review_reminder`
- `earnings_calendar`
- `research_meeting`
- `risk_check`

`manifest.lens_surface_summary` and
`investor_wiki_evidence.v1.json.coverage_summary.source_surface_summary` now
record:

- task/calendar surface counts;
- primary surface counts;
- missing expected surfaces;
- upstream collector counts;
- event kind counts;
- source platform/app counts;
- matched-symbol event count;
- time/due/start coverage;
- reminder and meeting URL coverage;
- project/calendar grouping coverage;
- completed and overdue task counts;
- explicit generic task/calendar lens boundary.

## Boundary

`ticktick` and `calendar` remain generic collectors. They do not write investor
Wiki facts directly. `task-calendar-investor` performs lens filtering over
user-authorized task/calendar events and still does not write the final Wiki
directly.

This pass does not claim:

- real TickTick/Dida OAuth validation;
- real Apple/Google/Outlook/Feishu calendar validation;
- recurring-event timezone validation on real devices;
- broad false-positive review on a real mixed life/work task corpus.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

New fixture coverage:

- reads upstream `collectorx.event.v1` events produced by `ticktick` and
  `calendar`;
- keeps investment tasks/calendar items and filters a life calendar item;
- classifies research-task, trade-plan, review-reminder, earnings-calendar,
  research-meeting, and risk-check surfaces;
- propagates the surface summary into both manifest and
  `finclaw.investor_wiki_evidence.v1`.

## Remaining Work

- Validate real TickTick/Dida exports or OAuth on an authorized account.
- Validate real Apple/Google/Outlook/Feishu/DingTalk/WeCom calendar exports.
- Backtest thresholds and allowlists on a real mixed personal task/calendar
  corpus.
- Validate recurring tasks, all-day events, and timezone behavior on macOS,
  Windows, and Linux.
