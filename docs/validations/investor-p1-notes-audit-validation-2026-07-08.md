# P1 Notes Audit Validation - 2026-07-08

This validation records the audit/content-policy pass for `notes-collector`.
No Notion token, cookie, service credential, private note payload, or live
account export is committed.

## Scope

- Collector: `notes-collector` `0.2.2`
- FinClaw target: generic notes Lake input for the `investment-notes` lens.
- Supported authorized inputs: Obsidian vaults, Notion API metadata, Markdown,
  TXT, HTML, JSON/JSONL/NDJSON, Evernote ENEX, and ZIP export packages.
- Explicit non-goal: generic notes do not directly write investor Wiki evidence
  or claim that a note is investment-related.

## Changes Validated

- Note events now include:
  - `content_length`
  - `content_digest`
  - `content_included`
  - URL when present
  - ZIP `source_archive` and `archive_member` references in `raw_ref`
- `manifest.field_coverage` reports recommended note metadata coverage:
  - source app
  - title
  - path
  - content preview
  - content length
  - tags
  - URL
  - event time
- `manifest.source_audit` reports source references, ZIP member event counts,
  archive counts, URL/path counts, and path-safety boundary.
- `manifest.content_policy` reports preview-only versus explicit full-content
  authorization and keeps investment classification marked as not done.
- ZIP import skips unsafe POSIX traversal, absolute paths, backslash traversal,
  and Windows drive-letter archive members.
- `manifest.evidence_policy` states that `notes-collector` is generic and
  requires the `investment-notes` lens before Wiki evidence is produced.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/notes-collector/tests/test_notes_collector.py
```

Covered fixtures:

- Obsidian-style Markdown vault with preview-only event output.
- Youdao-style JSON, Evernote ENEX, and Markdown authorized exports.
- ZIP package containing a safe Notion Markdown member and unsafe traversal /
  Windows drive-letter members.
- Platform coverage, field coverage, content policy, source audit, and generic
  evidence-policy assertions.

The test command passed in this validation pass.

## Current Gate

- `notes-collector`: `baseline+audit`
- `investment-notes` lens: still required for investor Wiki classification
- Real Notion/Youdao/Evernote account export/API validation: still required
- Windows/Linux real vault and export-path validation: still required
- False-positive review against real mixed personal notes: still required
