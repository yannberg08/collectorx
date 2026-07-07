# P0 China Wealth Source Audit Validation - 2026-07-08

This validation records the P0 source-audit pass for `china-wealth-assets`.
No real account credentials, payment passwords, bank passwords, cookies, tokens,
or private bank/payment payloads are committed.

## Scope

- Collector: `china-wealth-assets` `0.4.0`
- FinClaw target: fund, wealth-management, cash-management, transaction, and
  asset-snapshot evidence outside broker stock accounts.

## Manifest Additions

`manifest.collection_audit` now records:

- input count;
- resolved input file count;
- extension coverage;
- ZIP member count;
- skipped ZIP member count;
- skipped ZIP member extension counts;
- parsed record count;
- emitted event count;
- supported extensions;
- path-level parse results;
- `complete_asset_boundary_claimed: false`.

Existing manifest outputs remain:

- platform coverage for Alipay, Tiantian Fund, Danjuan, Qieman, and bank wealth;
- field coverage for product, quantity, NAV, market value, total asset, cash,
  cost, PnL, PnL rate, transaction amount, fee, and side;
- asset value summary by platform;
- explicit no-complete-boundary policy.

## Boundary

The collector still treats any parsed input as partial authorized input. It does
not claim complete asset boundary until real account or read-only screen
validation proves the account scope for each platform.

It must not collect:

- payment passwords;
- bank passwords;
- non-investment payment records;
- consumer spending history;
- transfer or redemption actions.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
```

Covered fixtures:

- missing-input gap audit;
- mixed platform JSON;
- Excel export parsing;
- ZIP provenance;
- skipped ZIP path-traversal accounting;
- platform coverage;
- field coverage;
- asset value summary;
- SoulMirror lake sync.

## Real Validation Status

This pass does not claim real Alipay, Tiantian Fund, Danjuan, Qieman, or
bank-wealth account validation.

Remaining work:

- validate real per-platform authorized exports or read-only screens;
- prove account-boundary scope per platform;
- compare parsed totals with platform-visible account totals;
- backtest against broker, bank statement, note, and review evidence.
