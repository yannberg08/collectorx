# FinClaw Batch Runbook Validation - 2026-07-08

## Purpose

Verify that FinClaw can turn catalog readiness into a staged batch execution
plan instead of inferring ordering from scattered collector plans.

## Scope

- `tools/finclaw_catalog.py`
- `tools/test_finclaw_catalog.py`
- `docs/finclaw-integration-guide.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `runbook --json` returns `collectorx.finclaw_runbook.v1`.
- Runbook items reuse the doctor item shape, including `argv` and
  `package_validation`.
- `ready_collectors` contains source collectors that can run now.
- `ready_lenses` contains lenses whose upstream Lake paths have been supplied.
- `needs_upstream_lake` contains lenses waiting for upstream Lake events.
- `needs_user_input` contains collectors waiting for authorized files, folders,
  accounts, or placeholder values.
- `soulmirror_runner` contains collectors that must be delegated to
  SoulMirror-managed execution.
- By default, deterministic `<upstream-id-events-jsonl>` placeholders are
  auto-linked from ready upstream package paths.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py runbook \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --json
.venv/bin/python tools/finclaw_catalog.py runbook \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --set email-events-jsonl=/tmp/lake/email/events.jsonl \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- FinClaw catalog tests passed.
- P0 default runbook grouped four entries into `ready_collectors`, two into
  `ready_lenses`, one into `needs_upstream_lake`, and five into
  `needs_user_input`.
- Supplying `email-events-jsonl` explicitly kept `email-research` in
  `ready_lenses` using the user-provided Lake path.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This validation improves product orchestration. It does not prove that any
collector preflight is satisfied on a real account or device.
