# FinClaw Batch Manifest Validation - 2026-07-08

## Purpose

Verify that FinClaw can request a compact, product-executable manifest for a
batch collector run without reparsing display commands or inferring downstream
validation steps.

## Scope

- `tools/finclaw_catalog.py`
- `tools/test_finclaw_catalog.py`
- `README.md`
- `docs/finclaw-investor-collector-productization.md`
- `docs/finclaw-integration-guide.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `batch-manifest --json` returns
  `schema=collectorx.finclaw_batch_manifest.v1`.
- The manifest uses the same filters, output-root replacement, placeholder
  replacement, and upstream auto-linking behavior as `runbook`.
- `ready_steps` are ordered command steps for the product runner.
- Each ready step includes executable `argv`, dependency ids, output directory,
  expected Lake `events.jsonl`, display-only command text, and
  `post_run_validation.argv`.
- Lens steps include `input_events_jsonl` when the upstream input is visible in
  the rendered command.
- `blocked_steps` preserve `next_action`, `missing_placeholders`,
  `requires_upstream`, `user_step`, `preflight`, and `failure_state`.
- `--no-auto-link-upstream` disables automatic lens promotion and reports the
  affected lenses as blocked.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py batch-manifest \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --json
.venv/bin/python tools/finclaw_catalog.py batch-manifest \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --no-auto-link-upstream \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- FinClaw catalog tests passed.
- P0 default batch manifest reported six ready steps and six blocked steps.
- Ready steps were ordered as source collectors first, then ready investor
  lenses.
- `email-research` received
  `/tmp/collectorx-out/email/lake/email/events.jsonl` as `input_events_jsonl`.
- Ready steps included `post_run_validation.argv`.
- With `--no-auto-link-upstream`, P0 ready steps dropped to four and
  `email-research` remained blocked on upstream Lake input.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

The batch manifest is an execution contract, not an executor. It does not run
collectors, unlock accounts, infer ambiguous research inputs, or validate real
account coverage beyond the package validators emitted for each step.
