# P0 China Wealth Field Coverage Validation - 2026-07-08

This validation records the ZIP/provenance and field-coverage pass for
`china-wealth-assets`. No real account export, payment credential, bank
credential, token, cookie, or private raw payload is committed.

## Scope

- Collector: `china-wealth-assets` `0.3.1`
- FinClaw target: non-broker fund, wealth-management, cash-management,
  subscription/redemption, dividend, and asset-snapshot evidence.
- Explicit non-goal: payment credentials, bank passwords, consumption records,
  and complete asset-boundary claims without real platform validation.

## Changes Validated

- Authorized ZIP packages are accepted in addition to CSV/TSV, JSON/JSONL/
  NDJSON, XLSX/XLSM, HTML, Markdown, and TXT.
- ZIP member provenance is preserved as `archive.zip::member`.
- Unsafe ZIP path traversal members are skipped.
- `manifest.field_coverage` reports recommended field coverage:
  - platform
  - product code/name/type
  - quantity/shares
  - NAV
  - market value
  - total assets
  - available cash
  - cost
  - PnL and PnL rate
  - transaction amount
  - fee
  - side
- `manifest.asset_value_summary` summarizes this run's authorized market value,
  total asset, and transaction amount by platform.
- `manifest.evidence_policy` explicitly states that complete asset-boundary and
  real-account validation are not claimed.
- The same field and value summaries are included in
  `investor_wiki_evidence.v1.json`.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
```

Covered fixtures:

- Tiantian Fund holding and subscription CSV with exact numeric values.
- Mixed Alipay asset snapshot, bank wealth holding, and Danjuan redemption JSON.
- Qieman XLSX holding export.
- All-expected-platform fixture for platform coverage.
- ZIP package containing a safe Alipay holding CSV and an unsafe traversal
  member.
- Field coverage and asset value summary.
- Credential-like raw key sanitization.
- SoulMirror lake sync path.

The test command passed in this validation pass.

## Current Gate

- `china-wealth-assets`: `baseline+audit`
- Real Alipay/Tiantian/Danjuan/Qieman/bank account validation: still not done
- Complete account/platform coverage proof: still not done
- G4 double-counting backtest against broker positions, bank statements, notes,
  and reviews: still required before production-candidate
