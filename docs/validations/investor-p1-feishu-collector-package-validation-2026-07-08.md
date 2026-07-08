# P1 Feishu Collector Package Validation - 2026-07-08

This validation records the Feishu productization pass from migrated utility
status to a CollectorX package baseline. No Feishu tenant secret, app secret,
cookie, access token, refresh token, user token, private workspace export, or
live enterprise data is committed.

## Scope

- Collector: `feishu` `0.2.0`
- FinClaw target: generic Feishu Lake input for `meeting-minutes`,
  `research-documents`, and future collaboration-dialogue lenses.
- Supported authorized inputs:
  - JSON, JSONL, NDJSON
  - CSV, TSV
  - HTML
  - Markdown, TXT
  - ZIP packages containing the supported member types
- Explicit non-goal: the Feishu generic collector does not directly write
  investor Wiki evidence or claim that a record is investment-related.

## Changes Validated

- `feishu_api.py collect` now writes:
  - `lake/feishu/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Existing OAuth/API commands remain available: `doc`, `search`, `chats`,
  `links`, `send`, `upload`, `folders`, and `recordings`.
- Events cover generic Feishu surfaces:
  - messages
  - chats
  - contacts
  - documents
  - file refs and folders
  - meeting refs and recording refs
- `manifest.source_audit` reports input count, resolved file count, extension
  counts, ZIP member counts, skipped ZIP member counts, skip reason counts,
  parsed record count, emitted event count, supported extensions, and
  path-level parse results.
- Credential-like raw fields are filtered, including app secrets, cookies,
  access tokens, refresh tokens, user tokens, authorization, session, and
  password fields.
- The generic/lens boundary remains explicit: Feishu events enter Lake, but
  investor Wiki evidence is produced by downstream lenses.

## Fixture Proof

Validated by:

```bash
.venv/bin/python -m py_compile skills/feishu/scripts/feishu_api.py skills/feishu/scripts/feishu_collect/__init__.py skills/feishu/scripts/feishu_collect/parser.py skills/feishu/tests/test_feishu_collect.py
.venv/bin/python skills/feishu/scripts/feishu_api.py --help
.venv/bin/python skills/feishu/tests/test_feishu_collect.py
```

Covered fixtures:

- Feishu JSON package with message, document, file ref, and recording records.
- Feishu CSV meeting record with participants and meeting link.
- Feishu ZIP package with one safe Markdown meeting artifact and three unsafe
  traversal / Windows drive members.
- Credential filtering for an `app_secret` fixture value.
- Gap-event behavior when no authorized input is provided.

## Current Gate

- `feishu`: `baseline+audit`
- `meeting-minutes`, `research-documents`, or future collaboration lenses are
  required for investor Wiki classification
- Real Feishu account/API validation: still required
- Tenant permission and workspace-scope boundary review: still required
- Participant identity normalization on real enterprise data: still required
- False-positive review against real mixed Feishu data: still required
