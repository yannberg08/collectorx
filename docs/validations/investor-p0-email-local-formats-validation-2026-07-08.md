# P0 Email Local Formats Validation - 2026-07-08

This validation records the P0 email pass that expands user-authorized local
email imports beyond EML/MBOX/table exports.

## Scope

- Collector: `email-collector`
- Version: `0.5.2`
- Inputs added: Apple Mail `.emlx` files and Maildir `cur/` / `new/` message
  files, including inside authorized ZIP packages.
- Evidence role: generic email evidence for broker research, IR messages,
  roadshow invitations, meeting invites, and attachments after filtering through
  the `email-research` lens.
- Explicit non-goal: live mailbox validation, password collection, full-body
  inclusion by default, attachment body extraction, or direct Investor Wiki
  conclusions from generic email events.

## Implementation

- `.emlx` is now a supported local import extension.
- Apple Mail EMLX parsing removes the leading byte-count line before parsing the
  RFC822 email message.
- Maildir import recognizes files under `cur/` and `new/` only when the content
  looks like an RFC822 email message. Ordinary extensionless files are skipped.
- ZIP packages can contain `.emlx` members and Maildir-style members while
  preserving `archive.zip::member` provenance.
- Event `raw_ref.format` now records `emlx` or `maildir` for these sources.

## Manifest Audit Added

- `apple_mail_emlx_supported`
- `apple_mail_emlx_file_count`
- `maildir_message_import_supported`
- `maildir_message_file_count`
- `<maildir>` extension coverage in `extension_counts` and ZIP member extension
  counts.

## Validation

Commands:

```bash
.venv/bin/python -m py_compile skills/email-collector/scripts/email_api.py skills/email-collector/scripts/email_collector/events.py
.venv/bin/python skills/email-collector/tests/test_events.py
```

Result:

```text
All email collector event tests passed!
```

Fixture coverage:

- Apple Mail `.emlx` folder import emits an email event with `raw_ref.format =
  emlx`.
- Maildir `cur/` import emits an email event with `raw_ref.format = maildir`.
- Extensionless non-email noise is skipped as `unsupported_extension`.
- ZIP packages can import both `.emlx` and Maildir members.
- Full bodies remain excluded from events unless `--event-include-body` is used.
- Attachment bodies are still never written.

## Remaining Gaps

- The current machine still has no registered mailbox state, so live IMAP G3
  validation remains pending.
- Real Apple Mail, Thunderbird, Dovecot, QQ Mail, 163 Mail, and Outlook exports
  should be validated with user-authorized samples.
- `email-research` still needs broader broker/IR sender backtesting and
  no-full-body leakage review against real mailboxes.
