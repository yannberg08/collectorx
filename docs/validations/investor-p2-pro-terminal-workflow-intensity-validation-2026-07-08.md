# P2 Professional Terminal Workflow Intensity Validation - 2026-07-08

This validation records the workflow-intensity and lineage pass for
`pro-terminal-usage`.

## Scope

Collector path:

- Vertical source: `pro-terminal-usage`
- Skill: `skills/pro-terminal-usage`
- FinClaw target: professional research workflow evidence for Wind, Choice,
  iFinD, and Bloomberg workspaces, watchlists, searches, downloads, exports,
  templates, models, factors, datasets, fields, function codes, query terms,
  query parameters, export paths, row counts, workspace/template IDs, object
  counts, source provenance, and license-safe workflow boundaries

This pass keeps the collector local, user-authorized, and workflow-metadata
only. It does not log in to terminal accounts, collect terminal credentials,
collect license keys, mirror vendor databases, mirror licensed content bodies,
mirror public market data, place orders, or claim a complete terminal usage
history before real licensed-account validation.

## Product Changes

- Upgraded `pro-terminal-usage` to `0.2.6`.
- Added per-event workflow-intensity and lineage metadata:
  `query_terms`, `parameters`, `export_path`, `row_count`, `workspace_id`,
  `template_id`, `symbol_count`, `field_count`, `dataset_count`,
  `factor_count`, `watchlist_size`, and `lineage_ref`.
- Added `manifest.workflow_intensity_summary` with query-term counts,
  parameter-key counts, export row totals, workspace/template ID counts,
  function-code counts, dataset/field/factor/template/workspace/download-format
  counts, and per-activity quantity totals.
- Added `workflow_intensity_boundary` inside
  `manifest.workflow_boundary_proof` so FinClaw can gate query/export lineage
  and object-count evidence before feeding Investor Wiki distillation.
- Mirrored `workflow_intensity_summary` into
  `investor_wiki_evidence.v1.json.coverage_summary`.
- Kept license-sensitive fields filtered and content previews capped.

## Fixture Validation

Validated scenarios:

- A partial Wind/Choice/iFinD workflow package emits query terms, query
  parameters, watchlist size, medium partial workflow proof, source audit, and
  license-safe false claims.
- A broad Bloomberg/Choice/Wind/iFinD package emits all expected terminal and
  activity types plus query parameters, explicit query terms, export paths,
  export row counts, workspace ID, template ID, symbol/field/dataset/factor
  counts, watchlist sizes, ZIP provenance, unsafe ZIP member skipping, and
  strong partial workflow proof.
- Missing input still emits `no_authorized_terminal_input` and cannot enter
  FinClaw Lake as workflow evidence.
- Evidence packages expose both workflow-boundary proof and workflow-intensity
  summary for SoulMirror/FinClaw ingestion.

Commands:

```bash
.venv/bin/python -m py_compile skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py skills/pro-terminal-usage/scripts/pro_terminal_usage.py skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
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

- Authorized CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow import: G1/G2
  baseline+audit.
- Workflow-intensity and lineage evidence: G1/G2 baseline+audit.
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
- Confirm Windows/macOS/Linux export paths, encodings, HTML/log formats, ZIP
  behavior, row-count semantics, and query/export lineage fields.
- Review workflow-topic and query-term false positives on real user samples.
- Complete legal/license review for each vendor boundary.
