# FinClaw Package Ingestion Gate Validation - 2026-07-08

## Scope

This pass adds a package-level validation gate for FinClaw job runners. The goal
is to verify a collector output directory before it enters durable Lake storage
or investor Wiki distillation.

## Changes

- Added `tools/validate_collector_package.py`.
- Added `tools/test_collector_package_validator.py`.
- Wired the validator CLI help and tests into `tools/validate_project.py`.
- Updated `tools/run_first_investor_loop.py` to write `manifest.json`.
- Added first-loop package validation with `--require-evidence`.
- Updated FinClaw integration and productization docs to require the package
  gate before Wiki distillation.

## Validation Coverage

The package validator checks:

- package directory exists
- `manifest.json` exists and is valid JSON
- `lake/<collector-id>/events.jsonl` exists
- events are valid JSONL
- events use `collectorx.event.v1`
- required event fields are present
- `privacy.sensitive` and `privacy.local_only` are booleans
- `data` and `raw_ref` are objects
- collector id matches the requested collector when supplied
- optional `investor_wiki_evidence.v1.json` passes the shared Investor Wiki
  contract

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  tools/validate_collector_package.py \
  tools/test_collector_package_validator.py \
  tools/run_first_investor_loop.py \
  tools/validate_project.py
```

```bash
.venv/bin/python tools/test_collector_package_validator.py
.venv/bin/python tools/validate_collector_package.py --help
PYTHON=.venv/bin/python bash test_collectors.sh
```

Expected result: all commands pass.

## Boundaries

- This is a product/job-runner gate, not a new collector.
- It does not claim real-account validation for any collector.
- It does not override collector-specific manifests; it checks that package
  shape and evidence contracts are safe enough for the next pipeline step.
