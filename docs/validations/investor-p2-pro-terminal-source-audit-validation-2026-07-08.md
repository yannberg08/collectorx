# P2 Professional Terminal Source Audit Validation

Date: 2026-07-08

## Scope

This pass hardens the vertical `pro-terminal-usage` collector for
user-authorized Wind, Choice, iFinD, and Bloomberg workflow metadata exports,
including CSV, JSON, Excel, HTML, text/log/config, and ZIP packages.

The collector remains workflow-metadata-only:

- It emits `collectorx.event.v1` workflow events into
  `lake/pro-terminal-usage/events.jsonl`.
- It captures the user's authorized workspaces, watchlists, searches,
  downloads, exports, templates, factors, datasets, fields, function codes, and
  workflow context where present.
- It keeps content previews capped and does not mirror licensed content bodies.
- It does not collect vendor databases, public market data mirrors, research
  report bodies, credentials, authorization headers, or license material.

## Change

Added `collect_from_inputs_with_audit` and wired collection audit into standard
package manifest output while keeping the previous `collect_from_inputs` API
compatible.

`manifest.source_audit` now records:

- requested inputs and missing inputs
- resolved input file count
- extension coverage
- parsed record count and emitted event count
- skipped file counts and skipped file reasons
- ZIP archive counts, ZIP member counts, skipped ZIP member counts, and skipped
  ZIP member reasons
- path-level parse results
- limit status
- path-safety flags for POSIX traversal and Windows drive-letter archive members

Missing input now produces both a gap event and an auditable `input_missing`
reason. ZIP limit accounting now records only the records actually emitted to
the lake.

## Validation Result

Status: `completed-baseline+audit`

Gate reached: G1/G2-partial local package audit.

Fixture validation covers:

- Wind JSON search and model-template records.
- iFinD CSV watchlist and download records.
- Choice saved HTML workspace record.
- Bloomberg nested JSON workspace, search, download, model-template, and
  factor-attention records.
- Choice/Wind XLSX workbook watchlist and download records.
- iFinD ZIP package import with archive provenance.
- Unsupported local file skip reasons.
- Unsafe ZIP member skipping.
- Missing input gap audit.
- ZIP limit accounting.
- Credential/license-like raw key filtering.
- Content preview cap and content length metadata.
- Terminal/activity/workflow-field coverage, workflow surface summary, license
  policy, and evidence policy.

Not claimed:

- Real Wind native export validation.
- Real Choice native export validation.
- Real iFinD native export validation.
- Real Bloomberg workflow export validation.
- Account-level validation.
- Product/legal license boundary review.
- Real Windows, macOS, or Linux export-path validation.

Next gates:

- Validate real Wind user workspace/export artifacts.
- Validate real Choice user workspace/export artifacts.
- Validate real iFinD user workspace/export artifacts.
- Validate real Bloomberg workflow exports without mirroring licensed content.
- Add source allowlists for known terminal export folders and file naming
  patterns.
- Validate Windows/macOS/Linux path, workbook, encoding, and timezone variants.
