# P1 WeChat Article Boundary Validation - 2026-07-08

This validation records the boundary-proof pass for the
`wechat-article-favorites` lens.

## Scope

- Skill: `investor-source-collectors` `0.1.15`
- Lens: `wechat-article-favorites`
- Upstream generic collector: `wechat-favorites`
- FinClaw target: user-saved/read/shared/saved-file investment public-account
  articles and article-source influence evidence.

## Productization Change

`manifest.json` now includes `wechat_article_boundary_proof`.

The proof records:

- authorized input counts and requested inputs;
- candidate, matched, and filtered record counts;
- upstream collector and item-type counts;
- favorite/read/share/saved-file action counts;
- source-account type counts, unique source-account count, public-account
  article count, and symbol matches;
- URL, source-account, tag, text-preview/content-pointer, and action-time
  coverage;
- the same article surface summary already propagated to Investor Wiki evidence
  coverage.

The proof explicitly keeps these boundaries false:

- complete WeChat favorites claimed;
- complete WeChat read history claimed;
- public-account full crawl claimed;
- public article body mirrored;
- direct WeChat reconnect;
- direct final Wiki writes.

## Validation Commands

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/tests/test_investor_sources.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- The mixed WeChat article fixture reads five upstream candidates.
- The lens keeps four investment article actions and filters one
  non-investment saved article.
- `wechat_article_boundary_proof.proof_level` is
  `authorized_wechat_articles_with_source_and_content_surface`.
- The proof reports four events, five candidates, four matched events, and one
  filtered candidate.
- The proof reports one each of favorite, read, share, and saved-file actions.
- The proof reports four source accounts, four public-account articles, URL
  coverage, source-account coverage, tag coverage, text coverage, and action
  time coverage.
- The proof does not claim complete WeChat favorites, complete read history,
  public-account crawling, public article body mirroring, direct WeChat
  reconnect, or direct Wiki writes.

## Remaining Gaps

- Real WeChat favorites database validation.
- Real public-account read-history validation.
- Source account and tag allowlists on real user data.
- Windows/Linux path validation for exported favorites/public-account stores.
- False-positive review against a mixed personal reading corpus.
