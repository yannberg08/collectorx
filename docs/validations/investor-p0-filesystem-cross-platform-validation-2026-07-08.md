# P0 Filesystem Cross-Platform Validation

Date: 2026-07-08

## Scope

This pass strengthens the generic `filesystem` collector that feeds the
`research-documents` lens.

The collector remains metadata-only:

- It collects path, name, extension, size, mtime, and path hash.
- It does not read file content.
- It does not decide whether a file is investment research.
- `research-documents` performs investment filtering and explicit content
  extraction when authorized.

## Change

Added a testable `platform_default_root_plan`:

- macOS: Documents, Desktop, Downloads, and iCloud Drive when present.
- Windows: Documents, Desktop, Downloads, OneDrive, and Documents/OneDrive when
  present.
- Linux: Documents, Desktop, and Downloads when present.

The collection manifest now records:

- `platform_default_root_plan`
- `collection_readiness.status`
- `collection_readiness.can_enter_finclaw`
- `content_read: false`
- `metadata_only: true`

## Validation Result

Status: `completed-baseline`

Gate reached: code-level cross-platform path validation.

Fixture validation covers:

- Metadata-only event output.
- No content in event data.
- Manifest readiness.
- macOS/Windows/Linux default-root behavior using synthetic home directories.

Not claimed:

- Real Windows device validation.
- Real Linux device validation.
- Research content extraction by the generic filesystem collector.

Next gates:

- Run the same collector on real Windows and Linux machines.
- Backtest `research-documents` lens false positives against broader private
  research folders.
- Keep explicit content extraction opt-in and scoped to selected research
  documents.
