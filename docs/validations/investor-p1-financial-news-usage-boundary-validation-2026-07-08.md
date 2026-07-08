# P1 Financial News Usage Boundary Validation - 2026-07-08

This validation records the usage-boundary proof pass for the vertical
`financial-news-usage` collector.

## Scope

- Skill: `financial-news-usage` `0.2.5`
- Source: `financial-news-usage`
- Platforms: CLS, WallstreetCN, Gelonghui
- FinClaw target: personal information-consumption traces, monitoring-rule
  hints, and attention-universe evidence.

## Productization Change

`manifest.json` now includes `usage_boundary_proof`.

The proof records:

- authorized input counts and requested inputs;
- parsed and emitted event counts;
- expected/observed/missing platform and action coverage;
- usage-topic counts and missing usage-topic coverage;
- file/URL source refs, ZIP member counts, skipped unsafe ZIP members, browser
  history inputs, browser-history source apps, and domain-filtered browser
  history event counts;
- URL/domain/source-app/query/symbol/tag/text coverage plus alert and
  subscription counts.

The proof explicitly keeps these boundaries false:

- complete usage history claimed;
- complete account boundary claimed;
- public news full crawl claimed;
- public article body mirrored;
- platform-wide data claimed;
- unrelated browser history collected;
- direct app/account reconnect;
- direct final Wiki writes.

## Validation Commands

```bash
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python -m py_compile \
  skills/financial-news-usage/scripts/financial_news_usage/parser.py \
  skills/financial-news-usage/scripts/financial_news_usage.py \
  skills/financial-news-usage/tests/test_financial_news_usage.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- The mixed authorized export fixture emits five personal usage events across
  CLS, WallstreetCN, and Gelonghui.
- The proof level is
  `authorized_financial_news_usage_with_platform_action_topic_coverage`.
- The proof reports all expected platforms and all expected actions: read,
  favorite, search, subscribe, and alert.
- The proof reports usage-topic coverage for all expected topics in the fixture.
- The proof reports ZIP alert provenance, three skipped unsafe ZIP members, and
  no path-traversal or Windows-drive ZIP members collected.
- The browser-history fixture only emits CLS/WallstreetCN domain-filtered
  events and marks proof level
  `authorized_financial_news_usage_with_browser_history`.
- The missing-input fixture emits a gap package with proof level
  `no_authorized_financial_news_usage_input`.

## Remaining Gaps

- Real CLS/WallstreetCN/Gelonghui app cache validation.
- Real account/API adapters and subscription/alert-store validation.
- Safari, Windows, and Linux browser-history path validation.
- Platform inference on noisy real exports.
- Topic false-positive review against real personal reading histories.
