# P2 Professional Terminal Export Package Validation - 2026-07-08

This validation records the second productization pass for
`pro-terminal-usage`.

## Export Package Import

Collector path:

- Vertical source: `pro-terminal-usage`
- Skill: `skills/pro-terminal-usage`

Result:

- Upgraded `pro-terminal-usage` to `0.2.0`.
- Added XLSX/XLSM workbook parsing for authorized workflow exports.
- Expanded multi-section JSON packages so one export can contain:
  - workspaces and dashboards
  - watchlists
  - searches and queries
  - downloads and exports
  - templates and models
  - factors and indicators
- Added workflow metadata useful to the investor avatar:
  - source section / sheet
  - project, strategy, and portfolio names
  - function codes, commands, formulas, and menu paths
  - universe, symbols, industries, markets, and regions
  - datasets, databases, tables, fields, and indicators
  - frequency, date range, start/end dates
  - download format, file name, and local file path hint
- Strengthened field-name normalization, list parsing, recursive credential and
  license filtering, and content/body preview capping.

Fixture validation:

- Bloomberg-style nested JSON emits workspace, search, download,
  model-template, and factor-attention events.
- Choice/Wind-style XLSX workbook emits watchlist and download events.
- Fake license data is removed from raw snapshots.
- Content/body-like fields are capped to a preview and are not treated as
  licensed database mirrors.
- Manifest activity counts include package and workbook events.

Current gate:

- Authorized CSV/JSON/Excel workflow package parsing: G1/G2 baseline.
- Real Wind/Choice/iFinD/Bloomberg native export validation: not done.
- Product/legal license boundary review: still required before production.

Remaining before production:

- Validate real Wind user workspace/export artifacts.
- Validate real Choice user workspace/export artifacts.
- Validate real iFinD user workspace/export artifacts.
- Validate real Bloomberg workflow exports without mirroring licensed content.
- Add source allowlists for known terminal export folders and file naming
  patterns.
- Validate Windows/macOS/Linux path, workbook, and encoding variants.
