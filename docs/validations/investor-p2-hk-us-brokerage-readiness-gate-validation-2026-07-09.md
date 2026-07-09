# P2 HK/US Brokerage Readiness Gate Validation - 2026-07-09

This validation covers `hk-us-brokerage` `0.2.9`, the vertical strong-fact
collector for user-authorized read-only Futu, Tiger, and IBKR exports.

## What Changed

- Added `manifest.usable_event_count`, `manifest.brokerage_event_count`,
  `manifest.strong_trade_event_count`, and `manifest.gap_event_count`.
- Added `collection_readiness.can_enter_hk_us_brokerage_lake`,
  `can_enter_data_quality_lake`, and `can_feed_investor_wiki_evidence`.
- Routed no-input and filtered-all gap events to
  `collectorx.data_quality.collection_gaps`.
- Kept retained assets, positions, executions, orders, cashflows, dividends,
  and FX as strong brokerage evidence.
- Updated `investor_wiki_evidence.v1.json` so gap events do not contribute to
  route counts or Investor Wiki facts, while `generated_from.raw_event_count`
  and `generated_from.gap_event_count` preserve package observability.

## Fixture Coverage

- Authorized Futu-style CSV rows for positions, executions, and cashflows.
- IBKR-style JSON records for asset snapshots and orders.
- Tiger-style nested JSON statements with all seven strong-trade surfaces.
- Futu-style XLSX/XLSM workbooks.
- ZIP-packaged brokerage exports with safe-member provenance.
- Partial authorization scope retention.
- Fully filtered authorization scope gap package.
- Missing authorized input gap package.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py \
  skills/hk-us-brokerage/scripts/hk_us_brokerage.py \
  skills/hk-us-brokerage/tests/test_hk_us_brokerage.py

.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Expected Assertions

- Retained packages set `can_enter_hk_us_brokerage_lake=true`,
  `can_enter_data_quality_lake=false`, and
  `can_feed_investor_wiki_evidence=true`.
- Fully filtered and missing-input packages set
  `can_enter_hk_us_brokerage_lake=false`,
  `can_enter_data_quality_lake=true`, and
  `can_feed_investor_wiki_evidence=false`.
- Gap-only packages keep `generated_from.event_count=0`,
  `generated_from.raw_event_count=1`, and `generated_from.gap_event_count=1`.
- Gap events route only to `collectorx.data_quality.collection_gaps`.

## Result

All commands above passed on 2026-07-09. The full `test_collectors.sh` run also
passed, including the HK/US brokerage collector, shared catalog validation,
batch runner validation, project validation, and the first investor-loop smoke
test.
