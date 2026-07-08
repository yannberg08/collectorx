# P2 HK/US Brokerage Scope Policy Validation - 2026-07-09

## Scope

This validation covers `hk-us-brokerage` `0.2.7`, the vertical strong-trade
collector for user-authorized read-only Futu, Tiger, and IBKR exports.

The goal is to narrow authorized brokerage records before Lake output while
preserving exact business numbers for records the user authorizes.

## What Changed

- `hk_us_brokerage.py collect` now accepts:
  - `--allow-broker` / `--deny-broker`
  - `--allow-account` / `--deny-account`
  - `--allow-subtype` / `--deny-subtype`
  - `--allow-symbol` / `--deny-symbol`
  - `--allow-market` / `--deny-market`
  - `--allow-currency` / `--deny-currency`
  - `--allow-keyword` / `--deny-keyword`
- Manifest `source_audit.brokerage_scope_policy` records configured filters,
  candidate record count, filtered record count, filter reason counts, and
  `brokerage_scope_policy_filtered_all`.
- `brokerage_boundary_proof.authorization_scope_boundary` gives FinClaw a
  stable place to inspect the user's authorization policy.
- If all candidate records are excluded by policy, readiness reports
  `scope_policy_filtered_all` and the collector does not emit a synthetic gap
  event.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/hk-us-brokerage/scripts/hk_us_brokerage.py \
  skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py \
  skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
```

```bash
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- HK/US brokerage fixture validation passed.
- FinClaw catalog and batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.
- Existing coverage still validates CSV/JSON/Excel/ZIP imports, nested broker
  statements, source audit, ZIP unsafe-member skips, account boundary,
  currency/market summary, fee/tax/margin summary, cashflow activity, income
  return, order execution, unified brokerage-boundary proof, and read-only
  evidence policy.
- New scope-policy tests cover partial retention by broker/account/subtype/
  symbol/market/currency/keyword and filtered-all readiness.

## Product Boundary

- The collector only emits user-authorized read-only brokerage records.
- Scope policy narrows authorized records; it does not claim complete account
  boundary, complete brokerage history, or investment intent.
- This pass does not claim real Futu, Tiger, or IBKR account export validation,
  read-only screen validation, broker native API validation, or Windows/Linux
  real path validation.
- This pass does not collect trading passwords, place orders, cancel orders,
  mutate orders, or crawl broker community content.
