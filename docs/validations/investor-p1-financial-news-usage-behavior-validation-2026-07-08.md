# P1 Financial News Usage Behavior Validation - 2026-07-08

This validation records the behavior-evidence pass for the
`financial-news-usage` vertical collector.

## Scope

- Skill: `financial-news-usage` `0.2.6`
- Source: `financial-news-usage`
- FinClaw target: user-authorized CLS, WallstreetCN, and Gelonghui usage traces
  that can help the investor avatar understand information-source habits,
  search intent, monitoring rules, and alert-driven attention.

## Productization Change

Events now preserve these behavior fields when the authorized input provides
them:

- query terms;
- subscription target;
- alert condition;
- notification channel;
- trigger source;
- referrer;
- session ID;
- dwell seconds;
- visit and typed counts;
- browser transition type.

`manifest.usage_behavior_summary` records behavior-field coverage and
read-depth/browser-use totals. The same summary is propagated to
`investor_wiki_evidence.v1`, and
`usage_boundary_proof.usage_behavior_boundary` exposes it to FinClaw without
claiming complete account history or public-news crawling.

## Validation Commands

```bash
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- The authorized export fixture preserves query terms, subscription target,
  alert condition, notification channel, trigger source, referrer, session ID,
  dwell seconds, and symbols.
- `manifest.field_coverage` reports the new behavior fields.
- `manifest.usage_behavior_summary` reports query-term, subscription-target,
  alert-condition, notification-channel, trigger-source, referrer, session,
  dwell, visit, typed-count, and browser-transition coverage.
- `usage_boundary_proof.proof_level` upgrades to
  `authorized_financial_news_usage_with_behavior_surface` when behavior fields
  are present.
- Browser-history validation keeps the explicit
  `authorized_financial_news_usage_with_browser_history` proof level while
  reporting visit/typed counts, browser-history trigger source, and transition
  type counts.
- `investor_wiki_evidence.v1` includes `usage_behavior_summary` in
  `coverage_summary`.
- The full CollectorX regression suite passed after the change, including
  catalog validation, batch-runner validation, package/evidence validators, and
  existing P0/P1/P2 collector tests.

## Remaining Gaps

- Real CLS, WallstreetCN, and Gelonghui app cache validation.
- Real account API validation.
- Real subscription and alert-store field differences.
- Safari, Windows, and Linux browser-history path validation.
- Topic and behavior false-positive review on noisy real exports.
