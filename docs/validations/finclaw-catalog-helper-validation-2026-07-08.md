# FinClaw Catalog Helper Validation - 2026-07-08

This validation records the product-side catalog helper for FinClaw investor
collector discovery and invocation planning.

## Scope

- Provide a stable CLI that merges the FinClaw investor catalog with invocation
  contracts.
- Let product runners list collectors, inspect a single collector, and render a
  command plan with unresolved-placeholder reporting.
- Keep SoulMirror-owned collectors distinct from ordinary shell commands.

## Code Changes

- Added `tools/finclaw_catalog.py`.
- Added `tools/test_finclaw_catalog.py`.
- Wired the helper CLI help and test into `tools/validate_project.py`.

## Covered Behaviors

- `list --json` returns merged catalog and invocation-contract summaries.
- `show <collector> --json` returns the catalog entry plus invocation contract.
- `plan <collector> --out-dir ... --set placeholder=value --json` replaces
  command placeholders and reports whether the command is ready to run.
- Lens entries preserve upstream requirements.
- `ticktick` reports `runner=soulmirror` and is not marked as an ordinary
  ready-to-run command.

## Validation

```bash
.venv/bin/python tools/finclaw_catalog.py --help
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py plan ths-watchlist \
  --out-dir /tmp/out \
  --set authorized-ths-watchlist-export=/tmp/watch.csv \
  --json
```

Result:

- Helper CLI help passed.
- Catalog helper tests passed.
- The example `ths-watchlist` plan produced a ready command with no unresolved
  placeholders.

## Non-Goals

- The helper does not execute collectors.
- The helper does not validate collector output packages.
- No collector readiness was promoted and no new real-account validation is
  claimed.
