# P0 Filesystem Source Audit Validation

Date: 2026-07-08

## Scope

This pass hardens the generic `filesystem` collector that feeds the
`research-documents` lens.

The collector remains metadata-only:

- It collects path, name, extension, size, mtime, and path hash.
- It does not read file content.
- It does not decide whether a file is investment research.
- `research-documents` performs investment filtering and explicit content
  extraction when authorized.

## Change

Added `scan_files_with_audit` and wired it into
`filesystem_query.py collect --out-dir`.

The standard package manifest now records `source_audit` with:

- requested roots, resolved roots, and missing root count
- scanned file count and emitted event count
- skipped file count and skipped directory count
- extension coverage and emitted extension coverage
- skipped extension counts and skipped reason counts
- allowed extensions, ignored directories, size policy, and limit status
- per-root scan result rows

This lets FinClaw distinguish a true empty authorized folder from skipped files,
unsupported extensions, hidden files, ignored directories, over-size files, or a
missing root.

## Validation Result

Status: `completed-baseline+audit`

Gate reached: G1/G2-partial local package audit.

Fixture validation covers:

- Metadata-only event output.
- No content in event data.
- Manifest readiness.
- Source audit for unsupported extensions.
- Source audit for hidden files.
- Source audit for ignored directories.
- Source audit for missing roots.
- macOS/Windows/Linux default-root behavior using synthetic home directories.

Not claimed:

- Real Windows device validation.
- Real Linux device validation.
- Broad private PDF/XLSX/DOCX corpus validation.
- Screenshot OCR.
- Research content extraction by the generic filesystem collector.

Next gates:

- Run the same collector on real Windows and Linux machines.
- Backtest `research-documents` lens false positives against broader private
  research folders.
- Decide screenshot OCR policy separately before reading image content.
- Keep explicit content extraction opt-in and scoped to selected research
  documents.
