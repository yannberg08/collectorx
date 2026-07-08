# P0 Email Thunderbird Local-Scan Validation - 2026-07-09

This validation records a productization pass for the P0 `email` generic
collector and the downstream `email-research` investor lens boundary.

## Scope

- Skill: `email-collector`
- Version: `0.5.5`
- Source role: user-authorized local mailbox evidence.
- Target mailbox client: Thunderbird local profile mbox files.
- Investor Wiki route: generic `email` Lake events must still pass through the
  `email-research` lens before becoming investor evidence.

## Implemented

- Added Thunderbird no-extension mbox detection for authorized local scans and
  imports.
- Detection requires a Thunderbird `Mail/` or `ImapMail/` path, or a matching
  `.msf` sidecar, plus mbox/RFC822 headers.
- Added explicit `.msf` summary-index skip reason:
  `thunderbird_summary_index`.
- Added local-scan audit fields for:
  - root statuses
  - root-type counts
  - candidate format counts
  - Thunderbird mbox file count
  - Thunderbird `.msf` skipped index count
  - scan truncation count
- Event raw refs mark parsed Thunderbird mailbox events as
  `format=thunderbird_mbox`.

## Fixture Validation

The fixture simulates a Linux Thunderbird profile:

```text
.thunderbird/abcd.default-release/
  Mail/pop.broker.example/Inbox
  Mail/pop.broker.example/Inbox.msf
```

Expected result:

- 1 email event is emitted from the `Inbox` mbox.
- `Inbox.msf` is recorded as a skipped Thunderbird summary index.
- `manifest.collection_audit.thunderbird_mbox_file_count == 1`.
- `manifest.collection_audit.local_scan_candidate_format_counts` reports
  `thunderbird_mbox`.
- `manifest.collection_audit.local_scan_root_type_counts` reports
  `thunderbird`.
- `manifest.mailbox_boundary_proof.local_export_boundary` carries the same
  Thunderbird counts and skipped-index proof.
- Full body remains excluded by default and attachment bodies are not written.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/email-collector/scripts/email_api.py \
  skills/email-collector/tests/test_events.py

.venv/bin/python skills/email-collector/tests/test_events.py
```

## Explicit Non-Claims

- This pass does not register or validate a live IMAP mailbox.
- This pass does not claim complete mailbox-history coverage.
- This pass does not read Thunderbird credentials, cookies, or profile secrets.
- This pass does not write full email bodies to events unless the user
  explicitly uses `--event-include-body`.
- This pass does not replace the `email-research` lens for investor Wiki use.
