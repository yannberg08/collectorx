# P0 Tonghuashun Watchlist Scope Policy Validation - 2026-07-09

This validation covers the P0 `ths-watchlist` collector after adding explicit
user authorization scope filters before Tonghuashun watchlist records enter the
Lake. No login passwords, trading passwords, cookies, tokens, sessions, or
broker-confirmed trade records are collected by this collector.

## Scope

- Collector: `ths-watchlist`
- Version: `0.1.3`; gap package ingestion was later hardened in version
  `0.1.4`.
- FinClaw route: vertical attention-universe evidence for the Investor Wiki,
  never broker-confirmed holdings, executions, orders, or fund flows.

## Added Behavior

- `ths_watchlist.py collect` accepts allow/deny filters for symbol, market,
  group, industry, tag, keyword, source path/member/label, and source platform.
- Scope policy is an authorization boundary only. It does not classify
  investment relevance and does not replace `ths-portfolio`,
  `eastmoney-portfolio`, research documents, notes, or reviews.
- Manifest `collection_audit.ths_watchlist_scope_policy` records configured
  filters, candidate event count, retained event count, filtered event count,
  reason counts, and `ths_watchlist_scope_policy_filtered_all`.
- Manifest `ths_watchlist_boundary_proof.authorization_scope_boundary` exposes
  the same policy boundary to FinClaw gating.
- When every candidate record is filtered, readiness reports
  `scope_policy_filtered_all` and the collector emits an explicit gap event
  instead of a misleading successful watchlist package.
- As of version `0.1.4`, no-input and filtered-all gap events are
  validator-safe profile events with non-empty `time`, candidate/filter counts,
  reason summaries, `manifest.watchlist_event_count=0`, and
  `manifest.gap_event_count=1`.

## Fixture Coverage

- Partial-retention fixture keeps one authorized watchlist record while
  filtering other candidates by symbol, market, group, industry, tag, keyword,
  and deny-keyword behavior.
- Filtered-all fixture verifies that a provided Tonghuashun watchlist export
  with an unmatched symbol policy produces an explicit filtered-all gap.
- Existing coverage still validates CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM,
  HTML/Markdown/TXT, ZIP member provenance, unsafe ZIP member skip handling,
  local-scan provenance, privacy masking, field coverage, and 7/20 Investor
  Wiki evidence output.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/ths-watchlist/scripts/ths_watchlist/parser.py \
  skills/ths-watchlist/scripts/ths_watchlist.py \
  skills/ths-watchlist/tests/test_ths_watchlist.py
```

```bash
.venv/bin/python skills/ths-watchlist/tests/test_ths_watchlist.py
.venv/bin/python skills/ths-watchlist/scripts/ths_watchlist.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- Tonghuashun watchlist fixture validation passed.
- CLI help shows the new scope-policy arguments.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.

## Expected Manifest Signals

- `collection_audit.ths_watchlist_scope_policy`
- `collection_audit.scope_policy_candidate_event_count`
- `collection_audit.scope_policy_retained_event_count`
- `collection_audit.scope_policy_filtered_event_count`
- `collection_audit.scope_policy_filter_reason_counts`
- `collection_audit.ths_watchlist_scope_policy_filtered_all`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.
- `ths_watchlist_boundary_proof.authorization_scope_boundary`

## Remaining Real Validation

- Run against real Tonghuashun local watchlist stores and real exported
  watchlist packages under realistic user authorization scope policies.
- Validate default app paths on Windows, macOS, and Linux machines.
- Backtest watchlist evidence against broker trades, research documents, notes,
  and reviews before promoting beyond attention-universe evidence.
