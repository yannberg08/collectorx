# P1 Task Calendar Checklist Validation - 2026-07-08

This validation records the task checklist, recurrence, and timezone surface pass
for `ticktick`, `calendar`, and the `task-calendar-investor` lens.

## Scope

- Skill: `ticktick-cli` `0.1.11`
- Skill: `investor-source-collectors` `0.1.18`
- Collector: `ticktick`
- Lens: `task-calendar-investor`
- FinClaw target: research-task execution steps, trading-plan checklists,
  review reminders, recurrence rules, reminders, and timezone-aware planning
  evidence.

## Productization Change

TickTick/Dida task collection now preserves task execution structure:

- SoulMirror live snapshots expose `timeZone`, `repeat`, `reminders`,
  `checklistTotal`, and `checklistCompleted` at the top level while keeping raw
  task fields in `data`.
- Offline authorized imports normalize start/due/completed times and capture
  all-day, timezone, recurrence frequency, reminders, checklist items, checklist
  total/completed/pending counts, and checklist completion rate.
- `manifest.time_status_summary` reports task time-quality, invalid start/due
  ranges, duration coverage, timezone coverage, recurrence-frequency counts,
  checklist totals, completed/pending checklist items, and average checklist
  completion rate.
- `task-calendar-investor` evidence now reports checklist execution structure in
  `lens_surface_summary` and
  `task_calendar_boundary_proof.task_structure_boundary`.

## Validation Commands

```bash
.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_events.py
.venv/bin/python skills/ticktick-cli/scripts/test_collect_for_soulmirror.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile \
  skills/ticktick-cli/scripts/ticktick_events.py \
  skills/ticktick-cli/scripts/collect_for_soulmirror.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- Authorized TickTick JSON fixture emits a `collectorx.event.v1` task with
  timezone, all-day, normalized time range, recurrence frequency, reminders, and
  two checklist items.
- The TickTick manifest reports recurrence-frequency counts, checklist task
  count, total checklist items, completed/pending checklist items, and average
  checklist completion rate.
- The SoulMirror live snapshot fixture exposes timezone, repeat, reminders, and
  checklist counts without leaking the bearer token.
- The `task-calendar-investor` fixture propagates checklist execution structure
  into `lens_surface_summary`,
  `task_calendar_boundary_proof.task_structure_boundary`, and
  `investor_wiki_evidence.v1.json`.
- The lens still keeps the generic/lens boundary: TickTick and calendar provide
  task/calendar evidence, while investment relevance is asserted only after
  `task-calendar-investor` filtering.

## Remaining Gaps

- Real TickTick/Dida OAuth validation with the managed broker.
- Real recurring tasks, timezone behavior, reminders, and checklist-heavy
  trading plans from an authorized account.
- Real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting calendar
  validation.
- False-positive review against a mixed personal/work/investment task-calendar
  corpus.
