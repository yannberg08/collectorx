# P0 Xueqiu Scope Policy Validation - 2026-07-09

This validation covers the P0 Xueqiu vertical collectors after adding explicit
user authorization scope filters before Xueqiu attention or activity records
enter the Lake. No account credentials, cookies, tokens, or private real-account
content are committed.

## Scope

- Collector: `xueqiu-watchlist`
- Version: `0.3.1`; gap package ingestion was later hardened in version
  `0.3.2`.
- Collector: `xueqiu-investor-activity`
- Version: `0.3.4`; gap package ingestion was later hardened in version
  `0.3.5`.
- FinClaw route: vertical attention-universe evidence for the Investor Wiki,
  never broker-confirmed trade facts.

## Added Behavior

- `xueqiu_query.py collect` accepts allow/deny filters for symbol, market,
  group, industry, tag, and keyword.
- `xueqiu_activity.py collect` accepts allow/deny filters for activity,
  source-surface, source-app, domain, symbol, author, and keyword.
- Scope policy is an authorization boundary only. It does not classify
  investment relevance and does not replace broker, research, notes, or review
  corroboration.
- Manifest audit records configured filters, candidate event count, retained
  event count, filtered event count, reason counts, and filtered-all status.
- Watchlist and activity boundary proof expose
  `authorization_scope_boundary` for FinClaw gating.
- When every candidate record is filtered, readiness reports
  `scope_policy_filtered_all`.
- As of `xueqiu-watchlist` `0.3.3` and `xueqiu-investor-activity` `0.3.6`,
  no-input and filtered-all states also emit validator-safe profile gap events
  with non-empty `time`, event-count summaries, data-quality routing, readiness
  gates, and non-trade boundary flags.

## Fixture Coverage

- Watchlist fixture keeps only the authorized attention universe while checking
  symbol, market, group, industry, keyword allow filters and deny-keyword
  behavior.
- Watchlist filtered-all fixture verifies a scoped-out export emits an explicit
  gap instead of looking like a missing export.
- Activity fixture keeps only authorized records while checking symbol and
  keyword allow filters plus deny-keyword behavior.
- Activity filtered-all fixture verifies the same explicit filtered-all
  readiness path.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/xueqiu-watchlist/scripts/xueqiu/parser.py \
  skills/xueqiu-watchlist/scripts/xueqiu_query.py \
  skills/xueqiu-watchlist/tests/test_parser.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity/parser.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity.py \
  skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

```bash
.venv/bin/python skills/xueqiu-watchlist/tests/test_parser.py
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
.venv/bin/python skills/xueqiu-watchlist/scripts/xueqiu_query.py collect --help
.venv/bin/python skills/xueqiu-investor-activity/scripts/xueqiu_activity.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- Xueqiu watchlist fixture validation passed.
- Xueqiu investor activity fixture validation passed.
- CLI help shows the new scope-policy arguments for both collectors.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Project validation passed after rerunning sequentially. A parallel local run
  first collided on the QQ fixture temp directory; the isolated rerun passed.
- Full collector regression suite passed.

## Expected Manifest Signals

- `collection_audit.xueqiu_watchlist_scope_policy`
- `collection_audit.xueqiu_watchlist_scope_policy_filtered_all`
- `collection_audit.xueqiu_activity_scope_policy`
- `collection_audit.xueqiu_activity_scope_policy_filtered_all`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.
- `xueqiu_watchlist_boundary_proof.authorization_scope_boundary`
- `activity_boundary_proof.authorization_scope_boundary`

## Remaining Real Validation

- Run against real Xueqiu watchlist exports and real account activity samples.
- Validate real HAR exports and copied Chromium/Safari history from user-owned
  profiles under the same scope filters.
- Validate pagination, favorites/posts/comments/follows/portfolio coverage, and
  rate/terms boundary before any one-click real account adapter claim.
