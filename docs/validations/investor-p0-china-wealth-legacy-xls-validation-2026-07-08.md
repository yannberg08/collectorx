# P0 China Wealth Legacy XLS Validation - 2026-07-08

This validation records the `china-wealth-assets` compatibility pass for common
Chinese fund and wealth exports that use `.xls` filenames but contain HTML
tables, Excel XML Spreadsheet content, renamed OOXML workbooks, or delimited
text.

No real account credentials, payment passwords, bank passwords, cookies, tokens,
or private bank/payment payloads are committed.

## Scope

- Collector: `china-wealth-assets` `0.4.4`
- FinClaw target: authorized Alipay, Tiantian Fund, Danjuan, Qieman, and bank
  wealth export compatibility.
- Non-goal: one-click real account adapters or complete asset-boundary claims.

## Fixture Coverage

The new fixture validates:

- Alipay fund holding from an HTML-table `.xls` export.
- Bank wealth holding from an Excel XML `.xls` export.
- Platform inference for `alipay` and `bank-wealth`.
- Subtype inference for `fund_holding` and `wealth_holding`.
- Numeric market-value preservation.
- `raw_ref.sheet` provenance for `html_table_1` and the XML worksheet name.
- Manifest extension audit for `.xls`.
- Asset value summary propagation.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/china-wealth-assets/scripts/china_wealth/parser.py \
  skills/china-wealth-assets/scripts/china_wealth.py \
  skills/china-wealth-assets/tests/test_china_wealth.py

.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
```

## Result

The legacy export path passes fixture validation and can now preserve structured
asset, holding, and value fields from `.xls` exports instead of degrading table
data into a single screen-snapshot event.

Remaining production gaps:

- Real Alipay/Tiantian/Danjuan/Qieman/bank export samples.
- Real per-platform account-boundary validation.
- One-click read-only adapters, subject to user authorization and platform
  terms.
