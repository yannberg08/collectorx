# P1 Meeting Collaboration Source Audit Validation - 2026-07-08

This validation records the source-audit hardening pass for P1 meeting and
collaboration collectors. No platform account token, cookie, meeting password,
private recording, or live enterprise workspace export is committed.

## Scope

- Collectors:
  - `meeting-artifacts` `0.3.0`
  - `collaboration-exports` `0.2.0`
- FinClaw target: generic meeting/collaboration Lake input for
  `meeting-minutes` and related investor lenses.
- Supported authorized inputs:
  - Meeting Markdown, TXT, HTML, JSON/JSONL/NDJSON, CSV/TSV, VTT, SRT, ZIP
  - DingTalk/WeCom JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT, ZIP
- Explicit non-goal: generic meeting/collaboration collectors do not directly
  write investor Wiki evidence or claim that a record is investment-related.

## Changes Validated

- `manifest.source_audit` now reports package-level input completeness:
  - `input_count`
  - `resolved_input_file_count`
  - `extension_counts`
  - `parsed_record_count`
  - `emitted_event_count`
  - `path_results`
- `manifest.source_audit` now reports ZIP member completeness:
  - `archive_member_count`
  - `archive_member_extension_counts`
  - `skipped_archive_member_count`
  - `skipped_archive_member_extension_counts`
  - `skipped_archive_member_reason_counts`
- Package summaries now surface skipped archive member count.
- Unsafe ZIP members are skipped and counted instead of silently disappearing:
  POSIX traversal, backslash traversal, and Windows drive-letter archive members
  are covered by fixture tests.
- The generic/lens boundary remains explicit: these collectors create Lake
  events and manifest audit metadata; investor Wiki evidence is still produced
  by downstream lenses.

## Fixture Proof

Validated by:

```bash
.venv/bin/python -m py_compile skills/meeting-artifacts/scripts/meeting_artifacts.py skills/meeting-artifacts/scripts/meeting_artifacts/parser.py skills/meeting-artifacts/scripts/meeting_artifacts/events.py skills/collaboration-exports/scripts/collaboration_exports.py skills/collaboration-exports/scripts/collaboration_exports/parser.py
.venv/bin/python skills/meeting-artifacts/tests/test_meeting_artifacts.py
.venv/bin/python skills/collaboration-exports/tests/test_collaboration_exports.py
python3 /Users/pengyingan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/meeting-artifacts
python3 /Users/pengyingan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/collaboration-exports
python3 -m json.tool collectors/finclaw-investor-catalog.json
PYTHON=.venv/bin/python bash test_collectors.sh
```

Covered fixtures:

- Local Markdown minutes and VTT transcript with input/extension/record counts.
- DingTalk, WeCom, Tencent Meeting, and Feishu-style meeting exports.
- Meeting ZIP package with one safe member and three unsafe traversal / Windows
  drive members.
- DingTalk collaboration JSON package with messages, file refs, contacts, and
  sanitized credential-like raw fields.
- DingTalk ZIP collaboration package with one safe meeting member and three
  unsafe traversal / Windows drive members.
- WeCom CSV message and meeting refs plus gap-event behavior.

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
