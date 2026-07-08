# FinClaw Batch Runner Validation - 2026-07-08

## Purpose

Verify that FinClaw can dry-run or execute a CollectorX batch manifest through
a controlled runner that uses executable argv arrays and post-run package
validation commands.

## Scope

- `tools/run_finclaw_batch.py`
- `tools/test_finclaw_batch_runner.py`
- `tools/validate_project.py`
- `README.md`
- `docs/finclaw-integration-guide.md`
- `docs/finclaw-investor-collector-productization.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- The runner emits `schema=collectorx.finclaw_batch_run_report.v1`.
- The default mode is dry-run and does not execute ready-step commands.
- `--execute` is required before any collector command runs.
- The runner executes only `ready_steps[*].argv`, never display command text.
- After a successful ready step, the runner executes
  `ready_steps[*].post_run_validation.argv` unless `--skip-validation` is used.
- A successful ready step without a ready post-run validation command is
  treated as a validation failure.
- A failed collector command or failed package validation stops the batch unless
  `--continue-on-error` is supplied.
- `--require-all-ready` exits with status `2` when blocked steps remain.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/run_finclaw_batch.py --help
.venv/bin/python tools/run_finclaw_batch.py \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- Batch runner tests passed.
- Runner help rendered successfully.
- P0 dry-run reported six ready steps, six blocked steps, and zero attempted
  steps.
- Fixture execution test wrote a valid CollectorX package and the runner ran
  `tools/validate_collector_package.py` successfully.
- Failed-step fixture returned a failed run report and skipped post-run
  validation for that step.
- Missing post-run validation fixture returned `validation_not_ready`.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

The runner is a controlled execution loop, not an authorization broker. It does
not unlock trading accounts, obtain OAuth tokens, infer missing user files, or
turn baseline collectors into production candidates without real user/device
validation.
