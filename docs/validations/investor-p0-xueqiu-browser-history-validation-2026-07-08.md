# P0 Xueqiu Browser History Validation - 2026-07-08

This validation records the browser-history input pass for
`xueqiu-investor-activity`.

## Scope

- Collector: `xueqiu-investor-activity`
- Version: `0.3.3`
- Source role: attention, information usage, opinion context, and saved-page
  evidence only.
- Strong-trade status: false. Browser history is never treated as broker
  assets, holdings, executions, orders, or fund flows.

## Implemented

- Added read-only parsing for user-authorized copied Chromium `History`,
  Safari `History.db`, `.sqlite`, `.sqlite3`, and `.db` browser history files.
- Added Xueqiu-only domain filtering for `xueqiu.com` and subdomains.
- Added ZIP member support for extensionless browser history files such as
  `Default/History`.
- Browser-history events emit:
  - `activity_type: saved_page`
  - `source_surface: browser_history`
  - `source_app`
  - URL/title/content preview
  - visit time
  - `visit_count`
  - `typed_count`
  - `transition_type`
- Manifest and Wiki evidence now carry:
  - `browser_history_supported`
  - `browser_history_domain_filtering`
  - `browser_history_input_count`
  - `browser_history_event_count`
  - `browser_history_source_apps`
  - `browser_history_boundary`
  - `complete_account_activity_claimed_from_history: false`

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity/parser.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity.py \
  skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py

.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

## Fixture Coverage

- Direct Chromium `History` file.
- ZIP package containing extensionless `Default/History`.
- Input paths containing spaces.
- Xueqiu canonical host, Xueqiu subdomain, and query-string URLs.
- Unrelated-domain exclusion.
- Browser-history source app, visit count, typed count, transition type, raw
  provenance, manifest audit, and Wiki evidence propagation.

## Explicit Non-Claims

- This is not a one-click Snowball account adapter.
- This does not claim complete Xueqiu account activity.
- This does not validate real account pagination.
- This does not collect broker-confirmed trade facts.
- This does not collect unrelated browser history.
