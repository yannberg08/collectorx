# P0 Email Mailbox Boundary Validation - 2026-07-08

This validation records the P0 pass that adds a stable mailbox-boundary proof to
the generic `email` collector.

## Scope

- Collector: `email-collector`
- Version: `0.5.3`
- Investor lens: `email-research`
- FinClaw target: user-authorized email evidence for broker research, IR,
  roadshow invitations, and research attachments after lens filtering.

## Productization change

- `manifest.mailbox_boundary_proof` is now emitted for both IMAP collection and
  local authorized imports.
- IMAP proof records selected account/folder boundaries, day windows, matched
  message count, fetched message count, skipped fetch count, read-only status,
  and password-output status.
- Local import proof records authorized inputs, parsed files, format coverage,
  ZIP member counts, skipped reasons, Apple Mail EMLX count, Maildir count,
  limit truncation, and archive safety flags.
- The proof explicitly keeps `complete_mailbox_claimed` and
  `complete_account_history_claimed` false.
- Body and attachment policy are part of the proof: body previews are collected,
  full body still requires `--event-include-body`, and attachment bodies remain
  excluded.
- Generic email events still do not write investor Wiki conclusions directly;
  `email-research` remains required.

## Validation commands

```bash
.venv/bin/python skills/email-collector/tests/test_events.py
.venv/bin/python -m py_compile skills/email-collector/scripts/email_api.py skills/email-collector/scripts/email_collector/events.py skills/email-collector/tests/test_events.py
```

## Verified behavior

- IMAP fixture package emits `authorized_imap_folder_window` proof with concrete
  mailbox, folder, matched-message, fetched-message, and attachment-ref facts.
- Missing IMAP account package emits `no_authorized_mailbox` proof and cannot
  enter FinClaw.
- Local EML/JSON/CSV package emits `authorized_local_export_boundary` proof.
- Apple Mail EMLX and Maildir imports are reflected in the local export proof.
- ZIP import proof records archive member counts, imported member counts, and
  unsafe/unsupported member skip reasons.
- Gap packages remain explicit and do not pretend that mailbox data was
  collected.

## Remaining production gaps

- No real mailbox is registered on this machine, so live IMAP G3 validation is
  still pending.
- Real broker/IR sender backtesting is still required.
- No-full-body leakage review must be repeated on real mailbox output.
- Real local mailbox exports from common Chinese email clients should be sampled
  before raising readiness beyond `baseline+audit`.
