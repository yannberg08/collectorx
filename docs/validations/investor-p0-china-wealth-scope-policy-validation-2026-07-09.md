# P0 China Wealth Scope Policy Validation - 2026-07-09

This validation covers the P0 `china-wealth-assets` collector after adding
explicit user authorization scope filters before fund, wealth, cash-management,
PDF statement, HAR, workbook, JSON, CSV, or ZIP records enter the Lake. No real
account credentials, cookies, tokens, payment passwords, bank passwords, or
private real-account files are committed.

## Scope

- Collector: `china-wealth-assets`
- Version: `0.4.6`; filtered-all package ingestion was later hardened in
  version `0.4.7` with
  `docs/validations/investor-p0-china-wealth-filtered-all-gap-validation-2026-07-09.md`.
- FinClaw route: partial fund/wealth/cash-management asset facts for the
  Investor Wiki; never a complete asset-boundary claim without real account or
  read-only-screen validation.

## Added Behavior

- `china_wealth.py collect` accepts allow/deny filters for platform, account,
  subtype, product code, product name, currency, side, and keyword.
- Scope policy is an authorization boundary only. It does not classify
  investment relevance, does not infer complete account coverage, and does not
  replace platform-level real validation.
- Manifest `collection_audit.china_wealth_scope_policy` records configured
  filters, candidate record count, retained/emitted count, filtered count,
  reason counts, and `china_wealth_scope_policy_filtered_all`.
- Manifest `asset_boundary_proof.authorization_scope_boundary` exposes the same
  policy boundary to FinClaw gating.
- When every candidate record is filtered, readiness reports
  `scope_policy_filtered_all`. As of version `0.4.7`, the collector also emits
  one `china_wealth_scope_policy_filtered_all` profile gap event so FinClaw can
  ingest a traceable authorization-boundary package.

## Fixture Coverage

- Partial-retention fixture keeps one authorized Alipay cash-management record
  while filtering other candidates by platform, account, subtype, product code,
  product name, currency, and deny-keyword behavior.
- Filtered-all fixture verifies that a provided Tiantian Fund export with an
  Alipay-only policy produces one profile gap event, explicit filtered-all
  readiness, and `asset_boundary_proof.overall_proof_level=scope_policy_filtered_all`.
- Existing coverage still validates CSV/JSON/Excel/legacy-XLS/HTML/PDF/HAR/ZIP
  parsing, exact numeric preservation, credential stripping, account/asset/
  currency summaries, asset-boundary proof, and SoulMirror sync.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/china-wealth-assets/scripts/china_wealth/parser.py \
  skills/china-wealth-assets/scripts/china_wealth.py \
  skills/china-wealth-assets/tests/test_china_wealth.py
```

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
.venv/bin/python skills/china-wealth-assets/scripts/china_wealth.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- China wealth fixture validation passed.
- CLI help shows the new scope-policy arguments.
- FinClaw catalog and batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.

## Expected Manifest Signals

- `collection_audit.china_wealth_scope_policy`
- `collection_audit.candidate_record_count`
- `collection_audit.scope_policy_filtered_record_count`
- `collection_audit.scope_policy_filter_reason_counts`
- `collection_audit.china_wealth_scope_policy_filtered_all`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.
- `asset_boundary_proof.authorization_scope_boundary`

## Remaining Real Validation

- Run against real Alipay, Tiantian Fund, Danjuan, Qieman, and bank wealth
  exports/PDF/HAR/read-only-screen samples under realistic user scope policies.
- Validate complete account-boundary proof per platform before promoting beyond
  partial authorized input.
- Review default product/account allowlists and false exclusions on real
  multi-platform asset packages.
