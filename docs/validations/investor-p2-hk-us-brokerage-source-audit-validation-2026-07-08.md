# P2 HK/US Brokerage Source Audit Validation

Date: 2026-07-08

## Scope

This pass hardens the vertical `hk-us-brokerage` collector for user-authorized
read-only Futu, Tiger, and IBKR CSV, JSON, Excel, and ZIP export packages.

The collector remains a read-only strong-trade source:

- It emits `collectorx.event.v1` brokerage events into
  `lake/hk-us-brokerage/events.jsonl`.
- It captures the user's authorized assets, positions, executions, orders,
  cashflows, dividends, FX, margin, tax, settlement, and multi-currency amount
  fields where present.
- It does not ask for login passwords, trading passwords, cookies, or tokens.
- It does not place, cancel, or modify orders.
- It does not claim a complete brokerage boundary without real account
  validation.

## Change

Added `collect_from_inputs_with_audit` and wired collection audit into standard
package manifest output while keeping the previous `collect_from_inputs` API
compatible.

`manifest.source_audit` now records:

- requested inputs and missing inputs
- resolved input file count
- extension coverage
- parsed record count and emitted event count
- skipped file counts and skipped file reasons
- ZIP archive counts, ZIP member counts, skipped ZIP member counts, and skipped
  ZIP member reasons
- path-level parse results
- limit status
- path-safety flags for POSIX traversal and Windows drive-letter archive members

Missing input now produces both a gap event and an auditable `input_missing`
reason. ZIP limit accounting now records only the records actually emitted to
the lake.

## Validation Result

Status: `completed-baseline+audit`

Gate reached: G1/G2-partial local package audit.

Fixture validation covers:

- Futu-style CSV position, execution, and cashflow rows.
- IBKR-style JSON asset and order records.
- Tiger-style nested JSON statement with all seven strong-trade surfaces.
- Futu-style XLSX workbook with separate position and dividend sheets.
- IBKR ZIP statement import with archive provenance.
- Unsupported local file skip reasons.
- Unsafe ZIP member skipping.
- Missing input gap audit.
- ZIP limit accounting.
- Credential-like raw key filtering.
- Broker/trade-surface/field coverage, value summary, and read-only evidence
  policy.

Not claimed:

- Real Futu account export validation.
- Real Tiger account export validation.
- Real IBKR Activity Statement or Flex Query validation.
- Real read-only screen validation.
- Real Windows, macOS, or Linux export-path validation.
- Broker-specific real column-map completeness.
- Complete brokerage-boundary coverage.

Next gates:

- Validate real Futu exports or read-only screens for assets, positions, trades,
  orders, funds, dividends, FX, margin, and taxes.
- Validate real Tiger exports or read-only screens for the same surfaces.
- Validate real IBKR Activity Statement / Flex Query exports.
- Confirm broker-specific column maps on real samples without committing
  private account payloads.
- Validate Windows/macOS/Linux path, encoding, timezone, and workbook variants.
