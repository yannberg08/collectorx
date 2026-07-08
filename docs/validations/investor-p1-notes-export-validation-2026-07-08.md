# P1 Notes Export Validation - 2026-07-08

This validation records the second productization pass for `notes-collector`.

## Notes Export Import

Collector path:

- Generic source: `notes`
- Skill: `skills/notes-collector`

Result:

- Added `notes_api.py import` for user-authorized local note exports and folders.
- Supported inputs:
  - Markdown
  - TXT
  - HTML
  - JSON/JSONL/NDJSON
  - Evernote/Yinxiang ENEX
- Added source inference for Youdao, Evernote/Yinxiang, Notion, Markdown, and
  generic note exports.
- Generic notes still route to `internal.knowledge.notes`.
- Investment filtering remains in `investment-notes`.

Fixture validation:

- Youdao-style JSON note export is converted into `collectorx.event.v1`.
- Evernote ENEX note export is converted into `collectorx.event.v1`.
- Markdown note export is converted into `collectorx.event.v1`.
- Default event output keeps `content_preview` only; full content requires
  explicit `--include-content`.

Current gate:

- Obsidian local vault: prior G2/G3 partial on macOS.
- Authorized export import: G1/G2 baseline.
- Real Notion/Youdao/Evernote account/API validation: not done.

Remaining before production:

- Validate real Notion exports and API pages including block content.
- Validate real Youdao Cloud Note exports.
- Validate real Evernote/Yinxiang ENEX exports with attachments and resources.
- Tune source-app/path/tag allowlists and false-positive review before promoting note content
  into investor Wiki conclusions.
