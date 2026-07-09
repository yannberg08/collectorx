# P0 Xueqiu Gap Package Validation - 2026-07-09

This validation covers `xueqiu-watchlist` version `0.3.3` and
`xueqiu-investor-activity` version `0.3.6`, which harden no-input and
filtered-all outputs into standard CollectorX packages and add explicit
business-lake, data-quality-lake, and Investor Wiki evidence readiness gates so
FinClaw can validate packages without mistaking collection gaps for real
Investor Wiki facts.

## Scope

- Collector: `xueqiu-watchlist`
- Collector: `xueqiu-investor-activity`
- FinClaw route: vertical attention-universe, information-network, opinion,
  saved-content, and model-portfolio evidence for the Investor Wiki.
- Gap packages must not claim broker-confirmed holdings, executions, orders,
  fund flows, or investment conclusions.

## Added Behavior

- `xueqiu-watchlist` no-input emits one profile gap event with
  `data.gap=xueqiu_watchlist_authorized_input_missing`.
- `xueqiu-watchlist` fully filtered scope emits one profile gap event with
  `data.gap=xueqiu_watchlist_scope_policy_filtered_all`.
- `xueqiu-investor-activity` no-input emits one profile gap event with
  `data.gap=xueqiu_authorized_input_missing`.
- `xueqiu-investor-activity` fully filtered scope emits one profile gap event
  with `data.gap=xueqiu_scope_policy_filtered_all`.
- Gap events carry non-empty `time`, `data.status`, `data.profile_type`,
  candidate/retained/filtered counts, filter reason counts, and explicit
  non-trade boundary flags.
- Gap events route to `collectorx.data_quality.collection_gaps`.
- Manifest output includes `usable_event_count`, `watchlist_event_count`,
  `activity_event_count`, and `gap_event_count` so packages can be observable
  while still reporting zero usable personal evidence.
- `collection_readiness.can_enter_xueqiu_watchlist_lake` and
  `collection_readiness.can_enter_xueqiu_activity_lake` gate retained Xueqiu
  business evidence.
- `collection_readiness.can_enter_data_quality_lake` gates gap packages.
- `collection_readiness.can_feed_investor_wiki_evidence=false` prevents gap
  packages from becoming Investor Wiki facts.
- `xueqiu-investor-activity` Investor Wiki evidence counts only usable activity
  events; collection gaps do not become user-profile facts.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/xueqiu-watchlist/scripts/xueqiu_query.py \
  skills/xueqiu-watchlist/scripts/xueqiu/parser.py \
  skills/xueqiu-watchlist/tests/test_parser.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity/parser.py \
  skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

```bash
.venv/bin/python skills/xueqiu-watchlist/tests/test_parser.py
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
```

## Results

- Syntax validation passed.
- Xueqiu watchlist fixture validation passed.
- Xueqiu investor activity fixture validation passed.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed.

## Expected Signals

- Watchlist filtered-all: `data.gap=xueqiu_watchlist_scope_policy_filtered_all`.
- Activity filtered-all: `data.gap=xueqiu_scope_policy_filtered_all`.
- No-input: `data.gap=xueqiu_watchlist_authorized_input_missing` or
  `data.gap=xueqiu_authorized_input_missing`.
- `event.kind=profile`.
- `event.time` is a non-empty string.
- `data.broker_trade_fact_claimed=false`.
- `data.holding_fact_claimed=false`.
- `data.order_or_fund_flow_claimed=false`.
- `manifest.watchlist_event_count=0` for watchlist gap packages.
- `manifest.activity_event_count=0` for activity gap packages.
- `manifest.usable_event_count=0` for gap packages.
- `manifest.gap_event_count=1`.
- `manifest.collection_readiness.can_enter_finclaw=false`.
- `manifest.collection_readiness.can_enter_xueqiu_watchlist_lake=false` for
  watchlist gap packages.
- `manifest.collection_readiness.can_enter_xueqiu_activity_lake=false` for
  activity gap packages.
- `manifest.collection_readiness.can_enter_data_quality_lake=true`.
- `manifest.collection_readiness.can_feed_investor_wiki_evidence=false`.
- `event.wiki_targets=["collectorx.data_quality.collection_gaps"]`.

## Remaining Real Validation

- Run against real Xueqiu watchlist exports and real account activity samples.
- Validate real HAR exports and copied Chromium/Safari history from user-owned
  profiles under the same scope filters.
- Validate pagination, favorites/posts/comments/follows/portfolio coverage, and
  rate/terms boundary before any one-click real account adapter claim.
