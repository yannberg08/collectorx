# P0 Xueqiu Source Audit Validation - 2026-07-08

This validation records the P0 Xueqiu watchlist and investor-activity pass for
source audit, saved-page handling, and field coverage. No real Xueqiu cookies,
tokens, private payloads, or credentials are committed.

## Scope

- Watchlist collector: `xueqiu-watchlist` `0.3.0`
- Investor activity collector: `xueqiu-investor-activity` `0.3.0`
- FinClaw target: vertical Xueqiu evidence for attention universe, information
  network, opinion expression, saved pages, and model-portfolio behavior.

## Fixes

- Fixed `xueqiu-investor-activity` saved HTML parsing. Saved Xueqiu pages now
  produce `saved_page` events instead of failing on undefined variables.
- Saved HTML pages are treated as non-trade evidence.

## Manifest Additions

Both Xueqiu collectors now record:

- input count;
- resolved input file count;
- extension coverage;
- ZIP member count;
- skipped ZIP member count;
- skipped ZIP member extension counts;
- parsed record count;
- emitted event count;
- path-level parse results;
- field coverage.

`xueqiu-investor-activity` additionally records pagination marker fields such as
`page`, `total`, `max_id`, `next_max_id`, `since_id`, and cursor-like fields.

## Evidence Boundary

Xueqiu remains non-broker evidence:

- no broker-confirmed holdings;
- no executions;
- no orders;
- no fund flows;
- no trading credentials;
- no platform-wide public scraping.

FinClaw may use it for attention, network, saved-page, opinion, and model
portfolio clues only, and should corroborate with broker, research, note, and
review sources.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/xueqiu-watchlist/tests/test_parser.py
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

Covered fixtures:

- watchlist CSV/JSON/XLSX/TXT/ZIP package collection;
- ZIP member provenance and skipped path-traversal accounting;
- watchlist filtered-record accounting;
- activity nested Snowball-like API shapes;
- saved HTML page parsing;
- pagination marker audit;
- field coverage in both manifests;
- credential-key sanitization;
- SoulMirror lake sync.

## Real Validation Status

This pass does not claim real Xueqiu account validation. The current remaining
G3/G4 work is:

- discover and validate a real user-authorized Xueqiu export or read-only
  account workflow;
- verify real pagination coverage for watchlists, follows, posts, comments,
  favorites, saved pages, and portfolios;
- review rate-limit and terms boundaries;
- backtest Xueqiu evidence against stronger trade, holding, research, note, and
  review sources.
