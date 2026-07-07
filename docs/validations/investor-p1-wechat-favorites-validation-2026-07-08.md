# P1 WeChat Favorites Validation - 2026-07-08

This validation records the first productization pass for WeChat favorites and
public-account article evidence without committing private article content or
local file paths.

## Generic WeChat Favorites Collector

Collector path:

- Generic source: `wechat-favorites`
- Skill: `skills/wechat-favorites`

Result:

- Added a runnable generic collector for user-authorized WeChat favorite,
  saved article, read, and share records.
- Supported inputs: JSON, JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT.
- Output package:
  - `lake/wechat-favorites/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Generic article events route to `internal.knowledge.saved_articles`.
- Manifest sets `can_claim_investment_article_favorites: false`.

Fixture validation:

- JSON favorites and saved HTML articles are converted to
  `collectorx.event.v1` file events.
- Events do not directly route to investor Wiki.
- Secret-like fields are removed from raw payload snapshots.

## WeChat Article Favorites Lens

Lens path:

- `wechat-article-favorites` via `skills/investor-source-collectors`

Fixture validation:

- Keeps an investment public-account article.
- Filters an unrelated lifestyle article.
- Tightened classifier false positives by requiring ASCII finance terms such as
  `PE`/`PB` to match as standalone tokens.

Real local candidate validation:

- Strict saved-article candidates found: 17.
- `wechat-favorites` emitted 17 generic saved-article events.
- `wechat-article-favorites` emitted 8 investor-article candidate events.
- Wiki coverage: 5 usable investor subdimensions.

Current gate:

- Local authorized saved-article files: G2/G3 partial on macOS.
- Lens filter: G2 baseline with one false-positive fix.
- Real WeChat favorites database/public-account read-history adapter: not done.

Remaining before production:

- Discover and validate real WeChat favorites/public-account artifact stores for
  supported WeChat versions.
- Add explicit allowlists/denylists for accounts, chats, tags, and folders.
- Separate favorite, read, share, and self-forwarded article actions when native
  metadata exists.
- Validate Windows/Linux WeChat export paths.
- Backtest against real trade timelines to prove these article actions help the
  investor Wiki rather than adding generic reading noise.
