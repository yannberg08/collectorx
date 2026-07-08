# Watchlist Evidence Contract Validation - 2026-07-08

## Scope

This pass upgrades watchlist-style vertical collectors so their standard
packages include `investor_wiki_evidence.v1.json` with the shared
`external.investor / 7 dimensions / 20 subdimensions` contract.

Covered collectors:

- `xueqiu-watchlist`
- `ths-watchlist`

## Changes

- Added `build_evidence()` to both watchlist parsers.
- Updated both CLIs to write `investor_wiki_evidence.v1.json` when `--out-dir`
  is used.
- Reused the shared `collectorx.investor_wiki` contract helper.
- Added fixture assertions for canonical dimension count, subdimension count,
  conservative support levels, and non-strong-trade evidence policy.

## Evidence Boundary

Watchlists can support:

- market-view hints
- value-preference hints
- industry-circle / attention-universe evidence
- information-learning-style hints
- style-profile hints
- information-source hints

Watchlists do not prove:

- broker-confirmed holdings
- executions
- orders
- fund flows
- complete portfolio boundaries
- investment conclusions without corroboration

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/xueqiu-watchlist/scripts/xueqiu/parser.py \
  skills/xueqiu-watchlist/scripts/xueqiu_query.py \
  skills/xueqiu-watchlist/tests/test_parser.py \
  skills/ths-watchlist/scripts/ths_watchlist/parser.py \
  skills/ths-watchlist/scripts/ths_watchlist.py \
  skills/ths-watchlist/tests/test_ths_watchlist.py
```

```bash
.venv/bin/python skills/xueqiu-watchlist/tests/test_parser.py
.venv/bin/python skills/ths-watchlist/tests/test_ths_watchlist.py
```

Expected result: all commands pass.

## Remaining Gaps

- No new real Snowball or Tonghuashun account validation is claimed.
- Attention-universe evidence still needs backtesting against trades, notes,
  research documents, and reviews before it can influence higher-confidence
  Wiki conclusions.
