# P1 Notes Table Import Validation - 2026-07-08

This validation records the P1 notes pass that adds user-authorized CSV/TSV
table imports to `notes-collector`.

## Scope

- Collector: `notes-collector`
- Version: `0.2.4`
- Inputs added: CSV and TSV note table exports, including inside authorized ZIP
  packages.
- Main real-world target: Notion database exports, investment rules tables,
  review templates, valuation assumptions, and research checklists.
- Evidence role: generic note evidence only. Investment-specific classification
  still belongs to the `investment-notes` lens.

## Implementation

- `.csv` and `.tsv` are now supported note export extensions.
- Each table row becomes one generic `notes` event.
- Title columns prefer `title/name/标题/名称`.
- Content columns prefer `content/text/正文/内容/备注/notes`.
- Non-metadata columns are appended to the note content preview so important
  table fields such as ticker, action, hypothesis, status, and owner are not
  dropped.
- ZIP packages can contain CSV/TSV note tables and still preserve
  `source_archive` / `archive_member` provenance.

## Manifest Audit Added

- `table_import_supported`
- `table_file_count`
- `table_row_count`
- `table_note_count`

## Validation

Commands:

```bash
.venv/bin/python -m py_compile skills/notes-collector/scripts/notes/parser.py skills/notes-collector/scripts/notes/events.py skills/notes-collector/scripts/notes_api.py
.venv/bin/python skills/notes-collector/tests/test_notes_collector.py
```

Result:

```text
notes-collector tests passed.
```

Fixture coverage:

- Notion-style CSV database export emits two generic note events.
- ZIP package containing a TSV table emits one generic note event and preserves
  archive member provenance.
- Notion source inference works from path names.
- Table extra columns are retained in the content preview.
- Full content is not written by default.
- Source audit records table file count, row count, and emitted table note
  count.

## Remaining Gaps

- Validate real Notion ZIP/database exports from user accounts.
- Validate real Youdao/Evernote table-like exports if encountered.
- Run broader investment-note false-positive backtesting on real mixed personal
  note libraries.
- Validate Windows/Linux vault and export paths.
