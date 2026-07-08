# P0 China Wealth Filtered-All Gap Validation - 2026-07-09

This validation covers the P0 `china-wealth-assets` collector after hardening
scope-policy filtered-all package behavior. A readable fund/wealth input that
is fully outside the user's authorization scope now emits a traceable gap event
instead of an empty Lake file.

## Scope

- Collector: `china-wealth-assets`
- Version: `0.4.7`
- FinClaw route: partial fund, wealth, cash-management, and bank-wealth asset
  facts for the Investor Wiki.
- Boundary: no complete asset-boundary claim, no payment password, no bank
  credential, no account mutation, and no filtered business asset record.

## Added Behavior

- `collect_from_inputs_with_audit(...)` converts
  `collection_audit.china_wealth_scope_policy_filtered_all=true` into one
  `collectorx.event.v1` profile event with
  `data.gap=china_wealth_scope_policy_filtered_all`.
- The gap event records candidate, retained, filtered, and reason counts but no
  product code, product name, position amount, transaction amount, account
  mutation, credential, cookie, token, or raw input path.
- No-input and filtered-all gap events now carry a non-empty `time` value so
  `tools/validate_collector_package.py` can validate the package.
- Manifest readiness remains `scope_policy_filtered_all` with
  `can_enter_finclaw=false`.
- Investor Wiki evidence still ignores gap events for 7/20 support, so a
  filtered-all package does not create fake asset, portfolio, or execution
  evidence.

## Fixture Coverage

- No-input fixture verifies a valid profile gap event and package validation.
- Filtered-all fixture verifies:
  - one profile gap event in `lake/china-wealth-assets/events.jsonl`
  - `data.gap=china_wealth_scope_policy_filtered_all`
  - candidate count `1`, retained count `0`, filtered count `1`
  - reason counts `{"platform_not_allowed": 1}`
  - no retained product or money fields in the gap event
  - `manifest.collection_readiness.status=scope_policy_filtered_all`
  - `manifest.collection_readiness.can_enter_finclaw=false`
  - `investor_wiki_evidence.v1.json` keeps all 20 subdimensions at
    `support_level=none`
  - package validation passes with
    `tools/validate_collector_package.py --collector china-wealth-assets`

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
rm -rf /tmp/china_wealth_scope_filtered_all_cli
.venv/bin/python skills/china-wealth-assets/scripts/china_wealth.py collect \
  --input /tmp/china_wealth_filtered_all_fixture.json \
  --out-dir /tmp/china_wealth_scope_filtered_all_cli \
  --allow-platform alipay \
  --collected-at 2026-07-09T16:00:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/china_wealth_scope_filtered_all_cli \
  --collector china-wealth-assets
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Results

- Syntax validation passed for `china_wealth/parser.py`, `china_wealth.py`,
  and `test_china_wealth.py`.
- China wealth fixture validation passed, including no-input gap package
  validation and filtered-all gap package validation.
- CLI help validation passed.
- Manual filtered-all CLI package produced one profile gap event with
  `data.gap=china_wealth_scope_policy_filtered_all`,
  `collection_readiness.status=scope_policy_filtered_all`,
  `can_enter_finclaw=false`, no asset-value summary, and all 20 Investor Wiki
  subdimensions at `support_level=none`.
- The manual filtered-all package passed
  `tools/validate_collector_package.py --collector china-wealth-assets`.
- JSON metadata validation passed for the FinClaw catalog, invocation
  contracts, and China wealth skill metadata.
- FinClaw catalog tests and batch runner tests passed.
- Full collector regression suite passed.
- Project validation passed with `tools/validate_project.py`.

## Remaining Real Validation

- Run against real Alipay, Tiantian Fund, Danjuan, Qieman, and bank wealth
  exports/PDF/HAR/read-only-screen samples under realistic scope policies.
- Validate default account/product/platform allowlists on real user packages.
- Confirm complete account-boundary proof per platform before promoting beyond
  partial authorized input.
