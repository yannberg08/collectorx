# P2 Social Activity Source Audit Validation - 2026-07-08

This validation records the source-audit hardening pass for `social-activity`.

## Scope

Collector path:

- Generic source: `social-activity`
- Lens target: `social-investment-influence`
- FinClaw target: weak investment influence and attention-source evidence only

This pass covers user-authorized Weibo, Bilibili, and Xiaohongshu activity
exports in JSON/JSONL/NDJSON, CSV/TSV, XLSX/XLSM, HTML, Markdown, TXT, and ZIP
packages.

The collector captures personal activity traces such as follows, likes,
favorites, watch history, comments, shares, creator references, topics, symbols,
and engagement counts. These records are weak influence evidence only. They
cannot stand alone as investment conclusions and must be corroborated by trades,
portfolio records, research notes, meeting records, or stronger evidence.

## Product Changes

- Added `collect_from_inputs_with_audit` and kept `collect_from_inputs` as a
  compatibility wrapper.
- Added input-level audit fields for requested inputs, missing inputs, resolved
  files, supported extensions, extension counts, skipped file counts, skipped
  reasons, parsed records, emitted events, path-level parse results, and
  `--limit` truncation.
- Added ZIP member audit for member count, emitted member events, skipped member
  count, skipped member reasons, and unsafe path refusal.
- Updated CLI package generation so `manifest.source_audit` receives the
  collection audit instead of relying only on emitted event refs.
- Updated `SUMMARY.md` output with skipped ZIP member count.
- Aligned skill metadata to `0.2.3` and `baseline+audit`.

## Fixture Validation

Validated scenarios:

- Weibo JSON records emit follow and comment events.
- Bilibili CSV records emit watch and like events.
- Xiaohongshu saved HTML emits a saved-page weak signal.
- Xiaohongshu nested JSON emits favorite, like, comment, share, and follow
  events.
- Bilibili/Weibo XLSX workbook emits watch and favorite events.
- Weibo ZIP package emits a share event with archive provenance.
- Unsupported input files are counted and reported by extension and reason.
- Missing input paths emit a collection-gap event and record `input_missing`.
- ZIP members using POSIX traversal, Windows traversal, and Windows drive paths
  are skipped and reported as `unsafe_path`.
- ZIP `--limit` accounting counts only emitted records.
- Fake credential field `token` is removed from raw snapshots.
- Content/comment fields are capped to previews and content length is recorded.
- Fixture reports all expected platforms, actions, recommended weak-signal
  fields, weak-evidence policy, influence surface summary, source audit, and
  content policy.

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

## Not Claimed

- No real Weibo account adapter or export validation.
- No real Bilibili account adapter or export validation.
- No real Xiaohongshu account adapter or export validation.
- No platform-wide scraping.
- No full creator-profile scraping.
- No credential, cookie, token, authorization header, or session capture.
- No investment conclusion from social activity alone.
- No Windows/macOS/Linux real-path validation beyond fixtures.
- No weak-evidence backtest against trades, notes, research files, or meetings.

## Remaining Before Production Candidate

- Validate real Weibo exports or read-only account activity screens.
- Validate real Bilibili exports or read-only account activity screens.
- Validate real Xiaohongshu exports or read-only account activity screens.
- Add user-controlled platform/domain/creator allowlists.
- Backtest `social-investment-influence` against stronger trades, notes,
  research documents, and meetings before any Wiki conclusion uses social
  evidence.
