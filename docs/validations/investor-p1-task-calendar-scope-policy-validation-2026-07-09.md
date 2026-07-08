# P1 Task/Calendar Scope Policy Validation - 2026-07-09

This validation records the authorization-scope pass for the generic `ticktick`
offline import helper and `calendar` collector.

## Scope

- Skills: `ticktick-cli` `0.1.12`, `calendar-collector` `0.2.2`
- Sources: `ticktick`, `calendar`
- FinClaw target: user-authorized task and calendar planning evidence before it
  is routed into the `task-calendar-investor` lens.

## Productization Change

`ticktick_events.py collect` now accepts explicit task-scope filters:

- `--allow-source-app` / `--deny-source-app`;
- `--allow-project` / `--deny-project`;
- `--allow-tag` / `--deny-tag`;
- `--allow-keyword` / `--deny-keyword`.

`calendar_query.py collect` now accepts explicit calendar-scope filters:

- `--allow-source-platform` / `--deny-source-platform`;
- `--allow-calendar` / `--deny-calendar`;
- `--allow-attendee` / `--deny-attendee`;
- `--allow-keyword` / `--deny-keyword`.

The filters are applied before downstream package/Lake output. They narrow the
user-authorized collection scope only; they do not classify a task or calendar
event as investment evidence.

The manifests now record:

- configured task/calendar allow and deny filters;
- candidate record count;
- filtered record count;
- filter reason counts;
- `policy_does_not_assert_investment_relevance=true`;
- `scope_policy_filtered_all` readiness when all candidates are outside scope.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/ticktick-cli/scripts/ticktick_events.py \
  skills/ticktick-cli/scripts/test_ticktick_events.py \
  skills/calendar-collector/scripts/calendar_query.py \
  skills/calendar-collector/scripts/calendar_collector/parser.py \
  skills/calendar-collector/tests/test_calendar_collector.py
.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_events.py
.venv/bin/python skills/calendar-collector/tests/test_calendar_collector.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Verified Behavior

- A mixed TickTick/Dida task export is filtered with:
  `--allow-source-app ticktick --allow-project 投资研究 --allow-tag 投资 --deny-keyword 买菜`.
- Only the authorized investment project task is emitted.
- A life task is excluded with `keyword_denied`.
- A Dida task is excluded with `source_app_not_allowed`.
- A mixed Google/Outlook calendar export is filtered with:
  `--allow-source-platform google --allow-calendar 投资日历 --allow-attendee analyst --deny-keyword 牙医`.
- Only the authorized investment calendar event is emitted.
- A personal appointment is excluded with `keyword_denied`.
- An Outlook event is excluded with `source_platform_not_allowed`.
- When authorized task/calendar inputs contain candidates but all are outside
  scope, package readiness reports `scope_policy_filtered_all`.

## Remaining Gaps

- FinClaw-managed TickTick OAuth Broker deployment and real-account validation.
- Real TickTick/Dida recurring task, timezone, checklist, and project/list
  validation.
- Real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting calendar
  account/export validation.
- Real-user scope-policy tuning on private project names, calendars, attendees,
  and keywords.
- `task-calendar-investor` false-positive review on broader real planning
  corpora.
