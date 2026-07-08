# P1 Notes Source Policy Validation - 2026-07-09

This validation records the source-app/path/tag authorization-scope pass for
the generic `notes` collector.

## Scope

- Skill: `notes-collector` `0.2.6`
- Source: `notes`
- FinClaw target: user-authorized Obsidian, Notion, Youdao, Evernote/Yinxiang,
  Markdown/HTML/JSON/CSV/TSV/ENEX, and ZIP note exports before they are routed
  into the `investment-notes` lens.

## Productization Change

`notes_api.py import` and `notes_api.py obsidian` now accept explicit
authorization-scope filters:

- `--allow-source-app` / `--deny-source-app`;
- `--allow-path` / `--deny-path`;
- `--allow-tag` / `--deny-tag`.

The filters are applied before generic note events enter `lake/notes/events.jsonl`.
They narrow the user-authorized collection scope only; they do not classify a
note as investment evidence.

`manifest.source_audit.note_source_policy` now records:

- configured allow/deny source-app filters;
- configured allow/deny path, notebook, or folder filters;
- configured allow/deny tag filters;
- candidate note count;
- filtered note count;
- filter reason counts;
- `policy_does_not_assert_investment_relevance=true`.

If an authorized input contains candidate notes but every candidate is outside
the configured scope, `collection_readiness.status` becomes
`source_policy_filtered_all`.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/notes-collector/scripts/notes/parser.py \
  skills/notes-collector/scripts/notes/events.py \
  skills/notes-collector/scripts/notes_api.py \
  skills/notes-collector/tests/test_notes_collector.py
.venv/bin/python skills/notes-collector/tests/test_notes_collector.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Verified Behavior

- A mixed authorized export containing Notion CSV rows, a Notion ZIP member,
  and a Youdao JSON note is filtered with:
  `--allow-source-app notion --allow-path "Notion Export" --allow-tag 规则 --deny-tag 生活`.
- Only the Notion notes under the allowed path with the allowed tag are emitted.
- The Youdao note is excluded with `source_app_not_allowed`.
- The life-tagged Notion row is excluded with `tag_denied`.
- ZIP provenance is preserved for the kept Notion ZIP note.
- `candidate_note_count`, `parsed_note_count`, `note_source_policy`, and
  `archive_member_event_count` are all written to `manifest.source_audit`.
- Existing Obsidian Markdown/Canvas, Youdao, Evernote ENEX, Notion table, ZIP,
  missing-input, preview-only, and path-safety tests still pass.

## Remaining Gaps

- Real Notion account/API validation.
- Real Youdao account/export validation.
- Real Evernote/Yinxiang account/export validation.
- Real-user allowlist tuning on private vaults/notebooks/tags.
- Real Windows/Linux Obsidian vault path validation.
- `investment-notes` false-positive review on broader real note corpora.
