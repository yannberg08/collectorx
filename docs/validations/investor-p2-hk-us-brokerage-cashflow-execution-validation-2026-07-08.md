# P2 HK/US Brokerage Cashflow And Execution Validation - 2026-07-08

This validation records the cashflow, income, and execution-surface pass for
the `hk-us-brokerage` vertical collector.

## Scope

- Skill: `hk-us-brokerage` `0.2.6`
- Source: user-authorized read-only Futu, Tiger, and IBKR exports
- FinClaw target: exact brokerage business numbers that help the investor
  avatar reconstruct cash movement, income sources, FX behavior, order status,
  and execution discipline.

## Productization Change

The collector now writes these manifest/evidence summaries:

- `manifest.cashflow_activity_summary`;
- `manifest.income_return_summary`;
- `manifest.order_execution_summary`.

The same summaries are propagated to:

- `manifest.brokerage_boundary_proof`;
- `investor_wiki_evidence.v1.coverage_summary`.

## Validation Commands

```bash
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- Tiger nested JSON preserves deposits, dividends, FX, order status, order
  type, time-in-force, order ID, trade ID, settlement date, and fill ratio.
- Futu workbook export preserves dividend net/tax values and unrealized P/L.
- `cashflow_activity_summary` reports cashflow/dividend/FX event counts,
  deposits, net cashflow, dividend gross/net/tax, FX amounts, FX pairs,
  settlement dates, ex-dates, and pay dates.
- `income_return_summary` reports dividend net/tax by symbol, P/L by currency,
  fee drag, and tax drag.
- `order_execution_summary` reports order/execution counts, status counts,
  side counts, order type, time-in-force, order/trade IDs, settlement dates,
  fill-ratio counts, and average fill ratio.
- `brokerage_boundary_proof` includes cashflow, income, and order-execution
  boundaries while keeping complete account/brokerage-history claims false.
- `investor_wiki_evidence.v1` includes the same three summaries in
  `coverage_summary`.
- The full CollectorX regression suite passed after the change, including
  catalog validation, batch-runner validation, package/evidence validators, and
  existing P0/P1/P2 collector tests.

## Remaining Gaps

- Real Futu, Tiger, and IBKR export/read-only-screen validation.
- Broker-specific column-map validation on real statements.
- Complete account-boundary proof from real account packages.
- Multi-currency margin, tax, dividends, and FX validation on real data.
- Windows/macOS/Linux path validation for broker-specific export locations.
