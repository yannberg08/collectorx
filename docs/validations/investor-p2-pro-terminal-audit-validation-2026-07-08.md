# P2 Professional Terminal Audit Validation - 2026-07-08

This validation records the audit/license-boundary pass for
`pro-terminal-usage`.

## Scope

Collector path:

- Vertical source: `pro-terminal-usage`
- Skill: `skills/pro-terminal-usage`
- FinClaw target: investor research workflow, attention universe, analysis
  ability, monitoring rules, and information-source evidence

This pass strengthens user-authorized workflow packages. It does not mirror
vendor databases, public market data, research reports, announcements, licensed
content bodies, cookies, tokens, passwords, authorization headers, or license
keys.

## Product Changes

- Preserved ZIP `source_archive` and `archive_member` in `raw_ref`.
- Added per-event `content_length` while keeping `content_preview` capped.
- Added `manifest.workflow_surface_summary` for workspace, project, module,
  function code, menu path, query, symbols, universe, industries, regions,
  factors, datasets, fields, template name, download format, content preview,
  and source section availability.
- Added `manifest.source_audit` for source refs, ZIP member events, archive
  count, source section/sheet events, and unsafe ZIP collection status.
- Added `manifest.license_policy` and `manifest.evidence_policy` to keep the
  collector scoped to personal workflow metadata only.
- Hardened ZIP path handling for POSIX traversal, Windows traversal, and
  Windows drive-letter members.

## Fixture Validation

Validated scenarios:

- Wind JSON usage records emit search and model-template events.
- iFinD CSV records emit watchlist and download events.
- Choice saved HTML workspace emits a workspace event.
- Bloomberg nested JSON emits workspace, search, download, model-template, and
  factor-attention events.
- Choice/Wind XLSX workbook emits watchlist and download events.
- iFinD ZIP package emits a watchlist event with archive provenance.
- Fake license/token-like fields are removed from raw snapshots.
- Content/body-like fields are capped to preview length and content length is
  recorded separately.
- ZIP members `../unsafe.json`, `..\\windows-traversal.json`, and
  `C:\\unsafe.json` are skipped.
- Manifest reports all expected terminals, all expected activities, all
  recommended workflow fields, workflow surface summary, source audit, license
  policy, and evidence policy.

Commands:

```bash
.venv/bin/python -m py_compile skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py skills/pro-terminal-usage/scripts/pro_terminal_usage.py skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
```

Result:

- Passed.

## Current Gate

- Authorized CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow package parsing:
  G1/G2 baseline+audit.
- Terminal/activity/workflow-field coverage manifest: G1/G2 baseline+audit.
- Workflow surface, source audit, and license policy manifest:
  G1/G2 baseline+audit.
- Real Wind/Choice/iFinD/Bloomberg native export validation: not done in this
  pass.
- Product/legal license boundary review: still required before production.

## Remaining Before Production Candidate

- Validate real Wind user workspace/export artifacts.
- Validate real Choice user workspace/export artifacts.
- Validate real iFinD user workspace/export artifacts.
- Validate real Bloomberg workflow exports without mirroring licensed content.
- Add source allowlists for known terminal export folders and file naming
  patterns.
- Validate Windows/macOS/Linux path, workbook, and encoding variants.
