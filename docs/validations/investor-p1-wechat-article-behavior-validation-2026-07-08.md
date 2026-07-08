# P1 WeChat Article Behavior Validation - 2026-07-08

This validation records the behavior-evidence pass for the generic
`wechat-favorites` collector and the `wechat-article-favorites` investor lens.

## Scope

- Generic skill: `wechat-favorites` `0.1.4`
- Lens skill: `investor-source-collectors` `0.1.20`
- FinClaw target: user-authorized public-account article actions that can help
  the investor avatar understand source influence, reading depth, sharing
  network, and symbol-level attention.

## Productization Change

Generic `wechat-favorites` events now preserve these fields when the authorized
input provides them:

- source-account type;
- article ID;
- favorite reason;
- share target;
- read duration and read progress;
- symbol hints;
- engagement counters.

`manifest.article_behavior_summary` records behavior coverage and average read
duration/progress. The `wechat-article-favorites` lens carries these fields into
`lens_surface_summary`, `investor_wiki_evidence.v1`, and
`wechat_article_boundary_proof.behavior_boundary`.

## Validation Commands

```bash
.venv/bin/python skills/wechat-favorites/tests/test_wechat_favorites.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- The generic fixture reads JSON, HTML, ZIP, and unsupported-file inputs.
- The generic manifest reports favorite/read/share/saved-file action coverage.
- The generic event payload preserves favorite reason, share target, read
  duration/progress, article ID, symbols, source-account type, and engagement
  counters.
- The generic manifest reports `article_behavior_summary` with behavior-field
  counts and read-depth averages.
- The investment lens keeps four investment article actions and filters one
  non-investment article.
- The lens surface summary reports article IDs, symbols, favorite reasons,
  share targets, read duration/progress, and engagement counters.
- `wechat_article_boundary_proof.proof_level` upgrades to
  `authorized_wechat_articles_with_behavior_surface`.
- `wechat_article_boundary_proof.behavior_boundary` reports the behavior-field
  counts and read-depth averages.
- The full CollectorX regression suite passed after the change, including
  catalog validation, batch-runner validation, package/evidence validators, and
  existing P0/P1/P2 collector tests.

## Remaining Gaps

- Real WeChat favorites database validation.
- Real public-account read-history validation.
- Account/tag allowlists and false-positive review on real user data.
- Windows/Linux path validation for exported favorites/public-account stores.
- Validation of platform-specific action metadata availability across WeChat
  versions.
