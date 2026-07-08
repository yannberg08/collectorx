# P1 Task Calendar Boundary Validation - 2026-07-08

This validation records the boundary-proof pass for the
`task-calendar-investor` lens.

## Scope

- Skill: `investor-source-collectors` `0.1.13`
- Lens: `task-calendar-investor`
- Upstream generic collectors: `ticktick`, `calendar`
- FinClaw target: trading plans, research tasks, review reminders, earnings
  calendar items, research meetings, risk checks, and execution-discipline
  timing evidence.

## Productization Change

`manifest.json` now includes `task_calendar_boundary_proof`.

The proof records:

- authorized input counts and requested inputs;
- candidate, matched, and filtered record counts;
- upstream collector, event-kind, and source app/platform counts;
- time, due/start, reminder, meeting URL, project/calendar, duration,
  multi-day, invalid-time, completed-task, and overdue-task coverage;
- the same task-calendar surface summary already propagated to Investor Wiki
  evidence coverage.

The proof explicitly keeps these boundaries false:

- complete task list claimed;
- complete calendar claimed;
- complete task/calendar context claimed;
- direct task/calendar reconnect;
- direct final Wiki writes.

## Validation Commands

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/tests/test_investor_sources.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- The mixed task/calendar fixture reads five upstream candidates.
- The lens keeps four investment task/calendar events and filters one life
  calendar item.
- `task_calendar_boundary_proof.proof_level` is
  `authorized_task_calendar_with_time_quality`.
- The proof reports four events, five candidates, four matched events, and one
  filtered candidate.
- The proof reports upstream counts for `ticktick` and `calendar`, source
  platform counts for `ticktick` and `feishu_calendar`, reminder coverage,
  meeting-link coverage, duration coverage, and zero invalid time ranges.
- The proof does not claim a complete task list, complete calendar, complete
  task/calendar context, direct reconnect, or direct Wiki writes.

## Remaining Gaps

- Real TickTick/Dida OAuth validation with the managed broker.
- Real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting calendar
  validation.
- Recurring task/calendar timezone behavior on real accounts and devices.
- False-positive review against a mixed personal/work/investment task-calendar
  corpus.
