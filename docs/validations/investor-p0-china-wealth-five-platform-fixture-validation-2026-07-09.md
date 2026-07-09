# P0 China Wealth Five-Platform Fixture Validation - 2026-07-09

Status: `completed-offline-fixture`

## Scope

This pass strengthens the P0 `china-wealth-assets` offline fixture surface for
Alipay, Tiantian Fund, Danjuan, Qieman, and bank wealth exports. It verifies
that one `collect` run can parse multi-platform fund, wealth, cash-management,
asset snapshot, and transaction records without claiming a complete user asset
boundary or real account validation.

This is an offline fixture validation only. It does not use real accounts,
payment credentials, bank credentials, order placement, redemption, or money
movement.

## Fixture Added

- `examples/fixtures/china-wealth-five-platform/five_platform_assets.json`

The fixture includes five authorized-export-style rows:

- Alipay asset snapshot with total asset and available cash.
- Tiantian Fund fund holding with code, name, shares, NAV, market value, cost,
  and profit.
- Danjuan subscription transaction with amount, fee, and side.
- Qieman cash-management holding with code, name, shares, NAV, market value,
  and profit.
- Bank wealth holding with product code, name, market value, cost, and profit.

The fixture intentionally includes credential-shaped fields and values:

- `cookie`
- `token`
- `authorization`
- `session_id`
- `password`

These are expected to be stripped from emitted asset facts and raw copies.

## Test Coverage Added

Added `test_collects_five_platform_offline_fixture_with_boundary_and_secret_guards`
in `skills/china-wealth-assets/tests/test_china_wealth.py`.

The test verifies:

- exactly five retained business events from one fixture collect
- observed platforms:
  `alipay`, `tiantian-fund`, `danjuan`, `qieman`, `bank-wealth`
- observed asset surfaces:
  `asset_snapshot`, `fund_holding`, `fund_transaction`, `cash_management`,
  `wealth_holding`
- holding, trade, and other event kinds are correctly emitted
- platform/account/product/value fields are parsed for holdings and flows
- all expected P0 platforms are observed in `manifest.platform_coverage`
- `manifest.platform_coverage.real_account_validation=false`
- `manifest.evidence_policy.complete_asset_boundary_claimed=false`
- `manifest.asset_boundary_proof.proof_scope=partial_authorized_input`
- `manifest.asset_boundary_proof.overall_proof_level=medium_partial_asset_boundary`
- `manifest.asset_boundary_proof.requires_real_account_validation=true`
- `investor_wiki_evidence.v1.json` inherits the same partial boundary posture
- generated package passes `tools/validate_collector_package.py`

## Secret-Leakage Guards

The test adds local fixture assertions, without changing the shared package
validator, to avoid conflicting with the main controller's validator work.

Assertions cover:

- no `SHOULD_NOT_LEAK` marker in `events.jsonl`, `manifest.json`,
  `investor_wiki_evidence.v1.json`, or `SUMMARY.md`
- no `cookie`, `token`, `authorization`, `password`, or `session` terms in
  emitted event `data` values
- no credential-shaped keys inside emitted event `data.raw`
- no credential-shaped terms in business-facing manifest/evidence values
  outside generic collector audit policy text

## Verification Commands

```bash
.venv/bin/python -m py_compile skills/china-wealth-assets/tests/test_china_wealth.py
```

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
```

```bash
rm -rf /tmp/china_wealth_five_platform_debug
.venv/bin/python skills/china-wealth-assets/scripts/china_wealth.py collect \
  --input examples/fixtures/china-wealth-five-platform/five_platform_assets.json \
  --out-dir /tmp/china_wealth_five_platform_debug \
  --collected-at 2026-07-09T18:00:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/china_wealth_five_platform_debug \
  --collector china-wealth-assets
```

## Results

- Syntax validation passed for `test_china_wealth.py`.
- Full `china-wealth-assets` test suite passed.
- Manual five-platform package generation passed.
- Manual package validation passed:
  `CollectorX package validation passed; collector=china-wealth-assets; events=5; evidence=present`.

## Remaining Real Validation

- Run read-only real account/export validation for Alipay, Tiantian Fund,
  Danjuan, Qieman, and representative bank wealth platforms.
- Validate real export layouts, PDFs, and HAR/read-only screen samples against
  the same field coverage expectations.
- Prove account coverage per platform before promoting beyond
  `partial_authorized_input`.
- Keep `complete_asset_boundary_claimed=false` and
  `real_account_validation=false` until G3/real-account validation is complete.
