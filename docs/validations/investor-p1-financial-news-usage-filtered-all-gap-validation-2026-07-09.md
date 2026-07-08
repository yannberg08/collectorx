# P1 Financial News Usage Filtered-All Gap Validation - 2026-07-09

This validation records the `financial-news-usage` `0.2.9` hardening pass for
FinClaw package ingestion. The collector now produces a validator-safe gap
package when a user-authorized finance-news usage input is fully excluded by
authorization scope policy.

## Scope

- Skill: `financial-news-usage`
- Version: `0.2.9`
- Collector: `financial-news-usage`
- Platforms: CLS, WallstreetCN, Gelonghui
- Boundary: personal usage traces only; no public-news crawl, no public article
  mirroring, no unrelated browser history, no credentials, and no investment
  conclusion.

## Added Behavior

- Filtered-all scope-policy runs emit one profile event with
  `data.gap=financial_news_scope_policy_filtered_all`.
- Missing-input/no-record gap events now carry a non-empty `time` value.
- Manifest `event_count` counts the package gap event while
  `usage_event_count=0` and `gap_event_count=1` keep usable personal usage
  evidence separate from collection-state evidence.
- Manifest readiness remains `scope_policy_filtered_all` with
  `can_enter_finclaw=false`.
- Gap events carry candidate, filtered, and reason counts but do not include
  public article bodies, local input paths, browser-history rows, credentials,
  tokens, or investment conclusions.

## Fixture Coverage

- Filtered-all fixture verifies:
  - one profile event in `lake/financial-news-usage/events.jsonl`
  - `data.gap=financial_news_scope_policy_filtered_all`
  - candidate count `1`, filtered count `1`, usage event count `0`
  - filter reason `topic_not_allowed`
  - no raw local input path in the gap event
  - `manifest.collection_readiness.status=scope_policy_filtered_all`
  - `manifest.usage_event_count=0`
  - `manifest.gap_event_count=1`
  - package validation passes with evidence required
- Missing-input fixture verifies:
  - one profile gap event with non-empty `time`
  - `data.gap=financial_news_usage_authorized_input_missing`
  - no usable usage events
  - package validation passes with evidence required

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/financial-news-usage/scripts/financial_news_usage/parser.py \
  skills/financial-news-usage/scripts/financial_news_usage.py \
  skills/financial-news-usage/tests/test_financial_news_usage.py
```

```bash
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
git diff --check
```

## Results

- Syntax validation passed for the financial-news CLI, parser module, and tests.
- Financial-news usage fixture tests passed, including normal exports,
  Chromium browser history, Safari `History.db`, ZIP-packaged browser history,
  partial scope-policy retention, filtered-all gap packages, and missing-input
  gap packages.
- Manual filtered-all CLI package produced exactly one profile gap event with
  `data.gap=financial_news_scope_policy_filtered_all`,
  `usage_event_count=0`, `gap_event_count=1`, and `can_enter_finclaw=false`.
- Manual filtered-all CLI package passed
  `tools/validate_collector_package.py --collector financial-news-usage --require-evidence`.
- JSON validation passed for the FinClaw investor catalog, invocation
  contracts, and financial-news metadata file.
- FinClaw catalog and batch-runner tests passed.
- Full collector regression suite passed.
- Project-level validation passed.
- `git diff --check` passed.

## Remaining Real Validation

- Validate real CLS, WallstreetCN, and Gelonghui app/account exports.
- Validate real subscription and alert fields.
- Validate real Safari/macOS history samples and Windows/Linux browser-history
  path workflows.
- Backtest topic classification and default authorization scopes against real
  user usage histories.
