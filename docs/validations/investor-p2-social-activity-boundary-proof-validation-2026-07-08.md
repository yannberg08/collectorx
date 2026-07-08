# P2 Social Activity Boundary Proof Validation - 2026-07-08

This validation records the weak-evidence boundary proof pass for
`social-activity` and the `social-investment-influence` lens.

## Scope

Collector paths:

- Generic source: `social-activity`
- Lens target: `social-investment-influence`
- Skills: `skills/social-activity` and `skills/investor-source-collectors`
- FinClaw target: weak investment influence evidence from user-authorized
  Weibo, Bilibili, and Xiaohongshu activity traces

This pass keeps the generic collector and lens strictly weak-evidence-only. It
does not scrape platform-wide content, mirror full creator profiles, mirror full
content bodies, collect private platform credentials, or claim standalone
investment conclusions.

## Product Changes

- Upgraded `social-activity` to `0.2.5`.
- Upgraded `investor-source-collectors` to `0.1.16`.
- Added `manifest.social_activity_boundary_proof` to the generic collector.
- Added `manifest.social_influence_boundary_proof` to the
  `social-investment-influence` lens.
- Added evidence
  `coverage_summary.source_boundary_proof_summary.social-investment-influence`
  so SoulMirror/FinClaw can inspect the social influence weak-evidence boundary
  from `investor_wiki_evidence.v1.json`.
- Updated collector configs, catalog, integration docs, production docs, and
  roadmap entries to expose the proof fields.

## Fixture Validation

Validated scenarios:

- A partial Weibo/Bilibili/Xiaohongshu package produces
  `medium_partial_social_activity_boundary`, enters FinClaw Lake, and still
  requires `social-investment-influence` before any investor Wiki evidence.
- A broad package produces `strong_partial_social_activity_boundary`, with all
  expected platforms, all expected actions, all recommended weak-signal fields,
  all expected social topics, content-preview limits, source audit counts, ZIP
  provenance, and unsafe ZIP member skipping.
- A missing input produces `no_authorized_social_activity_input`, cannot enter
  FinClaw Lake as usable social evidence, and keeps the missing input in
  source-boundary audit.
- The `social-investment-influence` lens emits
  `medium_partial_social_influence_boundary` for matched investment activity and
  exposes the same weak-evidence boundary in the Investor Wiki evidence package.
- False claims remain explicit: no standalone investment conclusion, no complete
  social activity history, no real account validation, no platform-wide scrape,
  no full creator-profile scrape, no full content mirror, no private platform
  credentials, and no direct Wiki write.

Commands:

```bash
.venv/bin/python skills/social-activity/tests/test_social_activity.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile skills/social-activity/scripts/social_activity/parser.py skills/social-activity/scripts/social_activity.py skills/social-activity/tests/test_social_activity.py skills/investor-source-collectors/scripts/investor_sources/events.py skills/investor-source-collectors/tests/test_investor_sources.py
python3 -m json.tool skills/social-activity/.collectorx.json
python3 -m json.tool skills/investor-source-collectors/.collectorx.json
python3 -m json.tool collectors/finclaw-investor-catalog.json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

Result:

- Passed.

## Current Gate

- Authorized JSON/CSV/Excel/HTML/TXT/ZIP social activity import: G1/G2
  baseline+audit.
- Social activity boundary proof: G1/G2 baseline+audit.
- Social investment influence lens boundary proof: G1/G2 baseline+audit.
- Investor Wiki evidence routing: G1/G2 baseline+audit, weak evidence only.
- Real Weibo/Bilibili/Xiaohongshu account/export validation: not done in this
  pass.
- Standalone investment conclusion claim: false until corroborated by stronger
  sources and reviewed by downstream logic.

## Remaining Before Production Candidate

- Validate real Weibo exports or read-only account activity screens.
- Validate real Bilibili watch/favorite/like/comment/follow/share exports.
- Validate real Xiaohongshu favorites/likes/comments/shares exports.
- Add platform/domain allowlists and creator allowlists.
- Review social-topic false positives on real user samples.
- Backtest weak influence signals against stronger trade, research document,
  note, meeting, and task evidence.
