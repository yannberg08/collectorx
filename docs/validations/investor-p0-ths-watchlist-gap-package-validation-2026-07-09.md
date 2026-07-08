# P0 Tonghuashun Watchlist Gap Package Validation - 2026-07-09

This validation covers `ths-watchlist` version `0.1.4`, which hardens
no-input and filtered-all outputs into standard CollectorX packages that FinClaw
can validate without mistaking collection gaps for real watchlist facts.

## Scope

- Collector: `ths-watchlist`
- Version: `0.1.4`
- FinClaw route: vertical attention-universe evidence for the Investor Wiki.
- Gap packages must not claim holdings, executions, orders, fund flows, or
  investment conclusions.

## Added Behavior

- No authorized input emits one profile gap event with
  `data.gap=ths_watchlist_authorized_input_missing`.
- A fully filtered authorization scope emits one profile gap event with
  `data.gap=ths_watchlist_scope_policy_filtered_all`.
- Gap events carry non-empty `time`, `data.status`, `data.profile_type`,
  candidate/retained/filtered counts, filter reason counts, and explicit
  non-trade boundary flags.
- Manifest output includes `watchlist_event_count` and `gap_event_count` so the
  package can be observable while still reporting zero usable watchlist facts.
- Fixture tests validate normal, no-input, and filtered-all outputs with
  `tools/validate_collector_package.py --require-evidence`.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/ths-watchlist/scripts/ths_watchlist.py \
  skills/ths-watchlist/scripts/ths_watchlist/parser.py \
  skills/ths-watchlist/tests/test_ths_watchlist.py
```

```bash
.venv/bin/python skills/ths-watchlist/tests/test_ths_watchlist.py
```

```bash
rm -rf /tmp/ths_watchlist_scope_filtered_all_cli /tmp/ths_watchlist_gap_fixture
mkdir -p /tmp/ths_watchlist_gap_fixture
printf '证券代码,证券名称\n600519,贵州茅台\n' > /tmp/ths_watchlist_gap_fixture/自选股.csv
.venv/bin/python skills/ths-watchlist/scripts/ths_watchlist.py collect \
  --input /tmp/ths_watchlist_gap_fixture/自选股.csv \
  --out-dir /tmp/ths_watchlist_scope_filtered_all_cli \
  --allow-symbol 688981 \
  --collected-at 2026-07-08T12:00:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/ths_watchlist_scope_filtered_all_cli \
  --collector ths-watchlist \
  --require-evidence
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
```

## Results

- Syntax validation passed.
- Tonghuashun watchlist fixture validation passed.
- Manual filtered-all package validation passed.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed.

## Expected Signals

- `event.kind=profile`
- `event.time` is a non-empty string.
- `data.gap=ths_watchlist_scope_policy_filtered_all` for fully filtered
  packages.
- `data.gap=ths_watchlist_authorized_input_missing` for no-input packages.
- `data.broker_trade_fact_claimed=false`
- `data.holding_fact_claimed=false`
- `data.order_or_fund_flow_claimed=false`
- `manifest.watchlist_event_count=0`
- `manifest.gap_event_count=1`
- `manifest.collection_readiness.can_enter_finclaw=false`

## Remaining Real Validation

- Run against real Tonghuashun local watchlist stores and exports on authorized
  user devices.
- Validate default app paths on Windows, macOS, and Linux machines.
- Backtest watchlist evidence against broker trades, research documents, notes,
  and reviews before promoting beyond attention-universe evidence.
