# P1 Financial News Usage Source Audit Validation

Date: 2026-07-08

## Scope

This pass hardens the vertical `financial-news-usage` collector for
user-authorized CLS, WallstreetCN, Gelonghui usage exports, saved pages, ZIP
packages, and browser-history copies.

The collector remains personal-usage evidence:

- It emits `collectorx.event.v1` usage events into
  `lake/financial-news-usage/events.jsonl`.
- It captures the user's reads, favorites, searches, subscriptions, alerts, and
  browser-history visits where present in authorized input.
- It does not crawl public news pages.
- It does not mirror a public news corpus.
- It does not collect credentials, cookies, or account secrets.

## Change

Added `collect_from_inputs_with_audit` and wired collection audit into standard
package manifest output while keeping the previous `collect_from_inputs` API
compatible.

`manifest.source_audit` now records:

- requested inputs and missing inputs
- resolved input file count
- extension coverage and browser-history input coverage
- parsed record count and emitted event count
- skipped file counts and skipped file reasons
- ZIP archive counts, ZIP member counts, skipped ZIP member counts, and skipped
  ZIP member reasons
- browser-history source apps
- path-level parse results
- limit status
- path-safety flags for POSIX traversal and Windows drive-letter archive members

Missing input now produces both a gap event and an auditable `input_missing`
reason.

## Validation Result

Status: `completed-baseline+audit`

Gate reached: G1/G2-partial local package audit.

Fixture validation covers:

- JSON finance-news usage import.
- Saved HTML page import.
- ZIP alert event import.
- Chromium browser-history import with finance-domain filtering.
- Unsupported local file skip reasons.
- Unsafe ZIP member skipping.
- Missing input gap audit.
- Credential-like raw key filtering.
- Content policy and vertical evidence policy.

Not claimed:

- Real CLS, WallstreetCN, or Gelonghui app/account adapter validation.
- Real subscription, alert, watchlist, or search stores.
- Real Safari browser-history validation.
- Real Windows or Linux browser-history path validation.
- Public-news crawling or public-news corpus mirroring.

Next gates:

- Discover and validate real CLS, WallstreetCN, and Gelonghui app caches or
  account export/API paths with explicit user authorization.
- Validate real subscription, alert, watchlist, and search storage fields.
- Validate Safari, Chrome, Edge, and other browser-history copies on macOS,
  Windows, and Linux.
- Keep account-level adapters read-only and scoped to personal usage traces.
