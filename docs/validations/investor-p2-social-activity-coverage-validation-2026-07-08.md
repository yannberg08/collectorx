# P2 Social Activity Coverage Validation - 2026-07-08

This validation records the third productization pass for `social-activity` and
the `social-investment-influence` weak-evidence boundary.

## Scope

Collector path:

- Generic source: `social-activity`
- Lens target: `social-investment-influence`
- FinClaw target: weak investment influence and attention-source evidence only

This pass improves user-authorized local activity packages. It does not scrape
platform-wide content, collect other people's full profiles, or let social
activity become a standalone investment conclusion.

## Product Changes

- Added authorized ZIP import for social activity packages.
- ZIP import supports JSON/JSONL/NDJSON, CSV/TSV, XLSX/XLSM, HTML, Markdown,
  and TXT members.
- ZIP import skips absolute paths and `..` path traversal members.
- File/ZIP member provenance is preserved in `raw_ref.path` as
  `archive.zip::member`.
- Added `manifest.platform_coverage` for expected P2 social platforms:
  - `weibo`
  - `bilibili`
  - `xiaohongshu`
- Added `manifest.action_coverage` for expected user actions:
  - `follow`
  - `like`
  - `favorite`
  - `watch`
  - `comment`
  - `share`
- Added `manifest.weak_signal_field_coverage` for recommended weak-signal
  metadata such as creator IDs/URLs, item IDs, tags, topics, symbols, watch
  progress, engagement counts, comment previews, and content previews.
- Added `manifest.weak_evidence_policy`:
  - `evidence_role=weak_influence_signal`
  - `investment_claim_allowed=false`
  - `requires_corroboration=true`
  - `collector_writes_investor_wiki_directly=false`
  - `lens_required=social-investment-influence`
  - `usable_as_investment_conclusion=false`
- Clarified the lens registry so `social-investment-influence` excludes
  standalone investment conclusions.

## Fixture Validation

Validated scenarios:

- Weibo JSON records emit follow and comment events.
- Bilibili CSV records emit watch and like events.
- Xiaohongshu saved HTML emits a saved-page weak signal.
- Xiaohongshu nested JSON emits favorite, like, comment, share, and follow
  events.
- Bilibili/Weibo XLSX workbook emits watch and favorite events.
- Weibo ZIP package emits a share event and preserves
  `weibo_share.zip::shares/weibo-share.json`.
- Fake credential field `token` is removed from raw snapshots.
- Content/comment fields are capped to previews.
- ZIP member `../unsafe.json` is skipped.
- Fixture reports all expected platforms, all expected actions, all recommended
  weak-signal fields, and the weak-evidence policy.

Commands:

```bash
.venv/bin/python skills/social-activity/tests/test_social_activity.py
.venv/bin/python -m py_compile skills/social-activity/scripts/social_activity/parser.py skills/social-activity/scripts/social_activity.py
```

Result:

- Passed.

## Current Gate

- Authorized JSON/CSV/Excel/HTML/TXT/ZIP social activity package parsing:
  G1/G2 baseline.
- Platform/action/weak-field coverage manifest: G1/G2 baseline.
- Weak-evidence policy manifest: G1/G2 baseline.
- Real Weibo/Bilibili/Xiaohongshu account export validation: not done in this
  pass.

## Remaining Before Production Candidate

- Validate real Weibo exports or read-only account activity screens.
- Validate real Bilibili exports or read-only account activity screens.
- Validate real Xiaohongshu exports or read-only account activity screens.
- Add user-controlled platform/domain/creator allowlists.
- Backtest `social-investment-influence` against stronger trades, notes,
  research documents, and meetings before any Wiki conclusion uses social
  evidence.
