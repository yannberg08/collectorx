# P2 Social Activity Validation - 2026-07-08

This validation records the first productization pass for generic social
activity and the investor influence lens.

## Social Activity Collector

Collector path:

- Generic source: `social-activity`
- Skill: `skills/social-activity`

Result:

- Added a runnable generic collector for user-authorized Weibo, Bilibili,
  Xiaohongshu, Douyin-like social activity exports and saved activity records.
- Supported inputs: JSON, JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT.
- Captured user-owned actions:
  - follows
  - likes
  - favorites
  - watch/view history
  - comments
  - shares
  - saved pages
- Output package:
  - `lake/social-activity/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Generic events route to `internal.social.activity`.
- Manifest sets `can_claim_investment_influence: false`.

Fixture validation:

- Weibo follow/comment, Bilibili watch/like, and Xiaohongshu saved-page records
  are converted to `collectorx.event.v1`.
- Generic social events do not directly route to investor Wiki.
- `social-investment-influence` keeps investment activity and filters
  entertainment activity.

Real local candidate validation:

- Broad keyword search was too noisy and produced 986 events from unrelated CSV
  and document rows; this was rejected as validation evidence.
- Strict social-domain/activity candidate search found 1 candidate file.
- `social-activity` emitted 1 generic event.
- `social-investment-influence` emitted 1 weak investor-influence candidate.
- The lens evidence had 5 weak supported subdimensions, but
  `usable_for_wiki_now` was empty. This is expected: social traces are weak
  influence evidence and should not become investor conclusions by themselves.

Current gate:

- Fixture/local parser: G1.
- Strict local saved-record validation: G2/G3 partial on macOS.
- Real Weibo/Bilibili/Xiaohongshu account/export/API validation: not done.

Remaining before production:

- Validate real Weibo user export or authorized browser/account history.
- Validate real Bilibili watch history, favorites, likes, follows, and comments.
- Validate real Xiaohongshu favorites, likes, follows, and comments.
- Add platform/domain allowlists to reduce noisy local-document matches.
- Add creator/account allowlists and denylists.
- Keep social activity as weak influence evidence unless supported by stronger
  trade, note, meeting, or research-document evidence.
