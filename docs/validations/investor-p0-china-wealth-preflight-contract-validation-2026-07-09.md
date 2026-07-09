# P0 China Wealth Preflight Contract Validation - 2026-07-09

This validation covers the `china-wealth-assets` `0.4.9` increment for source
preflight diagnostics and minimum field-contract gating. No real account files,
credentials, cookies, tokens, payment passwords, bank passwords, or private
platform payloads are committed.

## Scope

- Collector: `china-wealth-assets`
- FinClaw route: partial user-authorized China fund, wealth-management,
  cash-management, asset-snapshot, return, and cashflow facts.
- Non-goal: complete account/platform boundary proof. Real account validation
  remains false.

## Added Behavior

- `manifest.collection_audit.source_preflight` diagnoses whether requested
  inputs are supported platform export files, official statement PDFs,
  authorized browser HAR files, ZIP packages, or screen/text snapshots.
- If the user supplies input but none of it is supported, the package emits one
  `china_wealth_supported_input_missing` data-quality gap event and does not
  write business asset records.
- `china_wealth_asset_fact_contract.v1` gates candidate business records before
  asset-lake emission:
  - asset snapshots need a known platform and asset value;
  - holdings need a known platform, product identity, and value/unit evidence;
  - cash-management records need a known platform, product/cash identity, and
    cash value;
  - transaction/cashflow records need a known platform, cashflow amount, and
    direction or product identity.
- Rows that fail the minimum contract are blocked from asset facts. Partial
  rejection emits `china_wealth_field_contract_rejected_records`; full rejection
  emits `china_wealth_field_contract_rejected_all`.
- Manifest and Investor Wiki evidence now include `field_contract` summaries for
  asset, holding, return/income, and cashflow coverage.
- Secret-like string values in raw records are redacted, not only secret-like
  keys.

## Fixture Coverage

- Added
  `examples/fixtures/china-wealth-preflight-contract/preflight_contract_assets.json`.
- The fixture retains an Alipay asset snapshot and a Danjuan subscription
  cashflow.
- The fixture rejects a Tiantian Fund placeholder holding row that has product
  identity but no value/unit evidence.
- The fixture includes secret-marker strings under non-secret keys; the package
  verifies they do not leak into events, manifest, evidence, or summary.
- Unsupported `.docx` input produces a supported-source preflight gap package
  that passes package validation.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/china-wealth-assets/scripts/china_wealth/parser.py \
  skills/china-wealth-assets/scripts/china_wealth.py \
  skills/china-wealth-assets/tests/test_china_wealth.py
```

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
```

```bash
.venv/bin/python skills/china-wealth-assets/scripts/china_wealth.py collect --help
.venv/bin/python -m json.tool skills/china-wealth-assets/.collectorx.json
git diff --check
```

## Results

- Syntax validation passed.
- China wealth target tests passed, including package validation for no-input,
  filtered-all, unsupported-source, and field-contract gap packages.
- CLI help rendered successfully.
- Skill metadata JSON validation passed.
- `git diff --check` passed.

## Remaining Real Validation

- Run against real user-authorized exports/read-only screens for Alipay,
  Tiantian Fund, Danjuan, Qieman, and representative bank wealth products.
- Verify platform/account totals against visible account totals before claiming
  anything beyond partial authorized input.
- Review real bank/PDF/HAR samples for false field-contract rejection.
- Cross-check fund/wealth facts against broker, bank-statement, note, and review
  sources to avoid double counting.
