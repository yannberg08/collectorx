# P2 Social Activity Browser History Validation - 2026-07-08

This validation records the browser-history source pass for `social-activity`.

## Scope

Collector path:

- Generic source: `social-activity`
- Lens target: `social-investment-influence`
- Skill: `skills/social-activity`
- FinClaw target: weak social influence traces from Weibo, Bilibili, and
  Xiaohongshu user activity exports, saved pages, ZIP packages, and
  user-authorized browser-history copies

This pass keeps the collector local, user-authorized, preview-only, and weak
evidence only. It does not log in to social accounts, collect platform
credentials, scrape platform-wide content, collect unrelated browser history,
mirror full creator profiles, or let social activity become a standalone
investment conclusion.

## Product Changes

- Upgraded `social-activity` to `0.2.6`.
- Added read-only parsing for Chromium/Safari browser-history copies, including
  extensionless `History` files and `.sqlite`/`.sqlite3`/`.db` copies.
- Added domain filtering before history rows enter Lake. Only configured social
  platform domains are emitted as events.
- Browser-history events preserve `source_app`, URL/domain, visit ID, visit
  count, typed count, transition, and transition type.
- Added browser-history input/event/source-app audit fields to
  `manifest.source_audit`.
- Added browser-history event count, source-app counts, visit totals, typed
  totals, and transition-type counts to `manifest.influence_surface_summary`.
- Added browser-history source counts and domain-filtering policy to
  `manifest.social_activity_boundary_proof`.
- Package `SUMMARY.md` now reports browser-history event counts.

## Fixture Validation

Validated scenarios:

- A Chromium `History` copy containing Bilibili, Weibo, Xiaohongshu, and
  unrelated domains emits only the three supported social-domain events.
- Browser-history rows become `watch` weak-signal events and keep
  `investment_claim_allowed: false` plus `requires_corroboration: true`.
- Visit count, typed count, and transition type are preserved in events and
  summarized in manifest.
- Source audit records one browser-history input and three browser-history
  events.
- Boundary proof states domain filtering and explicitly rejects unrelated
  browser-history collection.

Commands:

```bash
.venv/bin/python -m py_compile skills/social-activity/scripts/social_activity/parser.py skills/social-activity/scripts/social_activity.py skills/social-activity/tests/test_social_activity.py
.venv/bin/python skills/social-activity/tests/test_social_activity.py
python3 -m json.tool collectors/finclaw-investor-catalog.json
python3 -m json.tool collectors/finclaw-invocation-contracts.json
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

Result:

- Passed.

## Current Gate

- Authorized JSON/CSV/Excel/HTML/TXT/ZIP social activity import: G1/G2
  baseline+audit.
- Authorized browser-history copy import: G1/G2 baseline+audit.
- Social activity boundary proof: G1/G2 baseline+audit.
- `social-investment-influence` lens routing: G1/G2 baseline+audit.
- Real Weibo/Bilibili/Xiaohongshu account/export validation: not done in this
  pass.
- Real browser path validation across macOS/Windows/Linux: not done in this
  pass.

## Remaining Before Production Candidate

- Validate real Weibo, Bilibili, and Xiaohongshu account exports or saved data.
- Validate real Chromium, Edge, Safari, and platform-app browser-history paths
  on macOS/Windows/Linux.
- Add user-tuned platform/domain and creator allowlists.
- Review social-topic false positives on real user samples.
- Backtest weak social evidence against stronger holdings, trades, notes,
  research documents, and meeting records before using it in the investor Wiki.
