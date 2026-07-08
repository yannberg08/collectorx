# FinClaw Package Validation Plan - 2026-07-08

## Purpose

Verify that FinClaw can move from a collector invocation plan to a post-run
package validation gate without rebuilding validator commands in product code.

## Scope

- `tools/finclaw_catalog.py`
- `tools/test_finclaw_catalog.py`
- `docs/finclaw-integration-guide.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `plan --json` returns a `package_validation` object.
- `doctor --json` returns `package_validation` for every item.
- `package_validation.argv` points to `tools/validate_collector_package.py`.
- `package_validation.argv` includes the resolved output package directory and
  `--collector <collector-id>`.
- Vertical collectors and investor lenses include `--require-evidence`.
- Generic collectors omit `--require-evidence`.
- `package_validation.ready=false` means the output package directory is not
  known yet, so FinClaw must wait until a package path exists before running the
  gate.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py plan ths-watchlist \
  --out-dir /tmp/collectorx-out \
  --set authorized-ths-watchlist-export=/tmp/watch.csv \
  --json
.venv/bin/python tools/finclaw_catalog.py doctor \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- FinClaw catalog tests passed.
- The ready `ths-watchlist` plan emitted package-validation argv with
  `--require-evidence`.
- The P0 doctor output emitted package-validation argv for direct commands,
  lens outputs, and generic collectors with the correct evidence requirement.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This validation does not prove that a real user has satisfied each collector
preflight. It only proves that FinClaw has a machine-readable package-gate plan
once a collector output directory is known.
