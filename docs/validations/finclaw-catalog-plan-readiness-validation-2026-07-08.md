# FinClaw Catalog Plan Readiness Validation - 2026-07-08

## Purpose

Verify that FinClaw can fail fast before attempting to run an incomplete or
wrong-runner collector invocation.

## Scope

- `tools/finclaw_catalog.py`
- `tools/test_finclaw_catalog.py`
- `docs/finclaw-integration-guide.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `plan --require-ready` returns status `0` only when the rendered plan is an
  ordinary command with no unresolved placeholders.
- If placeholders are missing, the plan still prints JSON, sets
  `next_action=fill_placeholders`, and exits with status `2`.
- If the collector belongs to a SoulMirror-managed runner, the plan still
  prints JSON, sets `next_action=use_soulmirror_runner`, and exits with status
  `2`.
- A ready ordinary command reports `next_action=run_command`.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py plan ths-watchlist \
  --out-dir /tmp/collectorx-out \
  --set authorized-ths-watchlist-export=/tmp/watch.csv \
  --json \
  --require-ready
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- FinClaw catalog tests passed.
- Ready `ths-watchlist` command planning returned status `0`,
  `ready_to_run=true`, and `next_action=run_command`.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This validation improves product invocation safety. It does not add new real
account validation for any collector and does not replace the package gate that
must run after collection.
