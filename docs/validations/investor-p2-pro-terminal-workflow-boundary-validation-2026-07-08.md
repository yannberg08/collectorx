# P2 Professional Terminal Workflow Boundary Validation - 2026-07-08

This validation records the unified workflow-boundary proof pass for
`pro-terminal-usage`.

## Scope

Collector path:

- Vertical source: `pro-terminal-usage`
- Skill: `skills/pro-terminal-usage`
- FinClaw target: professional research workflow evidence for Wind, Choice,
  iFinD, and Bloomberg workspaces, watchlists, searches, downloads, exports,
  templates, models, factors, datasets, fields, function codes, symbols,
  projects, workflow topics, and license-safe source boundaries

This pass keeps the collector local, user-authorized, and workflow-metadata
only. It does not log in to terminal accounts, collect terminal credentials,
collect license keys, mirror vendor databases, mirror licensed content bodies,
mirror public market data, place orders, or claim a complete terminal usage
history before real licensed-account validation.

## Product Changes

- Upgraded `pro-terminal-usage` to `0.2.5`.
- Added `manifest.workflow_boundary_proof` as the single FinClaw gate for:
  authorized input presence, terminal coverage, activity coverage,
  workflow-field coverage, workflow-topic coverage, workflow surface counts,
  source-boundary counts, license safety, Wiki flow, false claims, and
  completion blockers.
- Mirrored `workflow_boundary_proof` into
  `investor_wiki_evidence.v1.json.coverage_summary`.
- Updated package `SUMMARY.md` to show the proof level and licensed-content
  mirror state.
- Preserved user personal workflow metadata while keeping content previews
  capped and license/credential fields filtered.

## Fixture Validation

Validated scenarios:

- A partial Wind/Choice/iFinD workflow package produces
  `medium_partial_workflow_boundary`, enters FinClaw Lake, stays
  workflow-metadata-only, and reports missing Bloomberg coverage.
- A broad Bloomberg/Choice/Wind/iFinD package produces
  `strong_partial_workflow_boundary`, with all expected terminals, all expected
  activities, all recommended workflow fields, all expected workflow topics,
  content-preview limits, ZIP provenance, unsafe ZIP member skipping, and
  license-safe false claims.
- A missing input produces `no_authorized_terminal_input`, cannot enter FinClaw
  Lake as workflow evidence, and keeps the missing input in source-boundary
  audit.
- Evidence packages expose the same boundary proof for SoulMirror/FinClaw
  ingestion.
- False claims remain explicit: no complete terminal usage history, no real
  account validation, no license-safe account review, no vendor database mirror,
  no licensed content body mirror, no public market data mirror, no credentials,
  no license keys, no order mutation, and no direct Wiki write.

Commands:

```bash
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python -m py_compile skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py skills/pro-terminal-usage/scripts/pro_terminal_usage.py skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
python3 -m json.tool collectors/finclaw-investor-catalog.json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

Result:

- Passed.

## Current Gate

- Authorized CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow import: G1/G2
  baseline+audit.
- Unified workflow-boundary proof: G1/G2 baseline+audit.
- Professional terminal Investor Wiki evidence routing: G1/G2 baseline+audit.
- Real Wind/Choice/iFinD/Bloomberg account/export validation: not done in this
  pass.
- Legal/license review and complete terminal-usage-history claims: false until
  real account validation and license review pass.

## Remaining Before Production Candidate

- Validate real Wind exports or local workflow artifacts.
- Validate real Choice exports or local workflow artifacts.
- Validate real iFinD exports or local workflow artifacts.
- Validate real Bloomberg authorized workflow exports without mirroring
  licensed content.
- Confirm Windows/macOS/Linux export paths, encodings, HTML/log formats, and ZIP
  behavior.
- Review workflow-topic false positives on real user samples.
- Complete legal/license review for each vendor boundary.
