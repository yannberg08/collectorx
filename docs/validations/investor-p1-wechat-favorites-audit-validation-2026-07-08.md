# P1 WeChat Favorites Audit Validation - 2026-07-08

This validation records the audit/productization pass for `wechat-favorites`.

## Scope

Collector path:

- Generic source: `wechat-favorites`
- Skill: `skills/wechat-favorites`
- Lens target: `wechat-article-favorites`

This pass strengthens the upstream generic package for FinClaw Lake ingestion.
It does not crawl public-account article libraries and does not promote every
saved article into the investor Wiki.

## Product Changes

- Added per-event `text_length` so downstream lenses can judge whether a saved
  article has enough local content to support a Wiki claim.
- Preserved ZIP `source_archive` and `archive_member` in `raw_ref`, while
  keeping `raw_ref.path` as the original source label.
- Added `manifest.field_coverage` for recommended article/favorite metadata:
  item type, action type, title, source account, URL, action time, tags, text
  preview, and event time.
- Added `manifest.article_surface_summary` for article count, URL coverage,
  source-account coverage, tag coverage, text coverage, and public-account
  article count.
- Added `manifest.source_audit` for source refs, ZIP member events, archive
  count, and path-traversal collection status.
- Added `manifest.content_policy` and `manifest.evidence_policy` to make clear
  that this generic collector writes Lake events only; investment classification
  must happen in `wechat-article-favorites`.
- Hardened ZIP path handling for POSIX traversal, Windows traversal, and
  Windows drive-letter members.

## Fixture Validation

Validated scenarios:

- JSON favorites export produces favorite and read events.
- HTML saved public-account article produces a saved-file event.
- ZIP shared-article export produces a share event with archive provenance.
- Fake credential field `token` is removed from emitted events.
- ZIP members `../unsafe.json`, `..\\windows-traversal.json`, and
  `C:\\unsafe.json` are skipped.
- Manifest reports action coverage, field coverage, article surface summary,
  source audit, content policy, and evidence policy.

Command:

```bash
.venv/bin/python skills/wechat-favorites/tests/test_wechat_favorites.py
```

Result:

- Passed.

## Current Gate

- Authorized local file/folder/ZIP import: G1/G2 baseline+audit.
- Prior macOS saved-article validation: G2/G3 partial.
- Real WeChat favorites/public-account database validation: not done in this
  pass.
- Investment lens false-positive backtest: still needed before production.

## Remaining Before Production Candidate

- Discover and validate real WeChat favorites and public-account article
  storage on supported WeChat versions.
- Validate Windows and Linux paths where WeChat data is available.
- Add user-selected account/tag allowlists.
- Backtest `wechat-article-favorites` so non-investment saved articles do not
  enter investor Wiki conclusions.
