# FinClaw Catalog Doctor Validation - 2026-07-08

## Purpose

Verify that FinClaw can inspect the whole investor-collector matrix before a
run and route each collector to the correct next product action.

## Scope

- `tools/finclaw_catalog.py`
- `tools/test_finclaw_catalog.py`
- `collectors/finclaw-investor-catalog.json`
- `docs/finclaw-integration-guide.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `doctor --json` returns `collectorx.finclaw_catalog_doctor.v1`.
- `doctor --out-dir-root <dir>` replaces each `<out-dir>` with
  `<dir>/<collector-id>`.
- The report includes batch counts by `priority`, `category`, `runner`, and
  `next_action`.
- Direct missing user inputs use `next_action=fill_placeholders`.
- Lens entries waiting for upstream Lake inputs use
  `next_action=wait_for_upstream_lake`.
- SoulMirror-owned collectors use `next_action=use_soulmirror_runner`.
- `doctor --require-all-ready` exits with status `2` when any selected entry is
  not ready for ordinary command execution.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py doctor \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- FinClaw catalog tests passed.
- P0 doctor output grouped entries into `run_command`, `fill_placeholders`, and
  `wait_for_upstream_lake`.
- Lens entries reported upstream Lake requirements instead of generic missing
  file prompts.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This validation improves product orchestration. It does not add real account
validation, guarantee that a user has satisfied each preflight, or replace the
post-run CollectorX package gate.
