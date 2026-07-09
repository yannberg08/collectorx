# P2 Social Activity And Influence Readiness Gate Validation - 2026-07-09

This validation covers `social-activity` `0.2.9` and
`investor-source-collectors` `0.1.28`, the P2 social activity collector and
downstream `social-investment-influence` weak-evidence lens.

## What Changed

- Added `manifest.usable_event_count`, `manifest.social_activity_event_count`,
  and `manifest.gap_event_count` to `social-activity`.
- Added `collection_readiness.can_enter_social_activity_lake`,
  `can_enter_data_quality_lake`, `can_feed_social_investment_lens`, and
  `can_feed_investor_wiki_directly=false`.
- Kept retained Weibo, Bilibili, and Xiaohongshu follows, likes, favorites,
  watch history, comments, shares, saved pages, and browser-history visits as
  weak social activity signals.
- Routed `social-activity` no-input and filtered-all gap events to
  `collectorx.data_quality.collection_gaps`.
- Added `manifest.social_influence_event_count` and
  `collection_readiness.can_enter_social_investment_influence_lake` to
  `social-investment-influence`.
- Kept retained lens evidence eligible for Investor Wiki evidence packages, but
  always marked it as weak evidence that requires stronger trade/research
  corroboration.
- Routed lens filtered-all gap events to the data-quality lake and excluded
  them from Investor Wiki evidence facts.

## Fixture Coverage

- Weibo JSON follows and comments.
- Bilibili CSV and XLSX watch/like/favorite records.
- Xiaohongshu HTML and nested JSON saved/favorite records.
- Chromium browser-history copies filtered to social domains.
- ZIP-packaged social exports with unsafe-member rejection.
- Partial authorization scope retention.
- Fully filtered social-activity authorization scope gap package.
- Missing social-activity authorized input gap package.
- Retained social-investment-influence lens evidence.
- Fully filtered social-investment-influence lens gap package.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/social-activity/scripts/social_activity/parser.py \
  skills/social-activity/scripts/social_activity.py \
  skills/social-activity/tests/test_social_activity.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/tests/test_investor_sources.py

.venv/bin/python skills/social-activity/tests/test_social_activity.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Expected Assertions

- Retained `social-activity` packages set `can_enter_social_activity_lake=true`,
  `can_enter_data_quality_lake=false`,
  `can_feed_social_investment_lens=true`, and
  `can_feed_investor_wiki_directly=false`.
- Fully filtered and missing-input `social-activity` packages set
  `can_enter_social_activity_lake=false`,
  `can_enter_data_quality_lake=true`, and
  `can_feed_social_investment_lens=false`.
- Retained `social-investment-influence` packages set
  `can_enter_social_investment_influence_lake=true`,
  `can_enter_data_quality_lake=false`, and
  `can_feed_investor_wiki_evidence=true`.
- Fully filtered lens packages set
  `can_enter_social_investment_influence_lake=false`,
  `can_enter_data_quality_lake=true`, and
  `can_feed_investor_wiki_evidence=false`.
- Gap events route only to `collectorx.data_quality.collection_gaps`.
- Social influence lens evidence remains weak evidence and cannot claim an
  investment conclusion without corroboration.

## Result

All commands above passed on 2026-07-09 when run with the project virtual
environment. The full `test_collectors.sh` run also passed with
`PYTHON=.venv/bin/python`, including the social activity collector, social
investment influence lens, shared catalog validation, batch runner validation,
project validation, and the first investor-loop smoke test.

A plain `bash test_collectors.sh` run used the host Python at
`/Users/pengyingan/.local/bin/python3.12` and stopped at the TickTick API client
test because that host interpreter does not have `httpx` installed. The
project `.venv` run is the validated production path for this change set.
