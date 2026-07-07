# P2 HK/US Brokerage Coverage Validation - 2026-07-08

This validation records the third productization pass for `hk-us-brokerage`.

## Scope

Collector path:

- Vertical source: `hk-us-brokerage`
- Skill: `skills/hk-us-brokerage`
- FinClaw target: strong brokerage facts for HK/US assets, positions, orders,
  executions, cashflows, dividends, FX, margin, tax, and settlement evidence

This pass improves user-authorized local packages. It remains read-only: it
does not request login passwords, trading passwords, cookies, tokens, or place,
cancel, or modify orders.

## Product Changes

- Added authorized ZIP import for brokerage export packages.
- ZIP import supports CSV/TSV, JSON/JSONL/NDJSON, XLSX, and XLSM members.
- ZIP import skips absolute paths and `..` path traversal members.
- File/ZIP member provenance is preserved in `raw_ref.path` as
  `archive.zip::member`.
- Added `manifest.broker_coverage` for expected P2 brokers:
  - `futu`
  - `tiger`
  - `ibkr`
- Added `manifest.trade_surface_coverage` for expected strong-trade tables:
  - `asset_snapshot`
  - `position`
  - `execution`
  - `order`
  - `cashflow`
  - `dividend`
  - `fx`
- Added `manifest.field_coverage` for recommended strong numeric/business
  fields such as total assets, cash, buying power, margin, tax, settlement
  dates, gross/net amounts, FX amounts, and exchange rate.
- Added package summary lines for observed/missing brokers and trade surfaces.

## Fixture Validation

Validated scenarios:

- Futu-style CSV rows produce position, execution, and cashflow events.
- IBKR-style JSON records produce asset and order events.
- Tiger-style nested JSON statement emits all seven strong-trade subtypes.
- Futu-style XLSX workbook emits position and dividend events from separate
  sheets.
- IBKR ZIP statement emits an asset event and preserves
  `ibkr_activity.zip::statements/ibkr_asset.json`.
- Fake credential field `token` is removed from emitted raw snapshots.
- ZIP member `../unsafe.json` is skipped.
- Fixture reports all expected brokers, all expected trade surfaces, and all
  recommended strong fields observed.

Commands:

```bash
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
.venv/bin/python -m py_compile skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py skills/hk-us-brokerage/scripts/hk_us_brokerage.py
```

Result:

- Passed.

## Current Gate

- Authorized CSV/JSON/Excel/ZIP export package parsing: G1/G2 baseline.
- Broker/trade-surface/field coverage manifest: G1/G2 baseline.
- Real Futu/Tiger/IBKR account export validation: not done in this pass.
- Real read-only screen adapter validation: not done in this pass.

## Remaining Before Production Candidate

- Validate real Futu exports or read-only screens for assets, positions, trades,
  orders, funds, dividends, margin, and FX.
- Validate real Tiger exports or read-only screens for the same surfaces.
- Validate real IBKR Activity Statement / Flex Query exports.
- Add broker-specific export presets once real headers are observed.
- Validate Windows/macOS/Linux path, encoding, timezone, and workbook variants.
- Keep all adapters read-only and avoid credentials, cookies, or trading
  actions.
