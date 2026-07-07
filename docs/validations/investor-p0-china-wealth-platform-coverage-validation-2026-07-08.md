# P0 China Wealth Platform Coverage Validation

Date: 2026-07-08

## Scope

This pass strengthens `china-wealth-assets` so FinClaw can distinguish between:

- Authorized input coverage.
- Expected P0 platform coverage.
- Complete real account/asset boundary proof.

It does not claim real account validation.

## Expected P0 Platforms

The manifest now records coverage for:

- `alipay`
- `tiantian-fund`
- `danjuan`
- `qieman`
- `bank-wealth`

## Output Added

`manifest.platform_coverage` includes:

- `expected_p0_platforms`
- `observed_platforms`
- `missing_expected_platforms`
- `unknown_event_count`
- `complete_expected_platforms_observed`
- `real_account_validation`

The same platform coverage summary is also included in
`investor_wiki_evidence.v1.json`.

## Validation Result

Status: `completed-baseline`

Fixture validation covers:

- A partial Tiantian Fund input that reports the other expected platforms as
  missing.
- Mixed Alipay, bank wealth, and Danjuan input.
- An all-expected-platform fixture where `complete_expected_platforms_observed`
  is true but `real_account_validation` remains false.
- Existing numeric coverage, raw credential-key sanitization, Excel parsing, and
  SoulMirror lake sync tests.

Not claimed:

- Real Alipay/Tiantian/Danjuan/Qieman/bank validation.
- Complete user asset boundary.
- Bank account or payment credential access.

Next gates:

- Real per-platform read-only export or screen validation.
- Account coverage proof per platform.
- Cross-platform import path checks for actual user export files.
