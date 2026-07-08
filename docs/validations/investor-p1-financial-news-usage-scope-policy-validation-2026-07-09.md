# P1 Financial News Usage Scope Policy Validation - 2026-07-09

## Scope

This validation covers `financial-news-usage` `0.2.8`, the vertical collector
for user-authorized CLS, WallstreetCN, and Gelonghui usage traces. Version
`0.2.9` later hardens filtered-all package behavior; see
`docs/validations/investor-p1-financial-news-usage-filtered-all-gap-validation-2026-07-09.md`.

The goal is to narrow authorized finance-news usage records before Lake output
while preserving the product boundary: this collector records personal usage
signals, not public news facts or platform-wide content.

## What Changed

- `financial_news_usage.py collect` now accepts:
  - `--allow-platform` / `--deny-platform`
  - `--allow-action` / `--deny-action`
  - `--allow-source-app` / `--deny-source-app`
  - `--allow-domain` / `--deny-domain`
  - `--allow-topic` / `--deny-topic`
  - `--allow-keyword` / `--deny-keyword`
- Manifest `source_audit.financial_news_scope_policy` records configured
  filters, candidate record count, filtered record count, filter reason counts,
  and `financial_news_scope_policy_filtered_all`.
- `usage_boundary_proof.authorization_scope_boundary` gives FinClaw a stable
  place to inspect the user's authorization policy.
- If all candidate records are excluded by policy, readiness reports
  `scope_policy_filtered_all`. As of version `0.2.9`, the collector also emits
  one `financial_news_scope_policy_filtered_all` profile gap event so FinClaw
  can validate a traceable package instead of receiving an empty Lake file.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/financial-news-usage/scripts/financial_news_usage.py \
  skills/financial-news-usage/scripts/financial_news_usage/parser.py \
  skills/financial-news-usage/tests/test_financial_news_usage.py
```

```bash
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- Financial-news usage fixture validation passed.
- FinClaw catalog and batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.
- Existing coverage still validates JSON/CSV/HTML/Markdown/TXT/ZIP imports,
  Chromium browser history, direct Safari `History.db`, ZIP-packaged Safari
  history members, unsafe ZIP skips, source audit, behavior summary, and
  usage boundary proof.
- New scope-policy tests cover partial retention by platform/action/source
  app/domain/topic/keyword and filtered-all readiness. Version `0.2.9` extends
  this fixture to validate the gap package with
  `tools/validate_collector_package.py --collector financial-news-usage`.

## Product Boundary

- The collector only emits user-authorized usage traces.
- Scope policy narrows authorized records; it does not claim complete account
  history or investment intent.
- Browser-history inputs remain domain-filtered to CLS, WallstreetCN, and
  Gelonghui before event output.
- This pass does not claim real CLS, WallstreetCN, or Gelonghui app/account API
  validation.
- This pass does not claim public news crawling, public article mirroring,
  unrelated browser-history collection, topic false-positive backtesting, or
  Windows/Linux real browser path validation.
