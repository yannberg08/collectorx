# P2 Social Activity Topic Surface Validation - 2026-07-08

This validation records the social-topic and lens-surface pass for
`social-activity` and `social-investment-influence`.

## Scope

Collector paths:

- Generic source: `social-activity`
- Lens target: `social-investment-influence`
- Skills: `skills/social-activity` and `skills/investor-source-collectors`
- FinClaw target: weak investment influence, attention-source, and
  corroboration-candidate evidence only

This pass does not scrape platform-wide content, mirror full creator profiles,
collect platform credentials, or allow social traces to become standalone
investment conclusions.

## Product Changes

- Upgraded `social-activity` to `0.2.4`.
- Upgraded `investor-source-collectors` to `0.1.9`.
- Added per-event `social_topics`, `primary_social_topic`, and
  `social_topic_terms`.
- Added topic coverage to `manifest.influence_surface_summary`:
  - expected social topics
  - social topic counts
  - primary social topic counts
  - platform/topic counts
  - action/topic counts
  - missing expected social topics
  - events with social topics
- Added `social_influence_surface_summary` to
  `social-investment-influence` manifest/evidence output.
- Kept `investment_claim_allowed: false`, `requires_corroboration: true`, and
  `usable_as_investment_conclusion: false`.

## Fixture Validation

Validated scenarios:

- Weibo, Bilibili, and Xiaohongshu package fixtures still emit expected follow,
  like, favorite, watch, comment, share, and saved-page events.
- Investment social records classify into macro, strategy, industry,
  fundamental, fund/wealth, trading review, risk control, portfolio watch,
  creator education, and HK/US weak influence topics.
- Entertainment fixture `游戏直播剪辑` is not assigned investment social topics.
- The generic manifest reports all expected social topics covered in the package
  fixture.
- The lens manifest/evidence reports social-topic, platform, action, creator,
  engagement, and weak-evidence boundaries after investment filtering.
- Source audit, ZIP provenance, unsafe ZIP member skipping, credential
  filtering, content/comment preview caps, weak-evidence policy, and
  preview-only content policy remain covered.

Commands:

```bash
python3 /Users/pengyingan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/social-activity
python3 /Users/pengyingan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/investor-source-collectors
python3 -m json.tool skills/social-activity/.collectorx.json
python3 -m json.tool skills/investor-source-collectors/.collectorx.json
python3 -m json.tool collectors/finclaw-investor-catalog.json
.venv/bin/python -m py_compile skills/social-activity/scripts/social_activity/parser.py skills/social-activity/scripts/social_activity.py skills/social-activity/tests/test_social_activity.py skills/investor-source-collectors/scripts/investor_sources/events.py skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python skills/social-activity/tests/test_social_activity.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

Result:

- Passed.

## Current Gate

- Authorized local social export import: G1/G2 baseline+audit.
- Platform, action, field, topic, source-audit, content-policy, weak-evidence,
  and lens-surface manifests: G1/G2 baseline+audit.
- Real Weibo/Bilibili/Xiaohongshu account export validation: not done in this
  pass.
- Standalone investment conclusion from social activity: false.

## Remaining Before Production Candidate

- Validate real Weibo account exports or read-only activity screens.
- Validate real Bilibili watch/favorite/like/comment exports or read-only
  activity screens.
- Validate real Xiaohongshu favorite/like/comment/share exports or read-only
  activity screens.
- Add user creator/domain allowlists.
- Backtest social-topic false positives against stronger trades, notes,
  research documents, and meetings.
