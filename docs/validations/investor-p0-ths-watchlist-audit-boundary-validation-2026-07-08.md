# P0 Tonghuashun Watchlist Audit Boundary Validation - 2026-07-08

## Purpose

Validate that `ths-watchlist` emits a production-grade CollectorX package for
user-authorized Tonghuashun watchlist exports, including source audit, ZIP
provenance, field coverage, Investor Wiki evidence, and an explicit
attention-universe boundary proof.

## Scope

- `skills/ths-watchlist/scripts/ths_watchlist/parser.py`
- `skills/ths-watchlist/scripts/ths_watchlist.py`
- `skills/ths-watchlist/tests/test_ths_watchlist.py`
- `skills/ths-watchlist/VERSION`
- `skills/ths-watchlist/.collectorx.json`
- `skills/ths-watchlist/SKILL.md`
- `collectors/vertical/ths-watchlist.yaml`
- `collectors/finclaw-investor-catalog.json`
- `docs/finclaw-integration-guide.md`
- `docs/finclaw-investor-collector-productization.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `ths-watchlist` collects only user-authorized Tonghuashun watchlist exports.
- Supported inputs include CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM, HTML,
  Markdown, TXT, and ZIP packages.
- The package records requested inputs, missing inputs, resolved files, skipped
  files, skipped reasons, extension coverage, per-path parse results,
  parsed/filtered/emitted counts, ZIP member provenance, unsafe ZIP member
  skips, unsupported ZIP members, and limit truncation.
- `manifest.field_coverage` reports symbol, market, name, group, industry,
  reason, tags, added time, and source section coverage.
- `manifest.ths_watchlist_boundary_proof` states that Tonghuashun watchlists are
  attention-universe evidence only.
- The collector does not collect holdings, executions, orders, fund flows,
  trading passwords, cookies, tokens, or sessions.
- The collector does not claim complete Tonghuashun account coverage or complete
  attention-universe coverage.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/ths-watchlist/scripts/ths_watchlist/parser.py \
  skills/ths-watchlist/scripts/ths_watchlist.py
.venv/bin/python skills/ths-watchlist/tests/test_ths_watchlist.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Fixture Validation

- CSV, JSON, XLSX, TXT, and ZIP inputs emit seven watchlist events.
- JSON fixture includes one missing-code record, proving filtered-record audit.
- ZIP fixture includes one valid CSV member, one unsafe path member, and one
  unsupported member.
- Manifest audit records path-level parse results, skipped file counts,
  skipped ZIP member reasons, archive member counts, parsed/filtered/emitted
  counts, and field coverage.
- ZIP event raw refs preserve `archive.zip::member` provenance and member row.
- Evidence package remains canonical 7-dimension/20-subdimension Investor Wiki
  evidence.
- Boundary proof keeps strong-trade, holding, order, execution, fund-flow, and
  complete attention-universe claims false.

## Result

- Tonghuashun watchlist tests passed.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This pass does not validate a real Tonghuashun app export, real local store
format, Windows/Linux real devices, or backtest watchlist additions against
actual trades and research reviews.
