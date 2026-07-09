# P1 Financial News Readiness Gate Validation - 2026-07-09

This validation covers `financial-news-usage` `0.3.0`, the vertical collector
for user-authorized CLS, WallstreetCN, and Gelonghui usage traces.

## What Changed

- Added `manifest.usable_event_count`, `manifest.usage_event_count`, and
  `manifest.gap_event_count`.
- Added `collection_readiness.can_enter_financial_news_usage_lake`,
  `can_enter_data_quality_lake`, and `can_feed_investor_wiki_evidence`.
- Routed no-input and filtered-all gap events to
  `collectorx.data_quality.collection_gaps`.
- Kept retained read/favorite/search/subscribe/alert events as personal
  information-usage evidence only, not public-news facts.
- Updated `investor_wiki_evidence.v1.json` so gap events do not contribute to
  route counts or Investor Wiki facts, while `generated_from.raw_event_count`
  and `generated_from.gap_event_count` preserve package observability.

## Fixture Coverage

- Authorized JSON/HTML/ZIP usage package with all expected platforms and
  actions.
- Direct Chromium browser-history copy.
- Direct Safari `History.db` and ZIP-packaged Safari history member.
- ZIP limit behavior.
- Partial authorization scope retention.
- Fully filtered authorization scope gap package.
- Missing authorized input gap package.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/financial-news-usage/scripts/financial_news_usage/parser.py \
  skills/financial-news-usage/scripts/financial_news_usage.py \
  skills/financial-news-usage/tests/test_financial_news_usage.py

.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Expected Assertions

- Retained packages set
  `can_enter_financial_news_usage_lake=true`,
  `can_enter_data_quality_lake=false`, and
  `can_feed_investor_wiki_evidence=true`.
- Fully filtered and missing-input packages set
  `can_enter_financial_news_usage_lake=false`,
  `can_enter_data_quality_lake=true`, and
  `can_feed_investor_wiki_evidence=false`.
- Gap-only packages keep `generated_from.event_count=0`,
  `generated_from.raw_event_count=1`, and `generated_from.gap_event_count=1`.
- Gap events route only to `collectorx.data_quality.collection_gaps`.

## Result

All commands above passed on 2026-07-09. The full `test_collectors.sh` run also
passed, including the financial-news collector, upstream catalog validation,
and the first investor-loop smoke test.
