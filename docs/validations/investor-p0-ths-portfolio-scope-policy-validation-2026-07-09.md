# P0 Tonghuashun Portfolio Scope Policy Validation - 2026-07-09

This validation covers the P0 `ths-portfolio` collector after adding explicit
event-level user authorization scope filters before Tonghuashun strong trading
events enter the Lake. The collector remains read-only and preserves exact
business numbers for retained events.

## Scope

- Collector: `ths-portfolio`
- Version: `0.5.1`
- FinClaw route: strong trade and asset facts for the Investor Wiki, subject to
  real-device readiness and user authorization.
- Evidence surfaces: CSV trades, local Xcs historical executions, inferred
  holdings, personal metadata events, and read-only GUI asset/holding/order/
  execution/cashflow snapshots.

## Added Behavior

- `ths_query.py` accepts allow/deny filters for event kind, symbol, account,
  source, and keyword.
- Scope policy is an authorization boundary only. It does not assert investment
  relevance and does not replace research notes, reviews, or decision reasons.
- Manifest `collection_audit.ths_scope_policy` records configured filters,
  candidate event count, retained event count, filtered event count, reason
  counts, and `ths_scope_policy_filtered_all`.
- Manifest `ths_portfolio_boundary_proof.authorization_scope_boundary` exposes
  the same policy boundary to FinClaw gating.
- When every candidate event is filtered, readiness reports
  `scope_policy_filtered_all` and `can_enter_finclaw=false`.
- Scope-enabled packages filter `trades.normalized.json` and
  `estimated_holdings.json` with the same policy and omit full metadata/GUI
  sidecars to avoid bypassing the event-level authorization boundary.
- Retained trade, asset, holding, order, execution, and cashflow numbers remain
  exact; no order placement, order cancellation, credential capture, cookie
  capture, token capture, or broker-side mutation is performed.

## Fixture Coverage

- Partial-retention fixture keeps one authorized trade event while filtering
  other candidates by event kind and symbol.
- Filtered-all fixture verifies that a readable Tonghuashun input with an
  unmatched symbol policy produces `scope_policy_filtered_all`.
- Existing coverage still validates CSV parsing, local Xcs parsing, inferred
  holdings, personal metadata events, GUI table parsing, GUI gap events,
  package output, SoulMirror lake sync, and Windows code-level simulation
  fixtures.

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
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
```

## Results

- Syntax validation passed.
- Tonghuashun fixture validation passed.
- CLI help shows the new scope-policy arguments.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed.
- `git diff --check` passed.
- A sample scoped package generated from `examples/fixtures/ths-portfolio.sample.csv`
  with `--allow-symbol 600519` passed `tools/validate_collector_package.py
  --collector ths-portfolio --require-evidence`.

## Expected Manifest Signals

- `collection_audit.ths_scope_policy`
- `collection_audit.ths_scope_policy_filtered_all`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.
- `collection_readiness.scope_policy_filtered_all`
- `ths_portfolio_boundary_proof.authorization_scope_boundary`
- `ths_portfolio_boundary_proof.exact_business_numbers_preserved=true`
- `ths_portfolio_boundary_proof.read_only=true`
- `ths_portfolio_boundary_proof.order_mutation_performed=false`
- `ths_portfolio_boundary_proof.credentials_collected=false`

## Remaining Real Validation

- Run against more real Tonghuashun accounts and account states.
- Validate Windows and additional macOS Tonghuashun local paths on real devices.
- Review GUI current asset, holding, order, execution, and cashflow table
  coverage against additional unlocked trading pages.
- Backtest retained strong-trade evidence against research documents, notes,
  emails, and reviews before promotion beyond `deep-beta`.
