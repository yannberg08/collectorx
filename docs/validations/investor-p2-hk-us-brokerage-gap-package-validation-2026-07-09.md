# P2 HK/US Brokerage Gap Package Validation - 2026-07-09

This validation covers `hk-us-brokerage` version `0.2.8`, which hardens
no-input, no-record, and filtered-all outputs into standard CollectorX packages
that FinClaw can validate without mistaking collection gaps for broker facts.

## Scope

- Collector: `hk-us-brokerage`
- FinClaw route: vertical strong-trade and asset facts for Futu, Tiger, and
  IBKR user-authorized read-only exports.
- Gap packages must not claim holdings, executions, orders, cashflows,
  dividends, FX, account-boundary completeness, or investment conclusions.

## Added Behavior

- No authorized input emits one profile gap event with
  `data.gap=hk_us_brokerage_authorized_input_missing`.
- Empty authorized inputs emit one profile gap event with
  `data.gap=hk_us_brokerage_records_empty`.
- Fully filtered authorization scope emits one profile gap event with
  `data.gap=brokerage_scope_policy_filtered_all`.
- Gap events carry non-empty `time`, `data.status`, `data.profile_type`,
  candidate/retained/filtered counts, filter reason counts, and explicit
  non-business-fact boundary flags.
- Manifest output includes `brokerage_event_count` and `gap_event_count` so the
  package can be observable while still reporting zero usable brokerage facts.
- Investor Wiki evidence counts only retained brokerage records and reports
  `strong_trade_source=false` for pure gap packages.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/hk-us-brokerage/scripts/hk_us_brokerage.py \
  skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py \
  skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
```

```bash
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
```

## Results

- Syntax validation passed.
- HK/US brokerage fixture validation passed.
- Manual filtered-all package validation passed.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed.

## Expected Signals

- Filtered-all: `data.gap=brokerage_scope_policy_filtered_all`.
- No-input: `data.gap=hk_us_brokerage_authorized_input_missing`.
- `event.kind=profile`.
- `event.time` is a non-empty string.
- `data.broker_trade_fact_claimed=false`.
- `data.holding_fact_claimed=false`.
- `data.order_or_fund_flow_claimed=false`.
- `manifest.brokerage_event_count=0`.
- `manifest.gap_event_count=1`.
- `manifest.collection_readiness.can_enter_finclaw=false`.
- Pure gap evidence has `generated_from.event_count=0` and
  `coverage_summary.strong_trade_source=false`.

## Remaining Real Validation

- Validate real Futu, Tiger, and IBKR exports or read-only screens.
- Validate broker-specific column maps, multi-currency assets, margin, tax,
  dividends, FX, and settlement fields on real accounts.
- Validate complete account-boundary proof and Windows/macOS/Linux export paths
  before claiming production readiness.
