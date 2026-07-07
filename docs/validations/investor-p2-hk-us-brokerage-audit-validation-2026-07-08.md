# P2 HK/US Brokerage Audit Validation - 2026-07-08

This validation records the audit/value pass for `hk-us-brokerage`.

## Scope

Collector path:

- Vertical source: `hk-us-brokerage`
- Skill: `skills/hk-us-brokerage`
- FinClaw target: strong brokerage evidence for assets, holdings, executions,
  orders, cashflows, dividends, and FX

This pass strengthens user-authorized local export packages. It does not log in
to brokerage accounts, does not collect passwords/cookies/tokens, and never
places, cancels, or modifies orders.

## Product Changes

- Preserved ZIP `source_archive` and `archive_member` in `raw_ref`.
- Added `manifest.strong_trade_surface_summary` for strong trade subtype
  counts plus account, currency, symbol, amount, fee, tax, margin, and PnL
  availability.
- Added `manifest.asset_value_summary` with reported total assets, cash, and
  buying power by currency, plus broker/currency observation.
- Added `manifest.source_audit` for source refs, ZIP member events, archive
  count, source section/sheet events, and unsafe ZIP collection status.
- Added `manifest.evidence_policy` to make the read-only strong-trade boundary
  explicit.
- Hardened ZIP path handling for POSIX traversal, Windows traversal, and
  Windows drive-letter members.

## Fixture Validation

Validated scenarios:

- Futu-style CSV rows produce position, execution, and cashflow events.
- IBKR-style JSON records produce asset and order events.
- Tiger-style nested JSON statement emits all seven strong-trade subtypes.
- Futu-style XLSX workbook emits position and dividend events from separate
  sheets.
- IBKR ZIP statement emits an asset event with archive provenance.
- ZIP members `../unsafe.json`, `..\\windows-traversal.json`, and
  `C:\\unsafe.json` are skipped.
- Manifest reports all expected brokers, all expected strong trade surfaces,
  all recommended strong fields, strong trade surface summary, asset value
  summary, source audit, and read-only evidence policy.

Commands:

```bash
.venv/bin/python -m py_compile skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py skills/hk-us-brokerage/scripts/hk_us_brokerage.py skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
```

Result:

- Passed.

## Current Gate

- Authorized local CSV/JSON/Excel/ZIP import: G1/G2 baseline+audit.
- Strong trade subtype coverage manifest: G1/G2 baseline+audit.
- Asset value and source audit manifest: G1/G2 baseline+audit.
- Real Futu/Tiger/IBKR account export validation: not done in this pass.
- Complete brokerage boundary claim: false until real account validation passes.

## Remaining Before Production Candidate

- Validate real Futu exports or read-only screens for assets, positions, trades,
  orders, funds, dividends, FX, margin, and taxes.
- Validate real Tiger exports or read-only screens for the same surfaces.
- Validate real IBKR Activity Statement / Flex Query exports.
- Confirm Windows/macOS/Linux export paths and encodings.
- Confirm broker-specific column maps on real samples without committing
  private account payloads.
