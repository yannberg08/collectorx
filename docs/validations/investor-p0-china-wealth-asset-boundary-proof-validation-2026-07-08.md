# P0 China Wealth Asset-Boundary Proof Validation - 2026-07-08

## Scope

This validation hardens the P0 `china-wealth-assets` collector so FinClaw can
judge whether a user-authorized fund/wealth input is useful asset-boundary
evidence before investor Wiki distillation.

Covered collector:

- `china-wealth-assets` `0.4.3`

## What Changed

- Added `manifest.asset_boundary_proof`.
- Mirrored the same proof object into
  `investor_wiki_evidence.v1.json.coverage_summary.asset_boundary_proof`.
- Added package summary lines for overall proof strength and missing platforms.
- Account proof checks:
  - known platform
  - named account reference
  - asset snapshot surface
  - holding surface
  - transaction surface
  - numeric value fields
- Account proof levels:
  - `strong_partial_account_boundary`
  - `medium_partial_account_boundary`
  - `weak_partial_account_boundary`
  - `no_account_evidence`
- Overall proof levels:
  - `strong_partial_asset_boundary`
  - `medium_partial_asset_boundary`
  - `weak_partial_asset_boundary`
  - `no_authorized_asset_evidence`

## Boundary Policy

The proof remains partial. The collector still writes:

- `complete_asset_boundary_claimed: false`
- `requires_real_account_validation: true`

This means FinClaw may use the evidence to understand authorized fund/wealth
assets, but must not claim complete user asset coverage until real account or
read-only-screen validation proves platform and account scope.

## Validation Commands

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
.venv/bin/python -m py_compile \
  skills/china-wealth-assets/scripts/china_wealth/parser.py \
  skills/china-wealth-assets/scripts/china_wealth.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Fixture Coverage

- No-input gap package with `no_authorized_asset_evidence`.
- All expected P0 platforms: Alipay, Tiantian Fund, Danjuan, Qieman, bank
  wealth.
- Account-level strong/medium proof classification.
- Missing account requirements for transaction-only or holding-only inputs.
- Platform proof summaries.
- Package `SUMMARY.md` proof lines.
- Investor Wiki evidence propagation.

## Result

All validation commands passed.

The collector remains `baseline+audit`.

This improves asset-boundary quality inspection, but does not claim one-click
real Alipay/Tiantian/Danjuan/Qieman/bank account validation.
