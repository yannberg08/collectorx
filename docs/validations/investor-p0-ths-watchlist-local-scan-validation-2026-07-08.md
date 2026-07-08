# P0 Tonghuashun Watchlist Local-Scan Validation - 2026-07-08

## Scope

Validate that `ths-watchlist` can collect user-authorized local Tonghuashun
watchlist files without requiring a user-created export file, while preserving
the attention-universe-only boundary required by FinClaw Investor Wiki.

## Files Changed

- `skills/ths-watchlist/scripts/ths_watchlist.py`
- `skills/ths-watchlist/scripts/ths_watchlist/parser.py`
- `skills/ths-watchlist/tests/test_ths_watchlist.py`
- `skills/ths-watchlist/VERSION`
- `skills/ths-watchlist/.collectorx.json`
- `skills/ths-watchlist/SKILL.md`
- `collectors/vertical/ths-watchlist.yaml`
- `collectors/finclaw-investor-catalog.json`
- `collectors/finclaw-invocation-contracts.json`
- `tools/test_finclaw_catalog.py`
- Product docs and roadmap files.

## Product Behavior

- `collect --local-scan --container-root <authorized-ths-watchlist-root>` scans
  only the user-authorized root for likely Tonghuashun watchlist files.
- `--platform auto|mac|windows|linux|generic` records the local adapter used for
  discovery and supports cross-platform fixture simulation.
- `--probe-export <path>` writes a safe local-scan probe report before
  collection.
- Existing `--input` import still supports CSV/TSV, JSON/JSONL/NDJSON,
  XLSX/XLSM, HTML, Markdown, TXT, and ZIP exports.

## Boundary Assertions

- `ths-watchlist` remains attention-universe evidence only.
- It does not collect broker-confirmed holdings, executions, orders, fund
  flows, trading passwords, cookies, tokens, or sessions.
- Long numeric account/path fragments are masked in probe output and local-scan
  raw references.
- The collector does not claim complete Tonghuashun attention-universe coverage
  without real local-store validation.

## Fixture Validation

The new fixture creates a simulated Windows-style Tonghuashun user root with:

- `自选股.csv`
- `watchlist-extra.json`
- `ordinary.csv`
- `watchlist-secret.cookie`

Expected result:

- 2 watchlist events are emitted from the two likely watchlist candidates.
- The ordinary CSV and unsupported cookie file are not collected.
- Events carry `source_platform=windows`, `local_scan=true`, masked source path
  labels, and no leaked long numeric path fragments.
- Manifest records local-scan requested state, platform, candidate counts,
  local-scan event counts, and `authorized_ths_local_scan_partial` proof level.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/ths-watchlist/scripts/ths_watchlist.py \
  skills/ths-watchlist/scripts/ths_watchlist/parser.py \
  skills/ths-watchlist/tests/test_ths_watchlist.py
.venv/bin/python skills/ths-watchlist/tests/test_ths_watchlist.py
python3 -m json.tool collectors/finclaw-investor-catalog.json
python3 -m json.tool collectors/finclaw-invocation-contracts.json
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```
