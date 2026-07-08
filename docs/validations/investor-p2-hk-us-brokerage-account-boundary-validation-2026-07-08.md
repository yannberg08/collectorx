# P2 HK/US Brokerage Account Boundary Validation - 2026-07-08

This validation records the account-boundary, currency/market, and
fee/tax/margin pass for `hk-us-brokerage`.

## Scope

Collector path:

- Vertical source: `hk-us-brokerage`
- Skill: `skills/hk-us-brokerage`
- FinClaw target: strong brokerage evidence for assets, positions, executions,
  orders, cashflows, dividends, FX, margin, tax, account boundaries, and
  multi-currency portfolio context

This pass keeps the collector local and read-only. It does not log in to
brokerage accounts, collect passwords/cookies/tokens, place orders, cancel
orders, or claim a complete account boundary before real account validation.

## Product Changes

- Upgraded `hk-us-brokerage` to `0.2.4`.
- Added `manifest.account_boundary_summary` and mirrored it into
  `investor_wiki_evidence.v1.json`.
- Added `manifest.currency_market_summary` and mirrored it into evidence.
- Added `manifest.fee_tax_margin_summary` and mirrored it into evidence.
- Preserved exact authorized account IDs in account-boundary summaries because
  these are user-owned business facts needed by FinClaw Lake and the investor
  avatar.
- Kept `complete_account_boundary_claimed` false. One authorized export can be
  useful and numeric without proving it is the user's full Futu/Tiger/IBKR
  account universe.

## Fixture Validation

Validated scenarios:

- Futu-style CSV rows produce position, execution, and cashflow events with
  account `F-1`.
- IBKR-style JSON records produce asset and order events with account `U123`.
- Tiger-style nested JSON emits all seven strong-trade subtypes with account
  `T-888`.
- The manifest reports `T-888` as a full-surface account candidate while
  keeping the complete boundary claim false.
- The manifest reports USD/HKD multi-currency coverage and `USD->HKD` FX pair
  coverage.
- The manifest reports fee, tax, margin requirement, and maintenance margin
  totals by currency.
- Evidence coverage mirrors account-boundary and currency-market summaries for
  Wiki distillation.
- ZIP provenance, unsupported input skipping, unsafe ZIP member skipping,
  credential filtering, and read-only evidence policy remain covered.

Commands:

```bash
python3 /Users/pengyingan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/hk-us-brokerage
python3 -m json.tool skills/hk-us-brokerage/.collectorx.json
python3 -m json.tool collectors/finclaw-investor-catalog.json
.venv/bin/python -m py_compile skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py skills/hk-us-brokerage/scripts/hk_us_brokerage.py skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

Result:

- Passed.

## Current Gate

- Authorized CSV/JSON/Excel/ZIP export import: G1/G2 baseline+audit.
- Broker, trade-surface, field, value, source-audit, and evidence-policy
  manifests: G1/G2 baseline+audit.
- Account-boundary, currency/market, and fee/tax/margin summaries: G1/G2
  baseline+audit.
- Real Futu/Tiger/IBKR account export or read-only screen validation: not done
  in this pass.
- Complete account-boundary claim: false until real account validation passes.

## Remaining Before Production Candidate

- Validate real Futu exports or read-only screens for assets, positions,
  trades, orders, funds, dividends, FX, margin, and taxes.
- Validate real Tiger exports or read-only screens for the same surfaces.
- Validate real IBKR Activity Statement / Flex Query exports.
- Confirm Windows/macOS/Linux export paths, encodings, and ZIP behavior.
- Confirm broker-specific column maps on real samples without committing
  private account payloads.
