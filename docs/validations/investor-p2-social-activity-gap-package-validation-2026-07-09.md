# P2 Social Activity Gap Package Validation - 2026-07-09

## Scope

This validation covers `social-activity` `0.2.8`, the generic P2 collector for
user-authorized Weibo, Bilibili, and Xiaohongshu social activity exports,
browser-history copies, and ZIP packages.

The goal is to make no-input and authorization-scope-filtered runs observable
without turning collection gaps into social activity facts, investment influence
facts, or Investor Wiki conclusions.

## What Changed

- Normal social activity events now fall back to `collected_at` when a source
  record does not expose a usable time field, so emitted Lake events satisfy the
  shared CollectorX package contract.
- No-input and no-record runs emit a validator-safe profile gap event instead
  of relying on an ambiguous package state.
- Scope-policy filtered-all runs emit one
  `social_activity_scope_policy_filtered_all` profile gap event instead of an
  empty `events.jsonl`.
- Gap events include non-empty `time`, `data.subtype=collector_gap`,
  `data.status`, `data.profile_type`, candidate/retained/filtered counts,
  filter reason counts, and explicit false-claim flags for social activity
  facts, investment influence facts, investment conclusions, complete social
  history, platform-wide scraping, full creator profiles, full content bodies,
  unrelated browser history, and private platform credentials.
- Manifest output includes `social_activity_event_count` and `gap_event_count`
  so FinClaw can distinguish usable social weak-signal events from collection
  observability.
- `social-activity` remains a generic Lake collector. It does not write
  Investor Wiki evidence directly; `social-investment-influence` remains the
  downstream weak-evidence lens.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/social-activity/scripts/social_activity.py \
  skills/social-activity/scripts/social_activity/parser.py \
  skills/social-activity/tests/test_social_activity.py
```

```bash
.venv/bin/python skills/social-activity/tests/test_social_activity.py
```

Manual filtered-all package check:

```bash
rm -rf /tmp/social_activity_filtered_all_cli /tmp/social_activity_gap_fixture
mkdir -p /tmp/social_activity_gap_fixture
printf '{"activities":[{"platform":"小红书","action":"收藏","creator":"投教作者","title":"基金定投纪律","url":"https://www.xiaohongshu.com/explore/abc"}]}\n' \
  > /tmp/social_activity_gap_fixture/social.json
.venv/bin/python skills/social-activity/scripts/social_activity.py collect \
  --input /tmp/social_activity_gap_fixture/social.json \
  --out-dir /tmp/social_activity_filtered_all_cli \
  --allow-platform weibo \
  --collected-at 2026-07-08T05:00:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/social_activity_filtered_all_cli \
  --collector social-activity \
  --json
```

Project gates:

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Expected Signals

- `lake/social-activity/events.jsonl` contains exactly one profile gap event
  for filtered-all and no-input packages.
- `manifest.event_count=1`.
- `manifest.social_activity_event_count=0`.
- `manifest.gap_event_count=1`.
- `manifest.collection_readiness.status=scope_policy_filtered_all` for
  filtered-all packages.
- `manifest.collection_readiness.can_enter_finclaw=false`.
- The gap event does not include the raw local input path, credential, cookie,
  token, full creator profile, full content body, unrelated browser-history
  row, platform-wide scrape, investment influence fact, or investment
  conclusion.

## Product Boundary

- The collector remains a generic personal social activity collector, not a
  platform crawler and not an investment-conclusion source.
- Gap events are package observability only. They can tell FinClaw why a
  collection did not yield usable social activity evidence, but they cannot
  become social influence facts or Investor Wiki facts.
- This pass does not claim real Weibo, Bilibili, or Xiaohongshu account export
  validation, real browser-path validation, default creator/domain allowlists,
  social-topic false-positive review, or weak-evidence backtest.
