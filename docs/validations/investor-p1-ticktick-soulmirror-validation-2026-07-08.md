# P1 TickTick SoulMirror Validation - 2026-07-08

## Scope

This pass aligns the TickTick/Dida collector with the SoulMirror collector
runtime model: collector YAML, AgentRunner prompt, and a skill entrypoint that
returns one JSON snapshot array.

## Changes

- Updated `collectors/generic/ticktick.yaml` to `apiVersion: soulmirror/v1`.
- Added `collect_for_soulmirror.py` as the live collector entrypoint.
- Added managed OAuth support through `auth.py connect` and
  `TICKTICK_OAUTH_BROKER_URL`.
- Updated the Cloudflare Worker template for a FinClaw-owned OAuth Broker.
- Added `task collect-all` to the management CLI.
- Kept `ticktick_events.py` as an offline authorized export helper and changed
  its `--out-dir` event path to `exports/ticktick/events.jsonl` so it does not
  collide with daemon-owned `lake/ticktick/events.jsonl`.
- Updated FinClaw catalog/docs to describe the live path and remaining real
  account validation gap.
- Hardened the AgentRunner prompt and skill instructions so collection never
  starts OAuth and never writes a structured auth error into the
  snapshot/result file.

## Validation Coverage

- Missing auth returns a non-zero exit and structured
  `ticktick_auth_required` error on stderr.
- Missing auth does not return `[]`.
- Authorized fake OpenAPI validation covers:
  - project list lookup
  - active task collection
  - completed task collection
  - completed limit forwarding
  - project-name mapping
  - inbox fallback
  - duplicate task id dedupe
  - no token leakage in stdout snapshot
- Offline JSON/ZIP export conversion remains tested with gap and ZIP safety
  cases.
- Completed-task OpenAPI requests use the documented `startDate`/`endDate`
  fields and apply `limit` locally instead of sending a non-standard request
  field.
- The test suite now reads `collectors/generic/ticktick.yaml` and
  `skills/ticktick-cli/SKILL.md` to lock the no-OAuth-during-collection and
  no-error-object-in-result-file contract.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/ticktick-cli/scripts/collect_for_soulmirror.py \
  skills/ticktick-cli/scripts/test_collect_for_soulmirror.py \
  skills/ticktick-cli/scripts/auth.py \
  skills/ticktick-cli/scripts/ticktick_cli.py \
  skills/ticktick-cli/scripts/ticktick_api_client.py \
  skills/ticktick-cli/scripts/ticktick_events.py
```

```bash
.venv/bin/python skills/ticktick-cli/scripts/test_collect_for_soulmirror.py
.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_api_client.py
.venv/bin/python skills/ticktick-cli/scripts/test_ticktick_events.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

Expected result: all commands pass.

## Boundaries

- This is not a claim that a real TickTick account was collected in this
  environment.
- The managed OAuth Broker still needs deployment on a FinClaw-owned domain.
- Recurring-task, timezone, and real account backtests remain required before
  raising the TickTick path beyond `baseline+audit`.
