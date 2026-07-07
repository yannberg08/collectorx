# P2 Professional Terminal Usage Validation - 2026-07-08

This validation records the first productization pass for licensed professional
terminal workflow evidence.

## Professional Terminal Usage Collector

Collector path:

- Vertical source: `pro-terminal-usage`
- Skill: `skills/pro-terminal-usage`

Result:

- Added a runnable vertical collector for user-authorized workflow exports from
  Wind, Choice, iFinD, Bloomberg, or similar professional terminals.
- Supported inputs: JSON, JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT, INI/CONF,
  and log-like text files.
- Captured user workflow metadata:
  - workspaces and dashboards
  - watchlists
  - searches
  - downloads/exports
  - model templates
  - factor attention
- Output package:
  - `lake/pro-terminal-usage/events.jsonl`
  - `manifest.json`
  - `investor_wiki_evidence.v1.json`
  - `SUMMARY.md`
- Manifest sets `license_boundary: workflow_metadata_only`.
- Evidence sets `licensed_content_mirrored: false`.

Fixture validation:

- Wind search and model-template records are converted to
  `collectorx.event.v1`.
- iFinD watchlist and download rows are converted to `collectorx.event.v1`.
- Choice saved workspace HTML is converted to `collectorx.event.v1`.
- Events route to capability-circle, research-workflow, monitoring-rule, and
  information-source evidence.

Real local candidate validation:

- Candidate files found: 20.
- `pro-terminal-usage` emitted 20 workflow events.
- Kind counts: 18 note events, 1 watchlist event, 1 other event.
- Activity counts: 18 workspace, 1 watchlist, 1 search.
- Terminal counts: 9 Wind, 11 unknown.

Current gate:

- Fixture/local workflow parser: G1.
- Real licensed Wind/Choice/iFinD/Bloomberg export validation: not done.
- The local candidate run is not sufficient to claim G3 because many files were
  generic documents with professional-terminal terms rather than native terminal
  exports.

Remaining before production:

- Validate real Wind user workspace/export artifacts.
- Validate real Choice user workspace/export artifacts.
- Validate real iFinD user workspace/export artifacts.
- Confirm license-safe boundaries with product/legal review.
- Add source allowlists for terminal export folders and file naming patterns.
- Add Windows/macOS/Linux path and encoding tests for terminal exports.
- Backtest whether terminal workflow traces improve the investor Wiki without
  importing vendor-owned database content.
