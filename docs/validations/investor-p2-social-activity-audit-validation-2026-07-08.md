# P2 Social Activity Audit Validation - 2026-07-08

This validation records the audit/weak-evidence pass for `social-activity` and
the `social-investment-influence` lens boundary.

## Scope

Collector path:

- Generic source: `social-activity`
- Lens target: `social-investment-influence`
- FinClaw target: weak investment influence and attention-source evidence only

This pass strengthens user-authorized local activity packages. It does not
scrape platform-wide content, collect other people's full profiles, or let
social activity become a standalone investment conclusion.

## Product Changes

- Preserved ZIP `source_archive` and `archive_member` in `raw_ref`.
- Added per-event `content_length` while keeping `content_preview` and
  `comment_preview` capped.
- Added `manifest.influence_surface_summary` for creator, creator ID/URL,
  content URL/domain, item ID, tags, topics, symbols, engagement counts,
  comment/content previews, and source section availability.
- Added `manifest.source_audit` for source refs, ZIP member events, archive
  count, source section/sheet events, and unsafe ZIP collection status.
- Added `manifest.content_policy` for preview-only content boundaries and
  no platform-wide/full-creator-profile scraping.
- Strengthened `manifest.weak_evidence_policy` with generic-collector and real
  validation flags.
- Hardened ZIP path handling for POSIX traversal, Windows traversal, and
  Windows drive-letter members.

## Fixture Validation

Validated scenarios:

- Weibo JSON records emit follow and comment events.
- Bilibili CSV records emit watch and like events.
- Xiaohongshu saved HTML emits a saved-page weak signal.
- Xiaohongshu nested JSON emits favorite, like, comment, share, and follow
  events.
- Bilibili/Weibo XLSX workbook emits watch and favorite events.
- Weibo ZIP package emits a share event with archive provenance.
- Fake credential field `token` is removed from raw snapshots.
- Content/comment fields are capped to previews and content length is recorded.
- ZIP members `../unsafe.json`, `..\\windows-traversal.json`, and
  `C:\\unsafe.json` are skipped.
- Fixture reports all expected platforms, all expected actions, all recommended
  weak-signal fields, weak-evidence policy, influence surface summary, source
  audit, and content policy.

Commands:

```bash
.venv/bin/python -m py_compile skills/social-activity/scripts/social_activity/parser.py skills/social-activity/scripts/social_activity.py skills/social-activity/tests/test_social_activity.py
.venv/bin/python skills/social-activity/tests/test_social_activity.py
```

Result:

- Passed.

## Current Gate

- Authorized JSON/CSV/Excel/HTML/TXT/ZIP social activity package parsing:
  G1/G2 baseline+audit.
- Platform/action/weak-field coverage manifest: G1/G2 baseline+audit.
- Weak-evidence, influence surface, source audit, and content-policy manifest:
  G1/G2 baseline+audit.
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
