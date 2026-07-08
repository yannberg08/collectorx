# P0 China Wealth Account Boundary Validation - 2026-07-08

This validation records the P0 account-boundary pass for
`china-wealth-assets`. No real account credentials, payment passwords, bank
passwords, cookies, tokens, or private payment/bank payloads are committed.

## Scope

- Collector: `china-wealth-assets` `0.4.1`
- FinClaw target: fund, wealth-management, cash-management, transaction,
  asset-snapshot, account-boundary, and currency evidence outside broker stock
  accounts.

## Manifest Additions

`manifest.account_boundary_summary` now records:

- platform/account groups observed in the authorized input;
- named account group count and unknown-account event count;
- per-account kind/subtype counts;
- per-account asset surfaces;
- per-account product type counts, product count, product sample, and currency
  counts;
- per-account value summary by currency;
- `complete_account_boundary_claimed: false`;
- `requires_real_account_validation: true`.

`manifest.asset_surface_summary` now records:

- expected asset surfaces: asset snapshot, fund holding, wealth holding, cash
  management, and fund transaction;
- observed and missing asset surfaces;
- holding, transaction, and snapshot event counts;
- transaction side counts and transaction amount by side;
- platform-to-surface matrix.

`manifest.currency_summary` now records:

- event count by currency;
- value fields by currency;
- value fields by platform and currency.

The same summaries are also exposed in
`investor_wiki_evidence.v1.json.coverage_summary` so FinClaw/SoulMirror can
inspect boundary quality before distilling investor Wiki evidence.

## Boundary

The collector still treats parsed files as partial authorized input. It does
not claim a complete asset or account boundary until real account or read-only
screen validation proves platform/account scope.

It must not collect:

- payment passwords;
- bank passwords;
- non-investment payment records;
- consumer spending history;
- transfer, subscription, redemption, or order execution actions.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
```

New fixtures cover:

- five expected platforms in one authorized JSON input;
- five named account groups;
- asset snapshot, fund holding, wealth holding, cash management, and fund
  transaction surfaces;
- CNY and USD value fields;
- buy and sell transaction-side amounts;
- evidence-package propagation of account and asset-surface summaries.

## Real Validation Status

This pass does not claim real Alipay, Tiantian Fund, Danjuan, Qieman, or
bank-wealth account validation.

Remaining work:

- validate real per-platform authorized exports or read-only screens;
- prove account-boundary scope per platform;
- compare parsed totals with platform-visible account totals;
- backtest against broker, bank statement, note, and review evidence.
