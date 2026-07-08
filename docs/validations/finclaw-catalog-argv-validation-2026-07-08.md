# FinClaw Catalog Argv Validation - 2026-07-08

## Purpose

Verify that FinClaw can execute catalog plans without reparsing shell command
strings.

## Scope

- `tools/finclaw_catalog.py`
- `tools/test_finclaw_catalog.py`
- `docs/finclaw-integration-guide.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `plan --json` returns both `command` and `argv`.
- `doctor --json` returns both `command` and `argv` for every item.
- `command` is a display/audit string and may contain shell quoting.
- `argv` is the executable argument vector FinClaw should pass to the process
  runner.
- Path values with spaces are preserved as single `argv` elements.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py plan ths-watchlist \
  --out-dir '/tmp/collectorx out' \
  --set 'authorized-ths-watchlist-export=/tmp/watch list.csv' \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- FinClaw catalog tests passed.
- The sample plan kept quoted paths in `command` for display while preserving
  `/tmp/watch list.csv` and `/tmp/collectorx out` as single `argv` elements.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This validation improves process invocation reliability. It does not prove a
user has satisfied each collector preflight and does not replace post-run
package validation.
