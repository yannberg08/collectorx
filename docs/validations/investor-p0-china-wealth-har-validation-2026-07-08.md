# P0 China Wealth HAR Validation - 2026-07-08

This validation records the P0 China wealth pass that adds user-authorized
browser network export support to `china-wealth-assets`.

## Scope

- Collector: `china-wealth-assets`
- Version: `0.4.2`
- Input added: `.har` browser network export files selected by the user.
- Platforms covered by the HAR domain allowlist: Alipay, Tiantian Fund, Danjuan,
  Qieman, and bank wealth domains.
- Evidence role: fund holdings, wealth holdings, cash-management holdings,
  subscriptions, redemptions, dividends, asset snapshots, account-boundary
  signals, and value summaries outside broker stock accounts.
- Explicit non-goal: payment passwords, bank passwords, transfer actions,
  consumption records, non-investment payment flows, or a complete asset
  boundary claim.

## Implementation

- `.har` is now a supported input extension, including inside authorized ZIP
  packages.
- The parser reads only response bodies from whitelisted investment/fund/wealth
  platform domains.
- Domain names infer the platform when the response record does not provide one.
- Event provenance stores only local file path, HAR entry number, row number,
  endpoint path, response status, parser name, and platform.
- Request headers, request cookies, response cookies, Authorization headers, and
  request URL query strings are not written into events, manifest, or Investor
  Wiki evidence.

## Manifest Audit Added

- `authorized_browser_network_export_used`
- `browser_network_export_file_count`
- `har_entry_count`
- `har_investment_entry_count`
- `har_response_record_count`
- `har_skipped_entry_count`
- `har_skip_reason_counts`
- `har_endpoint_counts`
- `har_platform_entry_counts`
- `har_secret_material_stripped_count`
- `har_query_string_stripped_count`
- `har_secret_material_policy`

## Validation

Command:

```bash
.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py
```

Result:

```text
china-wealth-assets tests passed.
```

Fixture coverage:

- An Alipay HAR response emits a `cash_management` holding with account, shares,
  NAV, market value, and profit fields.
- A Tiantian Fund HAR response emits a `fund_transaction` buy event with amount
  and fee.
- A non-investment URL is skipped with `non_investment_platform_url`.
- A bank wealth non-JSON response is skipped with `non_json_response`.
- Platform domain inference populates `alipay` and `tiantian-fund`.
- `Cookie`, `Authorization`, token query strings, and secret fixture values do
  not appear in emitted events.

## Remaining Gaps

- Real user HAR samples are still needed to validate platform endpoint
  diversity, pagination, account totals, historical transactions, and bank
  wealth formats.
- This is not a one-click login/session adapter.
- The collector still reports only `partial_authorized_input` until real
  platform/account scope is proven for each user.
