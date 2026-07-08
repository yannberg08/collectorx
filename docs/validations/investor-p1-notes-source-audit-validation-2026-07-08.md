# P1 Notes Source Audit Validation

Date: 2026-07-08

## Scope

This pass hardens the generic `notes` collector used for Obsidian, Notion,
Youdao, Evernote/Yinxiang, Markdown, HTML, JSON, ENEX, and ZIP authorized note
exports.

The collector remains generic:

- It emits `collectorx.event.v1` note events into `lake/notes/events.jsonl`.
- It does not decide whether a note is an investment note.
- It does not write investor Wiki evidence directly.
- `investment-notes` performs investor-specific filtering and Wiki routing.

## Change

Added `parse_notes_export_with_audit` and wired collection audit into standard
package manifest output.

`manifest.source_audit` now records:

- source type and input kind
- resolved input file count
- extension coverage
- parsed note count and emitted event count
- skipped file counts and skipped file reasons
- ZIP archive counts, ZIP member counts, skipped ZIP member counts, and skipped
  ZIP member reasons
- path-level parse results
- limit status
- path-safety flags for POSIX traversal and Windows drive-letter archive members

Obsidian vault collection also writes per-file parse status into the same audit
surface.

## Validation Result

Status: `completed-baseline+audit`

Gate reached: G1/G2-partial local package audit.

Fixture validation covers:

- Obsidian vault event package output.
- Obsidian per-file source audit.
- Youdao JSON import.
- Evernote ENEX import.
- Markdown import.
- Unsupported import file skip reasons.
- ZIP package provenance.
- Unsafe ZIP member skipping.
- All expected P1 note platform coverage.
- Preview-only content policy by default.

Not claimed:

- Real Notion account/API validation.
- Real Youdao account/export validation.
- Real Evernote/Yinxiang account/export validation.
- Real Windows or Linux vault path validation.
- Investment-note classification by the generic collector.

Next gates:

- Validate real Notion, Youdao, and Evernote/Yinxiang account/export flows.
- Validate Windows and Linux Obsidian vault path behavior on real devices.
- Tune source-app/path/tag allowlists on real user vaults and exports.
- Backtest `investment-notes` false positives against broader real note corpora.
- Keep full note body collection behind explicit `--include-content`.
