# P2 HK/US Brokerage Export Package Validation - 2026-07-08

This validation records the second productization pass for
`hk-us-brokerage`.

## Export Package Import

Collector path:

- Vertical source: `hk-us-brokerage`
- Skill: `skills/hk-us-brokerage`

Result:

- Upgraded `hk-us-brokerage` to `0.2.0`.
- Added XLSX/XLSM workbook parsing for authorized broker statements.
- Expanded multi-section JSON packages so a single export can contain:
  - asset snapshots
  - positions
  - executions
  - orders
  - cashflows
  - dividends
  - FX
- Added stronger field coverage for investor-avatar reconstruction:
  - base/from/to currencies
  - exchange, ISIN, CUSIP
  - order type and time in force
  - gross/net amounts
  - FX amounts and exchange rate
  - settled/available cash
  - net liquidation
  - margin and maintenance margin
  - tax and withholding tax
  - realized/unrealized PnL and PnL rate
  - settlement, ex-dividend, and pay dates
- Strengthened field-name normalization, broker/status normalization, numeric
  parsing, and recursive raw-field sanitization.

Fixture validation:

- Tiger-style nested JSON statement emits all seven strong-trade subtypes.
- Futu-style XLSX workbook emits position and dividend events from separate
  sheets.
- Nested fake token data is removed from emitted raw snapshots.
- Numeric parsing handles currency marks, thousands separators, percentages,
  and parenthesized negative values.
- Manifest subtype counts include all collected brokerage surfaces.

Current gate:

- Authorized CSV/JSON/Excel export package parsing: G1/G2 baseline.
- Real Futu/Tiger/IBKR account export validation: not done.
- Real read-only screen adapter validation: not done.

Remaining before production:

- Validate real Futu exports for assets, positions, trades, orders, funds,
  dividends, margin, and FX.
- Validate real Tiger exports for the same surfaces.
- Validate real IBKR Activity Statement / Flex Query exports.
- Add broker-specific export presets once real headers are observed.
- Validate Windows/macOS/Linux path, encoding, and workbook variants.
- Keep the collector read-only: never request passwords and never place, cancel,
  or modify orders.
