# P0 China Wealth Productization Validation - 2026-07-08

This validation records the second productization pass for
`china-wealth-assets`.

## Scope

Collector path:

- Vertical source: `china-wealth-assets`
- Skill: `skills/china-wealth-assets`

Result:

- Upgraded the collector from simple CSV/JSON parsing to normalized fund,
  wealth, cash-management, transaction, and asset-snapshot events.
- Supported authorized CSV/TSV/JSON/JSONL/NDJSON/XLSX/XLSM/HTML/TXT/Markdown
  inputs.
- Added platform inference for:
  - Alipay
  - Tiantian Fund
  - Danjuan
  - Qieman
  - Bank wealth products
- Added numeric normalization for:
  - quantity/shares
  - NAV
  - market value
  - total assets
  - available cash
  - cost
  - PnL
  - PnL rate
  - transaction amount
  - fees
- Added credential-like raw key sanitization.
- Added `--sync-soulmirror` to copy the standard package into
  `~/.soulmirror/lake/china-wealth-assets`.

Fixture validation:

- Tiantian Fund CSV emits holding and transaction events with exact numeric
  fields.
- Mixed JSON emits Alipay asset snapshot, bank wealth holding, and Danjuan
  redemption events.
- Qieman XLSX emits a normalized holding event with sheet metadata.
- Credential-like raw fields are removed from retained metadata.
- SoulMirror lake sync writes root `events.jsonl`, `latest/manifest.json`, and
  `latest/soulmirror_sync.json`.

Real local candidate validation:

- This pass searched local authorized candidate locations for filenames clearly
  containing Alipay, Tiantian Fund, Danjuan, Qieman, fund, wealth, or bank
  wealth terms.
- No clearly named local fund/wealth export was found on this machine during
  this pass.
- Therefore this pass does not claim real account validation or a complete asset
  boundary.

Current gate:

- Local export/package parser: G1 strengthened.
- Prior broad local candidate parsing remains G2 partial, but not sufficient for
  production.
- Real platform/account adapter: not done.

Remaining before production:

- Validate real user-authorized exports or read-only screens for Alipay,
  Tiantian Fund, Danjuan, Qieman, and representative bank wealth products.
- Prove account/platform coverage before setting complete asset boundary.
- Add Windows/Linux path validation for downloaded/exported files.
- Backtest fund/wealth positions against broker positions and investment notes
  to avoid double counting and false portfolio conclusions.
