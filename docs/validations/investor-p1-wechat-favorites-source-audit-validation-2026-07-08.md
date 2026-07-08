# P1 WeChat Favorites Source Audit Validation

Date: 2026-07-08

## Scope

This pass hardens the generic `wechat-favorites` collector for user-authorized
WeChat favorites, saved public-account articles, read/share records, local
article files, and ZIP export packages.

The collector remains generic:

- It emits `collectorx.event.v1` saved-article/action events into
  `lake/wechat-favorites/events.jsonl`.
- It does not crawl public-account article libraries.
- It does not decide whether an article is investment evidence.
- It does not write investor Wiki evidence directly.
- `wechat-article-favorites` performs investor-specific filtering and Wiki
  routing.

## Change

Added `collect_records_with_audit` and wired collection audit into standard
package manifest output.

`manifest.source_audit` now records:

- requested inputs and missing inputs
- resolved input file count
- extension coverage
- parsed record count and emitted event count
- skipped file counts and skipped file reasons
- ZIP archive counts, ZIP member counts, skipped ZIP member counts, and skipped
  ZIP member reasons
- path-level parse results
- limit status
- path-safety flags for POSIX traversal and Windows drive-letter archive members

Missing input now produces both a gap event and an auditable `input_missing`
reason.

## Validation Result

Status: `completed-baseline+audit`

Gate reached: G1/G2-partial local package audit.

Fixture validation covers:

- JSON WeChat favorites import.
- Saved HTML public-account article import.
- ZIP shared article import.
- Favorite/read/share/saved-file action coverage.
- Unsupported local file skip reasons.
- Unsafe ZIP member skipping.
- Missing input gap audit.
- Credential-like raw key filtering.
- Preview-only content policy by default.

Not claimed:

- Real WeChat favorites database validation.
- Real public-account read-history validation.
- Real Windows or Linux WeChat path validation.
- Investment-article classification by the generic collector.

Next gates:

- Discover and validate real WeChat favorites/public-account stores with user
  authorization.
- Add account/tag allowlists for real user article sources.
- Validate Windows/Linux paths on real devices.
- Backtest `wechat-article-favorites` against stronger trade, research, and
  note evidence before using saved articles as influence evidence.
