# P1 Financial News Browser History Validation - 2026-07-08

This validation records the second productization pass for
`financial-news-usage`.

## Browser History Import

Collector path:

- Vertical source: `financial-news-usage`
- Skill: `skills/financial-news-usage`

Result:

- Upgraded `financial-news-usage` to `0.2.0`.
- Added read-only parsing for user-authorized browser history copies:
  - Chromium-family `History` SQLite databases such as Chrome, Edge, and Brave
  - Safari `History.db`
- Browser-history import only emits records whose URL host matches:
  - CLS / 财联社 domains
  - WallstreetCN / 华尔街见闻 domains
  - Gelonghui / 格隆汇 domains
- Captures action type, platform, domain, source app, URL, article title, visit
  time, visit count, typed count, transition, tags, symbols, article ID, and a
  sanitized raw snapshot where present.
- Strengthened action and platform normalization.
- Raw payload sanitization is recursive and removes credential-like keys before
  lake output.

Fixture validation:

- Structured CLS/Gelonghui/WallstreetCN exports still produce read, favorite,
  subscribe, and search events.
- Nested fake token data is removed from emitted raw snapshots.
- Chromium-style browser history emits only CLS and WallstreetCN visits.
- A non-finance `example.com` browser-history row is excluded.
- Platform counts are written into `manifest.json`.

Current gate:

- Authorized exports and saved pages: prior G2/G3 partial on macOS.
- Chromium browser-history copy: G1/G2 baseline via fixture.
- Safari browser-history parser: implemented, fixture-only pending real local
  validation.
- Real CLS/WallstreetCN/Gelonghui app/account APIs: not done.

Remaining before production:

- Validate real Chrome/Edge/Brave history copies on Windows, macOS, and Linux.
- Validate real Safari `History.db` copies on macOS.
- Discover and validate real app caches, authorized account exports, and
  subscription/alert stores for each platform.
- Keep this collector limited to user usage traces; public news search/crawling
  belongs to separate research tools, not personal-data collection.
