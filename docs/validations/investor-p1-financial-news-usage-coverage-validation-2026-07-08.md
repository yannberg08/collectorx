# P1 Financial News Usage Coverage Validation - 2026-07-08

This validation records the third productization pass for
`financial-news-usage`.

## Scope

Collector path:

- Vertical source: `financial-news-usage`
- Skill: `skills/financial-news-usage`
- FinClaw target: investor information-consumption and monitoring-rule evidence

This pass improves user-authorized local packages. It does not crawl CLS,
WallstreetCN, Gelonghui, or any public news corpus, and it does not treat public
news content as a personal Wiki fact.

## Product Changes

- Added authorized ZIP import for finance-news usage packages.
- ZIP import supports JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, and TXT
  members.
- ZIP import skips absolute paths and `..` path traversal members.
- File/ZIP member provenance is preserved in `raw_ref.path` as
  `archive.zip::member`.
- Added `manifest.platform_coverage` for expected P1 finance-news platforms:
  - `cls`
  - `wallstreetcn`
  - `gelonghui`
- Added `manifest.action_coverage` for expected user actions:
  - `read`
  - `favorite`
  - `search`
  - `subscribe`
  - `alert`
- Added package summary fields for observed and missing platforms/actions.
- Preserved the read-only Chromium/Safari browser-history path from the prior
  pass.

## Fixture Validation

Validated scenarios:

- JSON usage export produces favorite, subscribe, and search events.
- HTML saved page produces a read event.
- ZIP alert export produces an alert event.
- Fake credential field `cookie` is removed from emitted events.
- ZIP member `../unsafe.json` is skipped.
- Fixture reports all expected platforms and all expected actions observed.
- Chromium browser-history fixture still filters out non-finance domains and
  reports missing Gelonghui coverage when only CLS and WallstreetCN are present.

Commands:

```bash
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python -m py_compile skills/financial-news-usage/scripts/financial_news_usage/parser.py skills/financial-news-usage/scripts/financial_news_usage.py
```

Result:

- Passed.

## Current Gate

- Authorized local file/folder/ZIP import: G1/G2 baseline.
- Authorized Chromium/Safari browser-history copy import: G1/G2 baseline.
- Platform/action coverage manifest: G1/G2 baseline.
- Real CLS/WallstreetCN/Gelonghui app caches, account APIs, and subscription/
  alert stores: not done in this pass.
- Safari/Windows/Linux real browser-history path validation: still needed.

## Remaining Before Production Candidate

- Discover and validate real CLS, WallstreetCN, and Gelonghui app caches or
  account export/API paths with explicit user authorization.
- Validate real subscription, alert, watchlist, and search storage fields.
- Validate Safari, Chrome, Edge, and other browser history copies on macOS,
  Windows, and Linux.
- Add account-level adapters only where they are read-only and do not collect
  credentials, cookies, or platform-wide news.
