# P0 Xueqiu Package Validation - 2026-07-08

This validation records the package/provenance pass for `xueqiu-watchlist` and
`xueqiu-investor-activity`. No real account cookies, tokens, private payloads, or
raw user exports are committed.

## Scope

- Watchlist collector: `xueqiu-watchlist` `0.2.1`
- Investor activity collector: `xueqiu-investor-activity` `0.2.1`
- FinClaw target: attention universe, information network, opinion expression,
  saved research, and model-portfolio evidence.
- Explicit non-goal: broker-confirmed assets, executions, orders, and cashflows.

## Changes Validated

Watchlist:

- Authorized ZIP packages are accepted in addition to CSV/TSV, JSON/JSONL/
  NDJSON, XLSX/XLSM, HTML, Markdown, and TXT.
- ZIP member provenance is preserved as `archive.zip::member`.
- Unsafe ZIP path traversal members are skipped.
- Manifest now includes `archive_member_event_count` and an evidence policy that
  marks Xueqiu watchlists as attention-universe evidence only.

Investor activity:

- Authorized XLSX/XLSM workbooks are accepted for broad activity exports.
- Authorized ZIP packages are accepted for JSON/JSONL/NDJSON, CSV/TSV,
  XLSX/XLSM, HTML, Markdown, and TXT members.
- ZIP member provenance is preserved as `archive.zip::member`.
- Unsafe ZIP path traversal members are skipped.
- Manifest now includes `archive_member_event_count` and an evidence policy that
  marks Xueqiu as non-broker trade evidence.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/xueqiu-watchlist/tests/test_parser.py
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

Covered fixtures:

- Watchlist CSV/JSON/XLSX/TXT package parsing.
- Watchlist ZIP package with one safe CSV member and one unsafe traversal member.
- Activity post/follow/favorite/portfolio parsing.
- Activity ZIP package containing an Excel workbook portfolio record.
- Credential-like raw key sanitization.
- SoulMirror lake sync path.
- Evidence policy flags that prevent Xueqiu from being treated as a broker trade
  source.

Both test commands passed in this validation pass.

## Current Gate

- `xueqiu-watchlist`: `baseline+audit`
- `xueqiu-investor-activity`: `baseline+audit`
- Real Xueqiu account/export adapter: still not done
- Real pagination validation across watchlist, follows, favorites, posts,
  comments, and portfolios: still required
- G4 backtest against broker trades, notes, research documents, and reviews:
  still required before production-candidate
