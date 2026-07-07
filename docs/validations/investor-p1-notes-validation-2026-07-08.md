# P1 Notes Collector Validation - 2026-07-08

This validation records the first productization pass for notes-based investor
evidence without committing private note content.

## Environment

- Machine: macOS local development machine
- Date: 2026-07-08
- Privacy rule: raw note exports stayed under `/tmp/collectorx-real-validation`
  and are not committed.

## Generic Notes Collector

Collector path:

- Generic source: `notes` via `skills/notes-collector`

Result:

- Added `collectorx.event.v1` output for notes.
- Added full package output:
  - `lake/notes/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Default event output uses `content_preview`; full content requires
  `--include-content`.
- Generic notes route only to `internal.knowledge.notes`.
- Manifest sets `can_claim_investment_notes: false`.

Real local run:

- Source type: Obsidian-style local Markdown vault.
- Notes collected: 168.
- Event count: 168 `note` events.
- Manifest status: `events_collected`.

## Investment Notes Lens

Lens path:

- `investment-notes` via `skills/investor-source-collectors`

Result:

- Input: `lake/notes/events.jsonl` from the generic notes collector.
- Lens event count: 100.
- Manifest status: `events_collected`.
- Wiki coverage: 10 usable investor subdimensions.

Product finding:

- The shared lens manifest previously set
  `can_claim_complete_source_collection: true` when events existed. This was too
  strong. It now stays false and reports `source_collection_scope:
  partial_authorized_input`.

Current gate:

- Obsidian local source: G2/G3 partial on macOS.
- Investment-note lens: G3 partial on real local notes.
- Remaining before production: Notion API event validation, Youdao/Evernote
  adapters, user allowlists, false-positive review, Windows/Linux vault path
  validation, and optional content extraction policy.
