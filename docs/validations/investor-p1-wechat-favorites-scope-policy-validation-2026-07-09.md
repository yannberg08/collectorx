# P1 WeChat Favorites Scope Policy Validation - 2026-07-09

## Scope

This validation covers `wechat-favorites` `0.1.5`, the generic collector for
user-authorized WeChat favorites, saved public-account article files, read
actions, share actions, and ZIP packages.

The goal is to narrow authorized saved-article scope before generic Lake output,
while leaving investment relevance classification to the
`wechat-article-favorites` lens.

## What Changed

- `wechat_favorites.py collect` now accepts:
  - `--allow-source-account` / `--deny-source-account`
  - `--allow-source-account-type` / `--deny-source-account-type`
  - `--allow-action` / `--deny-action`
  - `--allow-tag` / `--deny-tag`
  - `--allow-domain` / `--deny-domain`
  - `--allow-keyword` / `--deny-keyword`
- Manifest `source_audit.wechat_favorites_scope_policy` records configured
  filters, candidate record count, filtered record count, filter reason counts,
  and `policy_does_not_assert_investment_relevance=true`.
- If all candidate records are excluded by policy, readiness reports
  `scope_policy_filtered_all`.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/wechat-favorites/scripts/wechat_favorites.py \
  skills/wechat-favorites/scripts/wechat_favorites/events.py \
  skills/wechat-favorites/scripts/wechat_favorites/parser.py \
  skills/wechat-favorites/tests/test_wechat_favorites.py
```

```bash
.venv/bin/python skills/wechat-favorites/tests/test_wechat_favorites.py
```

## Results

- Syntax validation passed.
- WeChat favorites fixture validation passed.
- Existing coverage still validates JSON, HTML, ZIP, unsafe ZIP member skips,
  unsupported file audit, behavior fields, symbols, engagement counters,
  content policy, and generic/lens evidence boundary.
- New scope-policy tests cover partial retention, source-account filtering,
  action filtering, tag filtering, domain filtering, keyword denial, and
  filtered-all status.

## Product Boundary

- `wechat-favorites` remains a generic collector and does not write investor
  Wiki facts directly.
- Scope policy narrows authorized saved-article/source records; it does not
  classify investment relevance.
- `wechat-article-favorites` remains responsible for deciding whether an
  article/action is useful to the investment avatar.
- This pass does not claim real WeChat favorites database validation,
  public-account read-history validation, complete favorites history, complete
  article-body mirroring, public-account full crawl, or false-positive
  backtesting.
