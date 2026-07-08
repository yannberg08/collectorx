# P0 WeChat Preflight Gap Package Validation - 2026-07-09

This validation covers the P0 generic `wechat` collector after hardening
`--collect --out-dir` gap behavior. FinClaw can now receive a standard
CollectorX package when WeChat preconditions are not ready or when the query
retains no owner-relevant text messages.

## Scope

- Collector: `wechat`
- Skill: `wechat-export`
- Version: `0.11.2`
- FinClaw route: generic personal communication Lake source before the
  `wechat-investment-dialogue` lens.
- Boundary: no direct investor Wiki evidence; no password, token, cookie,
  encryption key, raw database page, or automatic investment conclusion.

## Added Behavior

- `--collect --out-dir` writes a standard gap package when a readable
  `db_storage` path is missing.
- The same package path handles Mac 4.x key/dependency preflight failures and
  no retained owner-relevant text messages.
- Gap packages contain one `collectorx.event.v1` profile event with
  `data.profile_type=wechat_collect_preflight_gap`.
- Gap events explicitly record:
  - `raw_database_access_performed=false`
  - `credentials_collected=false`
  - `message_text_collected=false`
  - `investment_claim_allowed=false`
- Manifest `collection_readiness.can_enter_investor_lens=false` prevents the
  package from being treated as a successful upstream source for the investment
  dialogue lens.

## Fixture Coverage

- Existing two-message package fixture still verifies message events, field
  coverage, filter policy, message surface summary, source audit, and
  generic-to-lens boundary.
- New empty-message package fixture verifies `no_wechat_messages_collected`
  gap output and package validation.
- New CLI fixture calls `wechat_query.py --collect --db-dir <missing>
  --out-dir <dir>` and verifies:
  - exit success for product gap-package path
  - `manifest.collection_readiness.status=needs_readable_wechat_db_dir`
  - one profile gap event
  - no raw missing path in the gap event
  - package passes `tools/validate_collector_package.py --collector wechat`

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/wechat-export/scripts/wechat_query.py \
  skills/wechat-export/tests/test_collect_package.py
```

```bash
.venv/bin/python skills/wechat-export/tests/test_collect_package.py
.venv/bin/python skills/wechat-export/scripts/wechat_query.py --help
```

```bash
rm -rf /tmp/wechat_preflight_gap_cli
.venv/bin/python skills/wechat-export/scripts/wechat_query.py \
  --collect \
  --db-dir /tmp/collectorx-missing-wechat-db \
  --out-dir /tmp/wechat_preflight_gap_cli
.venv/bin/python tools/validate_collector_package.py \
  /tmp/wechat_preflight_gap_cli \
  --collector wechat
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
git diff --check
```

## Results

- Syntax validation passed for the hardened WeChat collector script and package
  tests.
- WeChat collect package tests passed, including the existing two-message
  fixture, the empty-message gap fixture, and the missing-db CLI preflight
  fixture.
- CLI help validation passed.
- Missing-db `--collect --out-dir` produced one
  `needs_readable_wechat_db_dir` profile gap event, with
  `can_enter_investor_lens=false`, `raw_database_access_performed=false`, and
  `message_text_collected=false`.
- Gap package validation passed with
  `tools/validate_collector_package.py --collector wechat`.
- JSON metadata validation passed for the FinClaw catalog, invocation
  contracts, and WeChat skill metadata.
- FinClaw catalog tests and batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed with `tools/validate_project.py`.
- Git whitespace validation passed with `git diff --check`.

## Remaining Real Validation

- Prepare authorized WeChat 4.x keys or platform-specific readable DB
  preconditions.
- Run generic `wechat` on a real Lake package and feed it into
  `wechat-investment-dialogue`.
- Tune contact/group/sender allowlists with the user.
- Backtest investment-dialogue evidence around actual trades and reviews.
