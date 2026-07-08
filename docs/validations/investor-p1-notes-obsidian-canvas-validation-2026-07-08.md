# P1 Notes Obsidian Canvas Validation - 2026-07-08

This validation records the `notes-collector` Obsidian Canvas import pass.

No Notion token, note-service credential, private live account payload, or full
note corpus is committed.

## Scope

- Collector: `notes-collector` `0.2.5`
- Generic collector target: Obsidian Markdown and Canvas files entering
  `lake/notes/events.jsonl`.
- Downstream lens target: `investment-notes`.
- Non-goal: investment relevance classification or direct investor Wiki writes.

## Added Support

- `.canvas` files are accepted in Obsidian vault collection, authorized export
  folder import, and ZIP import.
- Canvas files become generic note events.
- Event data preserves:
  - `note_format: obsidian_canvas`
  - `canvas_node_count`
  - `canvas_edge_count`
  - `linked_files`
  - text-node-derived tags
- `manifest.source_audit` records:
  - `canvas_import_supported`
  - `canvas_file_count`
  - `canvas_note_count`

## Fixture Coverage

The tests cover:

- Obsidian vault with one Markdown note and one Canvas research map.
- Authorized export folder containing Youdao JSON, Evernote ENEX, Markdown, and
  Obsidian Canvas.
- Preview-only content policy remains default.
- Generic/lens boundary remains intact.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/notes-collector/scripts/notes/parser.py \
  skills/notes-collector/scripts/notes/events.py \
  skills/notes-collector/scripts/notes_api.py \
  skills/notes-collector/tests/test_notes_collector.py

.venv/bin/python skills/notes-collector/tests/test_notes_collector.py
```

## Result

Obsidian Canvas research maps can now enter the generic notes Lake with
structured provenance and audit fields. FinClaw can use the downstream
`investment-notes` lens to decide whether those Canvas notes are investment
rules, valuation assumptions, research networks, or non-investment knowledge.

Remaining gaps:

- Real Windows/Linux Obsidian vault validation.
- Real Notion/Youdao/Evernote account/export validation.
- False-positive backtesting on mixed personal note corpora.
