# P1 Financial News Usage Audit Validation - 2026-07-08

This validation records the audit/productization pass for
`financial-news-usage`.

## Scope

Collector path:

- Vertical source: `financial-news-usage`
- Skill: `skills/financial-news-usage`
- FinClaw target: investor information-consumption and monitoring-rule evidence

This pass strengthens user-authorized local packages and browser-history
copies. It does not crawl CLS, WallstreetCN, Gelonghui, or any public news
corpus, and it does not treat public news content as a personal Wiki fact.

## Product Changes

- Added per-event `text_length` for saved/read pages.
- Preserved ZIP `source_archive` and `archive_member` in `raw_ref`.
- Added `manifest.field_coverage` for action, platform, title, URL, domain,
  source app, source, channel, query, symbols, tags, article ID, text preview,
  and event time.
- Added `manifest.usage_surface_summary` for URL/domain coverage, source apps,
  source/channel coverage, queries, symbols, tags, text, browser-history events,
  alerts, and subscriptions.
- Added `manifest.source_audit` for source refs, ZIP member events, archive
  count, browser-history event count, browser-history source apps, and unsafe
  ZIP collection status.
- Added `manifest.content_policy` and `manifest.evidence_policy` to make clear
  that the collector captures personal usage traces only; it is not a public
  news crawler or news-content mirror.
- Hardened ZIP path handling for POSIX traversal, Windows traversal, and
  Windows drive-letter members.

## Fixture Validation

Validated scenarios:

- JSON usage export produces favorite, subscribe, and search events.
- HTML saved page produces a read event with text length.
- ZIP alert export produces an alert event with archive provenance.
- Fake credential field `token` is removed from emitted events.
- ZIP members `../unsafe.json`, `..\\windows-traversal.json`, and
  `C:\\unsafe.json` are skipped.
- Manifest reports platform/action coverage, field coverage, usage surface
  summary, source audit, content policy, and evidence policy.
- Chromium browser-history fixture still filters out non-finance domains and
  reports browser-history source audit.

Commands:

```bash
.venv/bin/python -m py_compile skills/financial-news-usage/scripts/financial_news_usage/parser.py skills/financial-news-usage/scripts/financial_news_usage.py skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
```

Result:

- Passed.

## Current Gate

- Authorized local file/folder/ZIP import: G1/G2 baseline+audit.
- Authorized Chromium/Safari browser-history copy import: G1/G2 baseline+audit
  for parser path, with Chromium fixture exercised here.
- Platform/action/field/source audit manifest: G1/G2 baseline+audit.
- Real CLS/WallstreetCN/Gelonghui app caches, account APIs, and subscription/
  alert stores: not done in this pass.
- Safari/Windows/Linux real browser-history path validation: still needed.

## Remaining Before Production Candidate

- Discover and validate real CLS, WallstreetCN, and Gelonghui app caches or
  account export/API paths with explicit user authorization.
- Validate real subscription, alert, watchlist, and search storage fields.
- Validate Safari, Chrome, Edge, and other browser-history copies on macOS,
  Windows, and Linux.
- Add account-level adapters only where they are read-only and do not collect
  credentials, cookies, or platform-wide news.
