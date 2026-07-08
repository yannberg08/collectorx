# Investor P1 WeChat Article Surface Validation - 2026-07-08

Scope: `wechat-article-favorites` investor lens inside
`investor-source-collectors`.

Goal: prove that user-owned WeChat favorite/read/share/saved-article evidence
can become structured investment-avatar information-source evidence without
claiming that public-account content itself is a user fact.

Validated changes:

- `wechat-article-favorites` classifies broker research, company fundamentals,
  market strategy, industry themes, valuation methods, portfolio cases, risk
  warnings, and macro policy article surfaces.
- `manifest.lens_surface_summary` and
  `investor_wiki_evidence.v1.coverage_summary.source_surface_summary` report:
  - expected and missing article surfaces
  - primary article surface counts
  - saved/read/share/saved-file action counts
  - item type counts
  - upstream collector counts
  - source-account type counts
  - source-account count
  - public-account article count
  - URL, tag, text-preview, and action-time coverage
  - matched symbol event count
- The lens remains downstream of `wechat-favorites` and does not write final
  Wiki pages directly.

Fixture coverage:

- Favorite action from a broker research public account.
- Read action from a finance strategy account with macro/policy evidence.
- Saved-file action from a valuation-method article.
- Share action from a portfolio/risk article.
- One unrelated life article, which is filtered out.

Validation commands:

```bash
.venv/bin/python -m py_compile skills/investor-source-collectors/scripts/investor_sources/classifier.py skills/investor-source-collectors/scripts/investor_sources/events.py skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

Result:

- Local py_compile passed.
- `investor-source-collectors` test suite passed.

Remaining production gaps:

- Validate real WeChat favorites/public-account stores.
- Add user-configurable account/tag allowlists.
- Validate action metadata across macOS, Windows, and Linux export paths.
- Backtest false positives against mixed personal saved articles.
