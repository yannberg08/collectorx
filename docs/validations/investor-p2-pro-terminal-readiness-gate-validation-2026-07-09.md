# P2 Professional Terminal Readiness Gate Validation - 2026-07-09

This validation covers `pro-terminal-usage` `0.2.9`, the vertical workflow
metadata collector for user-authorized Wind, Choice, iFinD, and Bloomberg
exports.

## What Changed

- Added `manifest.usable_event_count`, `manifest.workflow_event_count`, and
  `manifest.gap_event_count`.
- Added `collection_readiness.can_enter_pro_terminal_usage_lake`,
  `can_enter_data_quality_lake`, and `can_feed_investor_wiki_evidence`.
- Routed no-input and filtered-all gap events to
  `collectorx.data_quality.collection_gaps`.
- Kept retained workspaces, watchlists, searches, downloads, model templates,
  factors, datasets, fields, query terms, parameters, export paths, row counts,
  workspace IDs, template IDs, and object counts as workflow evidence.
- Updated `investor_wiki_evidence.v1.json` so gap events do not contribute to
  route counts or Investor Wiki facts, while `generated_from.raw_event_count`
  and `generated_from.gap_event_count` preserve package observability.

## Fixture Coverage

- Wind-style JSON search and model-template records.
- iFinD-style CSV watchlist and download records.
- Choice-style HTML workspace records.
- Bloomberg-style nested JSON workspaces, searches, downloads, templates, and
  factors.
- Choice/Wind XLSX/XLSM workbooks.
- ZIP-packaged terminal exports with safe-member provenance and unsafe-member
  rejection.
- Partial authorization scope retention.
- Fully filtered authorization scope gap package.
- Missing authorized input gap package.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py \
  skills/pro-terminal-usage/scripts/pro_terminal_usage.py \
  skills/pro-terminal-usage/tests/test_pro_terminal_usage.py

.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Expected Assertions

- Retained packages set `can_enter_pro_terminal_usage_lake=true`,
  `can_enter_data_quality_lake=false`, and
  `can_feed_investor_wiki_evidence=true`.
- Fully filtered and missing-input packages set
  `can_enter_pro_terminal_usage_lake=false`,
  `can_enter_data_quality_lake=true`, and
  `can_feed_investor_wiki_evidence=false`.
- Gap-only packages keep `generated_from.event_count=0`,
  `generated_from.raw_event_count=1`, and `generated_from.gap_event_count=1`.
- Gap events route only to `collectorx.data_quality.collection_gaps`.
- Retained workflow evidence remains metadata-only and does not mirror vendor
  databases, licensed content bodies, credentials, cookies, tokens, or license
  material.

## Result

All commands above passed on 2026-07-09. The full `test_collectors.sh` run also
passed, including the professional terminal collector, shared catalog
validation, batch runner validation, project validation, and the first
investor-loop smoke test.
