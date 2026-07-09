# P1 Feishu Readiness Gate Validation - 2026-07-09

This validation covers `feishu` `0.2.1`, the generic Feishu collector for
user-authorized local exports.

## What Changed

- Added `manifest.usable_event_count`, `manifest.feishu_event_count`, and
  `manifest.gap_event_count`.
- Added `collection_readiness.can_enter_feishu_lake`,
  `can_enter_data_quality_lake`, `can_feed_meeting_minutes_lens`,
  `can_feed_research_documents_lens`,
  `can_feed_collaboration_dialogue_lens`, and
  `can_feed_investor_wiki_directly=false`.
- Normal Feishu export events now have a non-empty `time` fallback and can pass
  CollectorX package validation even when individual rows omit source time.
- Missing-input and no-readable-record states now emit validator-safe profile
  gap events with `business_records_written=false`, `read_only=true`, and
  `wiki_targets=["collectorx.data_quality.collection_gaps"]`.
- Gap-only packages set `can_enter_feishu_lake=false` and
  `can_enter_data_quality_lake=true`; retained Feishu events set the inverse.
- Feishu collect mode currently has no complete scope/filter API, so this pass
  does not add a filtered-all CLI surface.

## Fixture Coverage

- Authorized JSON/CSV/ZIP Feishu export package with message, document,
  meeting, and recording records.
- Missing authorized input gap package.
- Authorized but empty readable input gap package.
- Normal and gap packages are validated through
  `tools/validate_collector_package.py --collector feishu`.

## Commands

```bash
.venv/bin/python skills/feishu/tests/test_feishu_collect.py
.venv/bin/python tools/validate_collector_package.py /tmp/feishu_normal_fixture_cli/out --collector feishu
git diff --check
```

## Expected Assertions

- Retained packages set `can_enter_feishu_lake=true`,
  `can_enter_data_quality_lake=false`, `can_feed_investor_wiki_directly=false`,
  and keep all gap counters at zero.
- Gap-only packages set `usable_event_count=0`, `feishu_event_count=0`,
  `gap_event_count=1`, `can_enter_feishu_lake=false`, and
  `can_enter_data_quality_lake=true`.
- Gap events use `kind=profile`, valid `time`, `record_kind=collector_gap`,
  `business_records_written=false`, `read_only=true`, and route only to
  `collectorx.data_quality.collection_gaps`.

## Result

Targeted Feishu tests passed on 2026-07-09, including validator checks for the
normal package, missing-input gap, and no-readable-record gap. The standalone
normal fixture at `/tmp/feishu_normal_fixture_cli/out` also passed CollectorX
package validation for `--collector feishu`.
