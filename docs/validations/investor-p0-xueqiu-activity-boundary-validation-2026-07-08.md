# P0 Xueqiu Activity-Boundary Validation - 2026-07-08

## Scope

This validation hardens the P0 `xueqiu-investor-activity` collector so FinClaw
can distinguish broad Snowball personal-activity coverage from narrow or
partial authorized inputs.

Covered collector:

- `xueqiu-investor-activity` `0.3.2`

## What Changed

- Added `manifest.activity_boundary_proof`.
- Mirrored the same proof object into
  `investor_wiki_evidence.v1.json.coverage_summary.activity_boundary_proof`.
- Added package summary lines for activity-boundary proof and pagination
  completeness.
- Expected activity surfaces:
  - `watchlist`
  - `follow_user`
  - `follow_portfolio`
  - `portfolio_activity`
  - `comment`
  - `favorite`
  - `post`
  - `saved_page`
- Per-surface proof levels:
  - `usable_activity_evidence`
  - `thin_activity_evidence`
  - `raw_activity_presence_only`
  - `missing_activity_evidence`
- Pagination completeness records:
  - pagination marker count and fields
  - HAR endpoint counts
  - HAR response record count
  - limit truncation status
  - `complete_timeline_claimed: false`

## Boundary Policy

Snowball is not a broker trade source. The collector still writes:

- `xueqiu_is_broker_trade_source: false`
- `complete_xueqiu_activity_boundary_claimed: false`
- `pagination_completeness.complete_timeline_claimed: false`

This means FinClaw may use Snowball as attention-network, information-source,
opinion-expression, and model-portfolio evidence, but must not treat it as
broker-confirmed holdings, executions, orders, or complete personal timeline
coverage.

## Validation Commands

```bash
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
.venv/bin/python -m py_compile \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity/parser.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Fixture Coverage

- All expected activity surfaces in one authorized JSON fixture.
- HAR timeline response with pagination marker and endpoint audit.
- Evidence propagation into `investor_wiki_evidence.v1.json`.
- Package summary proof lines.
- Explicit non-broker-trade boundary.

## Result

All validation commands passed.

The collector remains `baseline+audit`.

This improves Snowball activity coverage inspection, but does not claim a
one-click real account adapter or complete timeline validation.
