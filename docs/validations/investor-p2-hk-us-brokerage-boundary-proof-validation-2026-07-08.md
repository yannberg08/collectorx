# P2 HK/US Brokerage Boundary Proof Validation - 2026-07-08

This validation records the unified brokerage-boundary proof pass for
`hk-us-brokerage`.

## Scope

Collector path:

- Vertical source: `hk-us-brokerage`
- Skill: `skills/hk-us-brokerage`
- FinClaw target: strong brokerage evidence for Futu, Tiger, and IBKR assets,
  positions, executions, orders, cashflows, dividends, FX, fees, tax, margin,
  account boundaries, and multi-currency portfolio context

This pass keeps the collector local and read-only. It does not log in to broker
accounts, collect passwords/cookies/tokens, place orders, cancel orders, mutate
orders, crawl public communities, or claim a complete brokerage history before
real account validation.

## Product Changes

- Upgraded `hk-us-brokerage` to `0.2.5`.
- Added `manifest.brokerage_boundary_proof` as the single FinClaw gate for:
  authorized input presence, broker coverage, strong trade-surface coverage,
  recommended numeric/business field coverage, account IDs, asset values,
  currency/market evidence, fee/tax/margin evidence, source-boundary counts,
  Wiki flow, false claims, and completion blockers.
- Mirrored `brokerage_boundary_proof` into
  `investor_wiki_evidence.v1.json.coverage_summary`.
- Updated package `SUMMARY.md` to show the proof level and complete-boundary
  claim state.
- Preserved exact user-authorized business numbers. The proof tells FinClaw how
  complete the package is without masking assets, cash, buying power, holdings,
  executions, orders, fees, tax, margin, FX, dividends, or cashflow values.

## Fixture Validation

Validated scenarios:

- A partial Futu/IBKR export produces `weak_partial_brokerage_boundary`, enters
  FinClaw Lake, preserves business numbers, and reports missing Tiger coverage.
- A broad Futu/Tiger/IBKR package produces `strong_partial_brokerage_boundary`,
  with all expected brokers, all expected trade surfaces, all recommended
  fields, full-surface account candidates, USD/HKD asset values, FX pairs, tax,
  fees, margin, ZIP provenance, and unsafe ZIP member skipping.
- A missing input produces `no_authorized_brokerage_input`, cannot enter
  FinClaw Lake as strong evidence, and keeps the missing input in source-boundary
  audit.
- Evidence packages expose the same boundary proof for SoulMirror/FinClaw
  ingestion.
- False claims remain explicit: no complete account boundary, no complete
  brokerage history, no native broker API validation, no trading password, no
  order mutation, no public community crawl, and no direct Wiki write.

Commands:

```bash
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
.venv/bin/python -m py_compile skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py skills/hk-us-brokerage/scripts/hk_us_brokerage.py skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
python3 -m json.tool collectors/finclaw-investor-catalog.json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

Result:

- Passed.

## Current Gate

- Authorized CSV/JSON/Excel/ZIP export import: G1/G2 baseline+audit.
- Unified brokerage-boundary proof: G1/G2 baseline+audit.
- Strong trade evidence package and Investor Wiki evidence routing: G1/G2
  baseline+audit.
- Real Futu/Tiger/IBKR account export or read-only screen validation: not done
  in this pass.
- Complete account-boundary and complete brokerage-history claims: false until
  real account validation passes.

## Remaining Before Production Candidate

- Validate real Futu exports or read-only screens for assets, positions,
  trades, orders, funds, dividends, FX, margin, and taxes.
- Validate real Tiger exports or read-only screens for the same surfaces.
- Validate real IBKR Activity Statement / Flex Query exports.
- Confirm Windows/macOS/Linux export paths, encodings, and ZIP behavior.
- Confirm broker-specific column maps on real samples without committing private
  account payloads.
