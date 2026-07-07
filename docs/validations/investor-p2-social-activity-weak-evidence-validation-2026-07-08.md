# P2 Social Activity Weak Evidence Validation - 2026-07-08

This validation records the second productization pass for `social-activity`.

## Weak Influence Evidence Import

Collector path:

- Generic source: `social-activity`
- Skill: `skills/social-activity`

Result:

- Upgraded `social-activity` to `0.2.0`.
- Added XLSX/XLSM workbook parsing for authorized social activity exports.
- Expanded multi-section JSON packages so one export can contain:
  - follows
  - likes
  - favorites / collections
  - watch history
  - comments
  - shares / reposts
- Added fields useful to the investor influence lens:
  - source section / sheet
  - creator ID and creator URL
  - URL domain and item ID
  - tags, topics, and symbols
  - duration and watch progress
  - like, comment, share, favorite, view, and follower counts
- Added explicit weak-evidence policy fields to every event:
  - `evidence_role: weak_influence_signal`
  - `investment_claim_allowed: false`
  - `requires_corroboration: true`
- Manifest readiness now records weak attention evidence and confirms that the
  collector does not claim investment conclusions.
- Strengthened platform inference from URLs, field-name normalization, list
  parsing, recursive credential filtering, and content/comment preview capping.

Fixture validation:

- Existing Weibo, Bilibili, and Xiaohongshu fixtures still emit generic social
  activity events.
- Xiaohongshu-style nested JSON emits favorites, likes, comments, shares, and
  follows.
- Bilibili/Weibo-style XLSX workbook emits watch-history and favorite events.
- Nested fake token data is removed from emitted raw snapshots.
- Content-like raw fields are capped to previews.
- Counts using Chinese `万` units are normalized numerically.
- Events remain routed to `internal.social.activity`; investment filtering
  remains in `social-investment-influence`.

Current gate:

- Authorized JSON/CSV/Excel activity package parsing: G1/G2 baseline.
- Weak-evidence policy: implemented in generic events and manifest.
- Real Weibo/Bilibili/Xiaohongshu account/export validation: not done.

Remaining before production:

- Validate real Weibo user export or authorized browser/account history.
- Validate real Bilibili watch history, favorites, likes, follows, and comments.
- Validate real Xiaohongshu favorites, likes, follows, and comments.
- Add platform/domain allowlists and creator allowlists from real user flows.
- Backtest weak influence evidence against stronger trade, note, meeting, and
  research-document evidence before allowing it to affect investor Wiki
  conclusions.
