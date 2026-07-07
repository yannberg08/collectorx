# P1 Financial News Usage Validation - 2026-07-08

This validation records the first productization pass for finance-app usage
evidence without committing private article content or local file paths.

## Financial News Usage Collector

Collector path:

- Vertical source: `financial-news-usage`
- Skill: `skills/financial-news-usage`

Result:

- Added a runnable vertical collector for user-authorized finance-news usage
  exports and saved pages.
- Target platforms: CLS, WallstreetCN, Gelonghui, plus unknown finance-news
  sources when the platform cannot be inferred.
- Supported inputs: JSON, JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT.
- Captured user actions: read, favorite, subscribe, search, alert.
- Output package:
  - `lake/financial-news-usage/events.jsonl`
  - `manifest.json`
  - `investor_wiki_evidence.v1.json`
  - `SUMMARY.md`
- Manifest sets `can_claim_complete_usage_history: false`.

Fixture validation:

- CLS favorite, Gelonghui search, WallstreetCN subscription, and saved HTML read
  events are converted to `collectorx.event.v1`.
- Evidence marks `source_is_public_news_crawler: false`.
- Secret-like fields are removed from raw payload snapshots.

Real local candidate validation:

- Candidate files found: 16.
- `financial-news-usage` emitted 41 usage events.
- Kind counts: 35 note events, 6 other events.
- Action counts: 35 read events, 6 search events.
- Platform counts: 15 CLS, 1 WallstreetCN, 25 unknown.
- Evidence routes were produced for information sources, attention universe, and
  research workflow.

Current gate:

- Local authorized saved usage/pages: G2/G3 partial on macOS.
- Real CLS/WallstreetCN/Gelonghui account or app adapters: not done.
- Platform inference needs strengthening for saved pages without explicit source
  metadata.

Remaining before production:

- Discover and validate per-platform authorized exports/account APIs/local cache
  boundaries.
- Add browser-history import for only user-selected finance domains.
- Normalize subscription, alert, and watchlist metadata.
- Add allowlists/denylists for columns, authors, domains, and keywords.
- Validate Windows/Linux paths and browser export formats.
- Backtest whether usage traces correlate with actual investment decisions
  without turning generic news consumption into conclusions.
