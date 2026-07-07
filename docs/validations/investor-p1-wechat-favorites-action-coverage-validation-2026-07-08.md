# P1 WeChat Favorites Action Coverage Validation - 2026-07-08

This validation records the second productization pass for `wechat-favorites`.

## Scope

Collector path:

- Generic source: `wechat-favorites`
- Skill: `skills/wechat-favorites`
- Lens target: `wechat-article-favorites`

This pass improves the upstream generic package. It does not crawl public
account article libraries and does not promote every saved article into the
investor Wiki.

## Product Changes

- Added authorized ZIP import for WeChat favorites/public-account article
  packages.
- ZIP import supports JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, and TXT
  members.
- ZIP import skips absolute paths and `..` path traversal members.
- File/ZIP member provenance is preserved in `raw_ref.path`.
- Added `manifest.action_coverage`:
  - expected P1 actions: `favorite`, `read`, `share`, `saved_file`
  - observed actions
  - observed expected actions
  - missing expected actions
  - action counts
  - unknown action count
  - `real_account_validation=false`
- Added `source_account_count` to show whether the collection has information
  source diversity without listing public-account names in the manifest.

## Fixture Validation

Validated scenarios:

- JSON favorites export produces favorite and read events.
- HTML saved public-account article produces a saved-file event.
- ZIP shared-article export produces a share event.
- Fake credential field `token` is removed from emitted events.
- ZIP member `../unsafe.json` is skipped.
- The fixture reports `all_expected_actions_observed`.

Command:

```bash
.venv/bin/python skills/wechat-favorites/tests/test_wechat_favorites.py
```

Result:

- Passed.

## Current Gate

- Authorized local file/folder/ZIP import: G1/G2 baseline.
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
