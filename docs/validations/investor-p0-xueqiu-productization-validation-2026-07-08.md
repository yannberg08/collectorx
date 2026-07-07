# P0 Xueqiu Productization Validation - 2026-07-08

This validation records the second productization pass for
`xueqiu-investor-activity`.

## Scope

Collector path:

- Vertical source: `xueqiu-investor-activity`
- Skill: `skills/xueqiu-investor-activity`

Result:

- Upgraded the collector from simple row parsing to normalized Xueqiu activity
  events.
- Supported authorized JSON/JSONL/CSV/TSV/HTML/TXT/Markdown inputs.
- Added extraction of common Snowball-like containers:
  - `statuses`
  - `list`
  - `data.items`
  - `stocks`
  - `cubes`
  - `rebalancing_histories`
- Added normalized security symbols, author metadata, source surfaces, metrics,
  saved-page metadata, and owner portfolio change details.
- Added sanitization of credential-like raw keys such as cookie, token,
  password, session, authorization, and secret.
- Added `--sync-soulmirror` to copy the standard package into
  `~/.soulmirror/lake/xueqiu-investor-activity`.

Fixture validation:

- Watchlist CSV emits a normalized `watchlist` event.
- Nested Snowball-like `data.items` JSON emits post, favorite, and
  owner-portfolio activity events.
- Portfolio rebalancing details are preserved as local evidence while
  `broker_confirmed_trade` remains `false`.
- Credential-like raw fields are removed from retained metadata.
- SoulMirror lake sync writes root `events.jsonl`, `latest/manifest.json`, and
  `latest/soulmirror_sync.json`.

Real local candidate validation:

- This pass searched local authorized candidate locations for filenames clearly
  containing `xueqiu` or `雪球`.
- No clearly named local Xueqiu export was found on this machine during this
  pass.
- Therefore this pass does not claim real account validation.

Current gate:

- Local export/package parser: G1 strengthened.
- Prior broad local candidate parsing remains G2 partial, but not sufficient for
  production.
- Real Xueqiu account/export adapter: not done.

Remaining before production:

- Validate a real user-authorized Xueqiu export or read-only account workflow.
- Prove pagination for posts, comments, favorites, follows, watchlists, and
  owner portfolios.
- Add rate-limit and terms boundary notes for any browser/API adapter.
- Backtest Xueqiu opinion/network evidence against stronger broker, note,
  research, and meeting evidence before promoting it into Wiki conclusions.
