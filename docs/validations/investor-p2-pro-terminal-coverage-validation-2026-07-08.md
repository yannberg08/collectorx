# P2 Professional Terminal Coverage Validation - 2026-07-08

This validation records the third productization pass for
`pro-terminal-usage`.

## Scope

Collector path:

- Vertical source: `pro-terminal-usage`
- Skill: `skills/pro-terminal-usage`
- FinClaw target: investor research workflow, attention universe, analysis
  ability, monitoring rules, and information-source evidence

This pass improves user-authorized local workflow packages. It does not mirror
vendor databases, public market data, research reports, announcements, licensed
content bodies, cookies, tokens, passwords, or authorization headers.

## Product Changes

- Added authorized ZIP import for professional-terminal workflow packages.
- ZIP import supports JSON/JSONL/NDJSON, CSV/TSV, XLSX/XLSM, HTML, Markdown,
  TXT, INI, CONF, and LOG members.
- ZIP import skips absolute paths and `..` path traversal members.
- File/ZIP member provenance is preserved in `raw_ref.path` as
  `archive.zip::member`.
- Added `manifest.terminal_coverage` for expected P2 terminals:
  - `wind`
  - `choice`
  - `ifind`
  - `bloomberg`
- Added `manifest.activity_coverage` for expected workflow activities:
  - `workspace`
  - `watchlist`
  - `search`
  - `download`
  - `model_template`
  - `factor_attention`
- Added `manifest.workflow_field_coverage` for recommended metadata fields such
  as workspace, project, module, function code, menu path, query, symbols,
  universe, industries, regions, factors, datasets, fields, template name,
  frequency, date range, download format, and file name.
- Separated collector provenance from business `path/menu_path` fields so local
  file paths are not mistaken for terminal menu paths.
- Added package summary lines for observed/missing terminals and activity types.

## Fixture Validation

Validated scenarios:

- Wind JSON usage records emit search and model-template events.
- iFinD CSV records emit watchlist and download events.
- Choice saved HTML workspace emits a workspace event.
- Bloomberg nested JSON emits workspace, search, download, model-template, and
  factor-attention events.
- Choice/Wind XLSX workbook emits watchlist and download events.
- iFinD ZIP package emits a watchlist event and preserves
  `ifind_workflow.zip::usage/ifind_watchlist.json`.
- Fake license/token-like fields are removed from raw snapshots.
- Content/body-like fields are capped to preview length and are not treated as
  licensed database mirrors.
- ZIP member `../unsafe.json` is skipped.
- Fixture reports all expected terminals, all expected activities, and all
  recommended workflow fields observed.

Commands:

```bash
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python -m py_compile skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py skills/pro-terminal-usage/scripts/pro_terminal_usage.py
```

Result:

- Passed.

## Current Gate

- Authorized CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow package parsing:
  G1/G2 baseline.
- Terminal/activity/workflow-field coverage manifest: G1/G2 baseline.
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
