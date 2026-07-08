# P0 EastMoney Portfolio Scope Policy Validation - 2026-07-09

This validation covers the P0 `eastmoney-portfolio` collector after adding
explicit event-level user authorization scope filters before EastMoney strong
trade, asset, and local investment behavior events enter the Lake. The
collector remains read-only and preserves exact business numbers for retained
events.

## Scope

- Skill: `eastmoney-portfolio`
- Version: `0.7.3`
- Lake collector id: `eastmoney-investor-v2`
- FinClaw route: production-candidate strong trade and asset facts for the
  Investor Wiki after real user authorization.
- Evidence surfaces: local watchlists, recent views, stock notes, chart
  drawings, custom panels, trade interface status logs, read-only GUI asset/
  holding/execution/order/fund-flow tables, and compatible trade detail
  exports.

## Added Behavior

- `eastmoney_query.py --collect-local` accepts allow/deny filters for event
  kind, symbol, account, source, and keyword.
- Scope policy is an authorization boundary only. It does not assert investment
  relevance and does not replace research notes, reviews, or decision reasons.
- Manifest `collection_audit.eastmoney_scope_policy` records configured
  filters, candidate event count, retained event count, filtered event count,
  reason counts, and `eastmoney_scope_policy_filtered_all`.
- Manifest `eastmoney_portfolio_boundary_proof.authorization_scope_boundary`
  exposes the same policy boundary to FinClaw gating.
- When every candidate event is filtered, the package emits an
  `eastmoney_scope_policy_filtered_all` gap event, readiness reports
  `scope_policy_filtered_all`, and `can_enter_finclaw=false`.
- Retained asset, position, execution, order, and fund-flow numbers remain
  exact; no order placement, order cancellation, transfer, credential capture,
  cookie capture, token capture, device fingerprint capture, or raw network
  payload collection is performed.
- Lake event normalization now backfills empty event `time` from
  `collected_at` so EastMoney packages satisfy the shared CollectorX package
  validator.
- EastMoney Investor Wiki evidence now uses the canonical `inv-*`
  subdimension IDs required by `collectorx.investor_wiki`.

## Fixture Coverage

- Partial-retention fixture keeps one authorized `broker_trade_execution` event
  for symbol `600519` while filtering all other candidates.
- Filtered-all fixture verifies that a readable EastMoney package with an
  unmatched symbol policy emits an explicit filtered-all gap event and marks
  readiness `scope_policy_filtered_all`.
- Existing coverage still validates Windows and Linux code-level path
  simulation, strong trade export parsing, unlocked/locked GUI state parsing,
  copied position table parsing, business-number preservation, package output,
  investor evidence, and validation status.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/eastmoney-portfolio/scripts/eastmoney_query.py \
  skills/eastmoney-portfolio/scripts/eastmoney/local_collect.py \
  skills/eastmoney-portfolio/scripts/eastmoney/scope.py \
  skills/eastmoney-portfolio/tests/test_local_collect.py
```

```bash
.venv/bin/python skills/eastmoney-portfolio/tests/test_local_collect.py
.venv/bin/python skills/eastmoney-portfolio/tests/test_parser.py
.venv/bin/python skills/eastmoney-portfolio/scripts/eastmoney_query.py --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
```

## Results

- Syntax validation passed.
- EastMoney local collector fixture validation passed.
- EastMoney parser validation passed.
- CLI help shows the new scope-policy arguments.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed.
- `git diff --check` passed.
- Partial scoped sample package generated from the Windows/trade-export
  fixtures with `--allow-event-kind broker_trade_execution --allow-symbol
  600519` passed `tools/validate_collector_package.py --collector
  eastmoney-investor-v2 --require-evidence`.
- Filtered-all scoped sample package generated with `--allow-symbol 999999`
  passed the same package validator and reported
  `collection_readiness.status=scope_policy_filtered_all`.

## Expected Manifest Signals

- `collection_audit.eastmoney_scope_policy`
- `collection_audit.eastmoney_scope_policy_filtered_all`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.
- `collection_readiness.scope_policy_filtered_all`
- `eastmoney_portfolio_boundary_proof.authorization_scope_boundary`
- `eastmoney_portfolio_boundary_proof.exact_business_numbers_preserved=true`
- `eastmoney_portfolio_boundary_proof.read_only=true`
- `eastmoney_portfolio_boundary_proof.order_mutation_performed=false`
- `eastmoney_portfolio_boundary_proof.credentials_collected=false`

## Remaining Real Validation

- Re-run on additional unlocked EastMoney accounts and account states.
- Validate Windows and Linux real-device local paths beyond current code-level
  simulations.
- Review default scope-policy presets for all-events, strong-trade-only,
  symbol-limited, account-limited, and research-behavior-only captures.
- Backtest retained strong-trade evidence against research documents, notes,
  emails, and reviews before broadening product defaults.
