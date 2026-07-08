# P0 Tonghuashun Portfolio Filtered-All Gap Validation - 2026-07-09

This validation covers the P0 `ths-portfolio` collector after hardening
scope-policy filtered-all package behavior. A readable Tonghuashun input that
is completely outside the user's authorization scope now produces an explicit
gap event instead of an empty Lake file.

## Scope

- Collector: `ths-portfolio`
- Version: `0.5.2`
- FinClaw route: deep-beta strong trade and asset evidence, subject to
  user authorization and real-device readiness.
- Boundary: read-only; exact business numbers are preserved only for retained
  events; filtered-all packages do not write trade, holding, order, execution,
  cashflow, metadata, or GUI sidecar facts.

## Added Behavior

- `write_collection_package()` now converts
  `collection_audit.ths_scope_policy_filtered_all=true` into one
  `collectorx.event.v1` profile event with `data.gap=ths_scope_policy_filtered_all`.
- The gap event records candidate, retained, filtered, and reason counts but no
  security symbol, amount, position, order, execution, cashflow, account, or GUI
  business row.
- `collection_readiness.can_enter_finclaw=false` remains explicit even though
  the Lake file has a traceable gap event.
- `collection_readiness.gap_count` includes the authorization-scope gap.
- Package validation now has at least one event to inspect, so FinClaw can
  distinguish "no data retained because of authorization scope" from a broken
  or empty package.

## Fixture Coverage

- Existing filtered-all fixture now asserts:
  - `event_count=1`
  - `kind_counts.profile=1`
  - `collection_readiness.gap_count=1`
  - `can_enter_finclaw=false`
  - emitted event `data.gap=ths_scope_policy_filtered_all`
  - no retained business `symbol` field in the gap event
- Existing partial-retention fixture still verifies exact retained trade
  amount preservation and sidecar filtering.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/ths-portfolio/scripts/ths_query.py \
  skills/ths-portfolio/scripts/ths/package.py \
  skills/ths-portfolio/scripts/ths/scope.py \
  skills/ths-portfolio/tests/test_parser.py
```

```bash
.venv/bin/python skills/ths-portfolio/tests/test_parser.py
.venv/bin/python skills/ths-portfolio/scripts/ths_query.py --help
```

```bash
rm -rf /tmp/ths_scope_filtered_all_cli
.venv/bin/python skills/ths-portfolio/scripts/ths_query.py \
  --file examples/fixtures/ths-portfolio.sample.csv \
  --allow-symbol 999999 \
  --output /tmp/ths_scope_filtered_all_cli
.venv/bin/python tools/validate_collector_package.py \
  /tmp/ths_scope_filtered_all_cli \
  --collector ths-portfolio \
  --require-evidence
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
git diff --check
```

## Results

- Syntax validation passed.
- Tonghuashun fixture validation passed.
- CLI help validation passed.
- Filtered-all sample package generated from
  `examples/fixtures/ths-portfolio.sample.csv` passed
  `tools/validate_collector_package.py --collector ths-portfolio --require-evidence`.
- The sample filtered-all package produced one profile event with
  `data.gap=ths_scope_policy_filtered_all`, `event_count=1`,
  `kind_counts.profile=1`, `collection_readiness.status=scope_policy_filtered_all`,
  and `collection_readiness.can_enter_finclaw=false`.
- JSON metadata validation passed for the FinClaw catalog, invocation
  contracts, and `ths-portfolio` skill metadata.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed.

## Remaining Real Validation

- Run against more real Tonghuashun accounts and account states.
- Validate Windows and additional macOS Tonghuashun local paths on real devices.
- Review GUI current asset, holding, order, execution, and cashflow table
  coverage against additional unlocked trading pages.
- Backtest retained strong-trade evidence against research documents, notes,
  emails, and reviews before promotion beyond `deep-beta`.
