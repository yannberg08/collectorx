# P1 Meeting Collaboration Audit Validation - 2026-07-08

This validation records the audit/source-provenance pass for
`meeting-artifacts` and `collaboration-exports`. No platform account token,
cookie, meeting password, private recording, or live enterprise workspace export
is committed.

## Scope

- Collectors:
  - `meeting-artifacts` `0.2.2`
  - `collaboration-exports` `0.1.1`
- FinClaw target: generic meeting/collaboration Lake input for
  `meeting-minutes` and related investor lenses.
- Supported authorized inputs:
  - Meeting Markdown, TXT, HTML, JSON/JSONL/NDJSON, CSV/TSV, VTT, SRT, ZIP
  - DingTalk/WeCom JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT, ZIP
- Explicit non-goal: generic meeting/collaboration collectors do not directly
  write investor Wiki evidence or claim that a record is investment-related.

## Changes Validated

- `meeting-artifacts` events now include:
  - text length
  - participant count
  - attachment ref count
  - ZIP `source_archive` and `archive_member`
- `meeting-artifacts` manifest now includes:
  - `field_coverage`
  - `meeting_surface_summary`
  - `source_audit`
  - generic-collector `evidence_policy`
- `collaboration-exports` now supports ZIP authorized packages and events
  preserve ZIP provenance in `raw_ref`.
- `collaboration-exports` manifest now includes:
  - `field_coverage`
  - `collaboration_surface_summary`
  - `source_audit`
  - generic-collector `evidence_policy`
- ZIP import skips unsafe POSIX traversal, backslash traversal, absolute paths,
  and Windows drive-letter archive members.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/meeting-artifacts/tests/test_meeting_artifacts.py
.venv/bin/python skills/collaboration-exports/tests/test_collaboration_exports.py
```

Covered fixtures:

- Local Markdown minutes and VTT transcript.
- DingTalk, WeCom, Tencent Meeting, and Feishu-style meeting exports.
- Meeting ZIP package with safe member and unsafe traversal / Windows drive
  members.
- DingTalk collaboration JSON package with messages, file refs, contacts, and
  sanitized credential-like raw fields.
- DingTalk ZIP collaboration package with safe meeting member and unsafe
  traversal / Windows drive members.
- WeCom CSV message and meeting refs plus gap-event behavior.

The test commands passed in this validation pass.

## Current Gate

- `meeting-artifacts`: `baseline+audit`
- `collaboration-exports`: `baseline+audit`
- `meeting-minutes` lens: still required for investor Wiki classification
- Real Feishu/DingTalk/WeCom/Tencent Meeting account/API validation: still
  required
- Participant identity normalization on real enterprise workspaces: still
  required
- Recording/transcript authorization chain validation: still required
- False-positive review against real mixed enterprise collaboration data: still
  required
