# P1 WeChat Favorites Readiness Gate Validation - 2026-07-09

This validation covers `wechat-favorites` `0.1.6`, the generic collector for
user-authorized WeChat favorites, public-account article files, read/share
actions, and ZIP packages.

## What Changed

- Added `manifest.usable_event_count`,
  `manifest.wechat_favorite_event_count`, `manifest.favorite_event_count`, and
  `manifest.gap_event_count`.
- Added `collection_readiness.can_enter_wechat_favorites_lake`,
  `can_enter_data_quality_lake`, `can_feed_wechat_article_favorites_lens`, and
  `can_feed_investor_wiki_directly=false`.
- Routed missing-input, no-readable, and scope-policy filtered-all runs to
  validator-safe `kind=profile` data-quality gap events with legal `time`,
  `business_records_written=false`, `read_only=true`, and
  `wiki_targets=["collectorx.data_quality.collection_gaps"]`.
- Kept retained favorite/read/share/saved-file events eligible for the
  `wechat-favorites` business lake and the downstream
  `wechat-article-favorites` lens.
- Kept gap-only packages out of the business lake, article lens, and direct
  Investor Wiki writes.

## Fixture Coverage

- Authorized JSON/HTML/ZIP package with favorite, read, share, and saved-file
  events.
- Partial authorization-scope retention across source account, action, tag,
  domain, and keyword filters.
- Fully filtered authorization-scope package producing
  `wechat_favorites_scope_policy_filtered_all`.
- Missing authorized input package producing `wechat_favorites_input_missing`.
- Unsupported/no-readable input package producing
  `wechat_favorites_no_readable_records`.
- Package validator checks for normal and gap-only packages.

## Commands

```bash
.venv/bin/python skills/wechat-favorites/tests/test_wechat_favorites.py
```

```bash
.venv/bin/python tools/validate_collector_package.py \
  /tmp/wechat_favorites_validator_normal_fixture \
  --collector wechat-favorites
```

```bash
git diff --check
```

## Expected Assertions

- Retained packages set `can_enter_wechat_favorites_lake=true`,
  `can_enter_data_quality_lake=false`,
  `can_feed_wechat_article_favorites_lens=true`, and
  `can_feed_investor_wiki_directly=false`.
- Fully filtered, missing-input, and no-readable packages set
  `can_enter_wechat_favorites_lake=false`,
  `can_enter_data_quality_lake=true`,
  `can_feed_wechat_article_favorites_lens=false`, and
  `can_feed_investor_wiki_directly=false`.
- Gap-only packages have `usable_event_count=0`,
  `wechat_favorite_event_count=0`, and `gap_event_count=1`.
- Gap events route only to `collectorx.data_quality.collection_gaps`.

## Result

The targeted test suite passed on 2026-07-09. The test suite validates normal,
missing-input, no-readable, and filtered-all packages through the CollectorX
package validator. A standalone normal fixture package under
`/tmp/wechat_favorites_validator_normal_fixture` also passed
`tools/validate_collector_package.py --collector wechat-favorites`.

## Integration Notes

- This pass intentionally does not modify
  `collectors/finclaw-investor-catalog.json`,
  `collectors/finclaw-invocation-contracts.json`,
  `docs/production-readiness.md`, `docs/finclaw-integration-guide.md`, or the
  roadmap files; the main thread should wire those after conflict-safe review.
- `wechat-favorites` remains a generic collector. It does not classify
  investment relevance and does not write Investor Wiki facts directly.
