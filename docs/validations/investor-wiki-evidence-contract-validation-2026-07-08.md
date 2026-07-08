# Investor Wiki Evidence Contract Validation - 2026-07-08

## Scope

This pass validates the shared FinClaw/SoulMirror evidence-package contract for
collectors that emit `investor_wiki_evidence.v1.json`.

The goal is not to claim new real-account validation. The goal is to ensure that
generated evidence packages can be consumed by the investor-portrait Wiki layer
as `external.investor / 7 dimensions / 20 subdimensions` metadata instead of
route-only summaries.

## Changes

- Added `collectorx.investor_wiki`.
- Added `tools/validate_investor_wiki_evidence.py`.
- Added `tools/test_investor_wiki_contract.py`.
- Wired the contract test and first-investor-loop evidence validation into
  `tools/validate_project.py`.
- Added canonical dimension coverage to evidence packages from:
  - `eastmoney-portfolio`
  - `xueqiu-investor-activity`
  - `china-wealth-assets`
  - `hk-us-brokerage`
  - `pro-terminal-usage`
  - `financial-news-usage`
- Kept `ths-portfolio` and `investor-source-collectors` on their existing
  canonical 7/20 dimension-tree outputs, now covered by the stricter project
  smoke test and package-level tests.

## Evidence Semantics

- Strong trade and asset sources can support portfolio, execution,
  decision-log, risk-exposure, and time-preference subdimensions.
- Snowball activity remains attention, network, opinion, and model-portfolio
  evidence, not broker-confirmed trade evidence.
- Professional terminal usage remains workflow metadata and information-source
  evidence, not licensed content mirroring and not trading execution evidence.
- Financial news usage remains personal read/favorite/search/subscribe/alert
  evidence, not public-news crawling and not user investment conclusions.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  collectorx/investor_wiki.py \
  tools/validate_investor_wiki_evidence.py \
  tools/test_investor_wiki_contract.py \
  skills/eastmoney-portfolio/scripts/eastmoney/local_collect.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity/parser.py \
  skills/china-wealth-assets/scripts/china_wealth/parser.py \
  skills/hk-us-brokerage/scripts/hk_us_brokerage/parser.py \
  skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py \
  skills/financial-news-usage/scripts/financial_news_usage/parser.py
```

```bash
.venv/bin/python tools/test_investor_wiki_contract.py
.venv/bin/python skills/eastmoney-portfolio/tests/test_local_collect.py
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
.venv/bin/python skills/hk-us-brokerage/tests/test_hk_us_brokerage.py
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
```

Expected result: all commands pass.

## Remaining Gaps

- This pass does not add new real WeChat, Snowball, Alipay/Tiantian/Danjuan,
  Futu/Tiger/IBKR, Wind/Choice/iFinD, CLS/WallstreetCN/Gelonghui, Windows, or
  Linux account validation.
- Wiki backtests against real personal history still require authorized real
  data samples.
- Route-only legacy packages may be inspected with
  `--allow-route-only`, but product-facing FinClaw distillation should use the
  strict default validator.
