# P0 WeChat Standard Package Validation - 2026-07-08

This pass productizes the generic WeChat collector output path for FinClaw. It
does not claim real WeChat account validation.

## Scope

- Collector: `wechat`
- Skill: `wechat-export`
- Priority: P0
- Goal: make `wechat_query.py --collect` produce a standard CollectorX package
  that the `wechat-investment-dialogue` lens can consume.

## Implemented

- Added `--out-dir` to `wechat_query.py --collect`.
- Writes:
  - `lake/wechat/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Converts legacy collect records into `collectorx.event.v1` message events.
- Preserves legacy `--out <file>` compact JSON array compatibility.
- Manifest records:
  - collection readiness
  - platform/key preconditions
  - field coverage
  - message surface summary
  - filter policy
  - source audit
  - generic-to-lens evidence policy
- `wechat` remains a generic collector. Investor evidence must flow through
  `wechat-investment-dialogue`.

## Validation

Commands run:

```bash
.venv/bin/python -m py_compile \
  skills/wechat-export/scripts/wechat_query.py \
  skills/wechat-export/tests/test_collect_package.py \
  tools/validate_project.py

.venv/bin/python skills/wechat-export/tests/test_collect_package.py

.venv/bin/python skills/wechat-export/scripts/wechat_query.py --help
```

Results:

- Package fixture test passed.
- `--help` exposes `--out-dir`.
- No real WeChat database, key, password, cookie, token, or decrypted DB content
  is required by the fixture test.

## Status

- `wechat`: `baseline+audit`
- `wechat-investment-dialogue`: unchanged runnable lens baseline

## Remaining Gap

- Real macOS source validation still requires authorized WeChat 4.x per-database
  keys. On the current Mac this remains blocked by key/SIP preconditions.
- Windows/Linux need real authorized local database/key or decrypted database
  validation.
- Contact/group allowlists and trade-adjacent Wiki backtests are still required
  before production-candidate.
