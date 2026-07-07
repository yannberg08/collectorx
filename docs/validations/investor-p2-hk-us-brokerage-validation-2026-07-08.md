# P2 HK/US Brokerage Validation - 2026-07-08

This validation records the first productization pass for HK/US brokerage
strong-trade evidence.

## HK/US Brokerage Collector

Collector path:

- Vertical source: `hk-us-brokerage`
- Skill: `skills/hk-us-brokerage`

Result:

- Added a runnable vertical collector for user-authorized read-only brokerage
  exports.
- Target brokers: Futu/Moomoo, Tiger, IBKR.
- Supported inputs: CSV, TSV, JSON, JSONL/NDJSON.
- Captured strong-trade surfaces:
  - asset snapshots
  - positions
  - executions
  - orders
  - cashflows
  - dividends
  - FX
- Output package:
  - `lake/hk-us-brokerage/events.jsonl`
  - `manifest.json`
  - `investor_wiki_evidence.v1.json`
  - `SUMMARY.md`
- Manifest sets `can_claim_complete_hk_us_trade_boundary: false`.

Fixture validation:

- Futu-style position, execution, and cashflow rows are converted to
  `collectorx.event.v1`.
- IBKR-style asset and order records are converted to `collectorx.event.v1`.
- Numeric business fields are preserved: quantity, price, market value, amount,
  fees, cash, total assets, buying power.
- Evidence marks `strong_trade_source: true` while still avoiding a complete
  boundary claim from partial exports.

Real local candidate validation:

- Candidate files found: 5.
- No valid CSV/TSV/JSON/JSONL read-only brokerage export was found.
- Collector emitted 1 gap event.
- Manifest status: `needs_hk_us_brokerage_authorized_input`.
- `can_enter_finclaw: false` for this run.

Current gate:

- Fixture/local export parser: G1.
- Real Futu/Tiger/IBKR export or read-only screen validation: not done.

Remaining before production:

- Validate real Futu exports for assets, positions, trades, orders, funds,
  dividends, and FX.
- Validate real Tiger exports for the same surfaces.
- Validate real IBKR Activity Statement / Flex Query exports.
- Add broker-specific column maps and currency/market normalization.
- Add Windows/macOS/Linux path and encoding tests for exported reports.
- Keep the collector read-only: never request passwords and never place, cancel,
  or modify orders.
