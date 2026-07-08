# Investor P1 Financial News Topic Surface Validation - 2026-07-08

Scope: `financial-news-usage` vertical collector.

Goal: prove that user-owned finance-news usage traces can expose information
consumption topics for the investment avatar without crawling public news or
treating public articles as personal facts.

Validated changes:

- Events now include `usage_topics`, `primary_usage_topic`, and
  `usage_topic_terms`.
- `manifest.usage_surface_summary` and
  `investor_wiki_evidence.v1.coverage_summary.usage_surface_summary` report:
  - expected and missing usage topics
  - topic counts and primary topic counts
  - platform/topic counts
  - URL, domain, source-app, query, symbols, tags, text, browser-history,
    alert, and subscription coverage
- Supported topics:
  - macro policy
  - market strategy
  - industry theme
  - company fundamental
  - HK/US market
  - risk event
  - trading opportunity
  - portfolio alert

Fixture coverage:

- CLS favorite/export record for industry and company-fundamental evidence.
- Gelonghui search record for HK market and industry evidence.
- WallstreetCN subscription and saved HTML page for macro/strategy evidence.
- CLS ZIP alert for portfolio-alert, risk-event, and trading-opportunity
  evidence.
- Chromium browser-history validation remains domain-filtered.
- Unsafe ZIP members are skipped.

False-positive tightening:

- `风险偏好` is treated as market-strategy context, not risk-event evidence.
- Generic `电报` channel text is not treated as a trading-opportunity topic.

Validation commands:

```bash
.venv/bin/python -m py_compile skills/financial-news-usage/scripts/financial_news_usage/parser.py skills/financial-news-usage/scripts/financial_news_usage.py skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
```

Result:

- Local py_compile passed.
- `financial-news-usage` test suite passed.

Remaining production gaps:

- Validate real CLS, WallstreetCN, and Gelonghui account/app exports.
- Validate Safari, Windows, and Linux browser-history copies.
- Backtest topic false positives on noisy real usage exports.
- Confirm real subscription and alert field names.
